
import os
import json
import uuid
import logging
import tempfile

from pathlib import Path
from contextvars import ContextVar

import tiktoken

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException
)
from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    APIStatusError
)
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from typing import Optional, Any

from starlette.middleware.base import BaseHTTPMiddleware

from resume_reader import read_resume, ResumeReadError
from match import match_once
from validate_extract import make_live_caller


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

load_dotenv()

ROOT = Path(__file__).resolve().parent

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_RESUME_TOKENS = 10000
MAX_RETRIES = 2
LLM_TIMEOUT = 30
ALLOWED_EXTENSIONS = {".pdf", ".txt"}

MODEL = os.getenv(
    "ANALYZER_MODEL",
    "openai/gpt-oss-120b"
)

INPUT_RATE = float(
    os.getenv("INPUT_COST_PER_MILLION_USD", "0")
)

OUTPUT_RATE = float(
    os.getenv("OUTPUT_COST_PER_MILLION_USD", "0")
)


# --------------------------------------------------
# LOGGING AND REQUEST ID
# --------------------------------------------------

request_id_context = ContextVar(
    "request_id",
    default="unknown"
)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | %(message)s"
    )
)

logger = logging.getLogger("resume_analyzer")


class RequestIdFilter(logging.Filter):

    def filter(self, record):
        record.request_id = request_id_context.get()
        return True


logger.addFilter(RequestIdFilter())


class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        request_id = str(uuid.uuid4())

        token = request_id_context.set(request_id)

        try:
            logger.info(
                "Request started: %s",
                request.url.path
            )

            response = await call_next(request)

            response.headers["X-Request-ID"] = request_id

            logger.info(
                "Request completed with status %s",
                response.status_code
            )

            return response

        except Exception:
            logger.exception("Unexpected request failure")
            raise

        finally:
            request_id_context.reset(token)


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="AI Resume Analyzer API",
    description=(
        "Analyze resumes against job descriptions "
        "using AI."
    ),
    version="1.0.0"
)

app.add_middleware(RequestIDMiddleware)


# --------------------------------------------------
# RESPONSE MODEL
# --------------------------------------------------

class AnalyzeResponse(BaseModel):

    candidate_name: Optional[str] = None
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    reasoning: str

    candidate_details: dict[str, Any]

    token_usage: dict[str, int]

    estimated_cost_usd: float


# --------------------------------------------------
# LLM CLIENT
# --------------------------------------------------

def get_client():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:

        raise HTTPException(
            status_code=503,
            detail="AI service is currently unavailable."
        )

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=LLM_TIMEOUT,
        max_retries=MAX_RETRIES
    )


# --------------------------------------------------
# TOKEN VALIDATION
# --------------------------------------------------

def count_resume_tokens(text: str) -> int:

    encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def validate_resume_tokens(text: str):

    token_count = count_resume_tokens(text)

    if token_count > MAX_RESUME_TOKENS:

        raise HTTPException(
            status_code=413,
            detail=(
                "Resume exceeds the maximum limit of "
                f"{MAX_RESUME_TOKENS} tokens."
            )
        )


# --------------------------------------------------
# ERROR HANDLING
# --------------------------------------------------

def handle_llm_error(exc):

    if isinstance(exc, RateLimitError):

        logger.warning("LLM rate limit reached")

        raise HTTPException(
            status_code=503,
            detail=(
                "AI service is busy. "
                "Please try again later."
            )
        )

    if isinstance(exc, APITimeoutError):

        logger.warning("LLM request timed out")

        raise HTTPException(
            status_code=503,
            detail=(
                "AI service timed out. "
                "Please try again."
            )
        )

    if isinstance(exc, APIConnectionError):

        logger.warning("LLM connection failed")

        raise HTTPException(
            status_code=503,
            detail="Unable to connect to AI service."
        )

    if isinstance(exc, APIStatusError):

        logger.error(
            "LLM provider returned HTTP %s",
            exc.status_code
        )

        raise HTTPException(
            status_code=502,
            detail="AI analysis service returned an error."
        )

    logger.exception("Unexpected LLM failure")

    raise HTTPException(
        status_code=502,
        detail=(
            "Unable to analyze resume. "
            "Please try again."
        )
    )


# --------------------------------------------------
# RESUME EXTRACTION
# --------------------------------------------------


def extract_resume(resume_text, client, prompt_path=None):

    # Load JSON schema
    schema_path = (
        ROOT / "schemas/resume_extraction_v1.json"
    )

    schema = json.loads(
        schema_path.read_text(encoding="utf-8")
    )

    # Initialize validator
    validator = Draft202012Validator(schema)

    # Load selected prompt
    if prompt_path is None:
        prompt_path = ROOT / "prompts/extract_resume_v1.md"

    prompt = Path(prompt_path).read_text(
        encoding="utf-8"
    )

    messages = [
        {
            "role": "system",
            "content": prompt
        },
        {
            "role": "user",
            "content": (
                "Extract this resume into JSON.\n\n"
                f"<resume>\n{resume_text}\n</resume>"
            )
        }
    ]

    total_prompt = 0
    total_completion = 0

    for attempt in range(MAX_RETRIES + 1):

        try:

            response = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages
            )

            usage = response.usage

            if usage:
                total_prompt += usage.prompt_tokens
                total_completion += usage.completion_tokens

            raw = (
                response.choices[0].message.content or ""
            )

            data = json.loads(raw)

            # Validate extracted JSON
            errors = list(
                validator.iter_errors(data)
            )

            if not errors:

                return data, {
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                    "total_tokens": (
                        total_prompt + total_completion
                    )
                }

            error_text = "; ".join(
                error.message for error in errors
            )

        except json.JSONDecodeError:

            error_text = "Invalid JSON response"

        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            APIStatusError
        ) as exc:

            handle_llm_error(exc)

        if attempt < MAX_RETRIES:

            logger.warning(
                "Invalid extraction response. Retrying."
            )

            messages.extend([
                {
                    "role": "assistant",
                    "content": raw
                },
                {
                    "role": "user",
                    "content": (
                        "Correct these validation errors: "
                        f"{error_text}. "
                        "Return valid JSON only."
                    )
                }
            ])

    raise HTTPException(
        status_code=502,
        detail="Resume extraction failed validation."
    )

# --------------------------------------------------
# COST CALCULATION
# --------------------------------------------------

def calculate_cost(usage):

    input_cost = (
        usage["prompt_tokens"]
        * INPUT_RATE
        / 1_000_000
    )

    output_cost = (
        usage["completion_tokens"]
        * OUTPUT_RATE
        / 1_000_000
    )

    return round(input_cost + output_cost, 8)


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "AI Resume Analyzer"
    }


# --------------------------------------------------
# ANALYZE API
# --------------------------------------------------

@app.post(
    "/analyze",
    response_model=AnalyzeResponse
)
async def analyze(

    resume_file: Optional[UploadFile] = File(
        default=None
    ),

    resume_text: Optional[str] = Form(
        default=None
    ),

    job_description: str = Form(...)

):

    # Validate job description

    if not job_description.strip():

        raise HTTPException(
            status_code=400,
            detail="Job description cannot be empty."
        )

    # Exactly one resume input must be provided

    has_file = resume_file is not None

    has_text = bool(
        resume_text and resume_text.strip()
    )

    if has_file == has_text:

        raise HTTPException(
            status_code=400,
            detail=(
                "Provide exactly one resume file "
                "or resume_text."
            )
        )

    # ----------------------------------------------
    # FILE UPLOAD
    # ----------------------------------------------

    if resume_file:

        filename = resume_file.filename or ""

        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:

            raise HTTPException(
                status_code=415,
                detail="Only PDF and TXT files are supported."
            )

        content = await resume_file.read(
            MAX_FILE_SIZE + 1
        )

        if len(content) > MAX_FILE_SIZE:

            raise HTTPException(
                status_code=413,
                detail=(
                    "Resume file exceeds the 5 MB limit."
                )
            )

        if not content:

            raise HTTPException(
                status_code=400,
                detail="Uploaded resume is empty."
            )

        if (
            extension == ".pdf"
            and not content.startswith(b"%PDF-")
        ):

            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file."
            )

        if extension == ".txt":

            try:
                content.decode("utf-8-sig")

            except UnicodeDecodeError:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "TXT file must use UTF-8 encoding."
                    )
                )

        temp_path = None

        try:

            with tempfile.NamedTemporaryFile(
                suffix=extension,
                delete=False
            ) as temp:

                temp.write(content)

                temp_path = Path(temp.name)

            resume = read_resume(temp_path)

        except ResumeReadError:

            raise HTTPException(
                status_code=400,
                detail="Unable to read the uploaded resume."
            )

        except OSError:

            raise HTTPException(
                status_code=400,
                detail="Unable to process the uploaded file."
            )

        finally:

            if temp_path and temp_path.exists():

                temp_path.unlink()

    else:

        resume = resume_text.strip()

    # ----------------------------------------------
    # RESUME VALIDATION
    # ----------------------------------------------

    if not resume.strip():

        raise HTTPException(
            status_code=400,
            detail="Resume contains no readable text."
        )

    validate_resume_tokens(resume)

    # ----------------------------------------------
    # AI ANALYSIS
    # ----------------------------------------------

    try:

        client = get_client()

        # Step 1: Extract candidate information

        candidate, extraction_usage = extract_resume(
            resume,
            client
        )

        # Step 2: Match candidate against job description

        match_prompt = (
            ROOT / "prompts/match_v1.md"
        ).read_text(encoding="utf-8")

        call = make_live_caller(client)

        result = match_once(
            call,
            match_prompt,
            json.dumps(
                candidate,
                ensure_ascii=False
            ),
            job_description
        )

        if not result:

            raise HTTPException(
                status_code=502,
                detail=(
                    "Job matching failed. "
                    "Please try again."
                )
            )

        # ------------------------------------------
        # MATCHING TOKEN USAGE
        # ------------------------------------------

        matching_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0
        }

        for attempt in result.get("log", []):

            tokens = attempt.get("tokens") or {}

            matching_usage["prompt_tokens"] += (
                tokens.get("prompt", 0)
            )

            matching_usage["completion_tokens"] += (
                tokens.get("completion", 0)
            )

        # ------------------------------------------
        # TOTAL TOKEN USAGE
        # ------------------------------------------

        usage = {

            "prompt_tokens": (
                extraction_usage["prompt_tokens"]
                + matching_usage["prompt_tokens"]
            ),

            "completion_tokens": (
                extraction_usage["completion_tokens"]
                + matching_usage["completion_tokens"]
            )
        }

        usage["total_tokens"] = (
            usage["prompt_tokens"]
            + usage["completion_tokens"]
        )

        # ------------------------------------------
        # FINAL RESPONSE
        # ------------------------------------------

        return {

            "candidate_name": candidate.get(
                "candidate_name"
            ),

            "score": result["score"],

            "matched_skills": result["matched"],

            "missing_skills": result["missing"],

            "reasoning": result["reasoning"],

            "candidate_details": candidate,

            "token_usage": usage,

            "estimated_cost_usd": calculate_cost(
                usage
            )
        }

    except HTTPException:

        raise

    except (
        APITimeoutError,
        APIConnectionError,
        RateLimitError,
        APIStatusError
    ) as exc:

        handle_llm_error(exc)

    except Exception:

        logger.exception(
            "Resume analysis failed."
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Resume analysis failed. "
                "Please try again."
            )
        )
