import os
import json
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from jsonschema import Draft202012Validator
from openai import OpenAI

from resume_reader import read_resume, ResumeReadError
from match import match_once
from validate_extract import make_live_caller

load_dotenv()

ROOT = Path(__file__).resolve().parent
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".pdf", ".txt"}

MODEL = os.getenv("ANALYZER_MODEL", "openai/gpt-oss-120b")

app = FastAPI(
    title="AI Resume Analyzer API",
    description="Analyze resumes against job descriptions.",
    version="1.0.0"
)


def get_client():
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="API service is not configured."
        )

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )


def extract_resume(resume_text, client):
    schema = json.loads(
        (ROOT / "schemas/resume_extraction_v1.json")
        .read_text(encoding="utf-8")
    )

    validator = Draft202012Validator(schema)

    prompt = (
        ROOT / "prompts/extract_resume_v1.md"
    ).read_text(encoding="utf-8")

    messages = [
        {"role": "system", "content": prompt},
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

    for attempt in range(2):
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

        raw = response.choices[0].message.content or ""

        try:
            data = json.loads(raw)
            errors = list(validator.iter_errors(data))

            if not errors:
                return data, {
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                    "total_tokens": total_prompt + total_completion
                }

            error_text = "; ".join(
                error.message for error in errors
            )

        except json.JSONDecodeError:
            error_text = "Invalid JSON response"

        messages.extend([
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"Correct these validation errors: {error_text}. "
                    "Return valid JSON only."
                )
            }
        ])

    raise HTTPException(
        status_code=502,
        detail="Resume extraction failed validation."
    )


def calculate_cost(usage):
    input_rate = float(
        os.getenv("INPUT_COST_PER_MILLION_USD", "0")
    )
    output_rate = float(
        os.getenv("OUTPUT_COST_PER_MILLION_USD", "0")
    )

    return round(
        usage["prompt_tokens"] * input_rate / 1_000_000
        + usage["completion_tokens"] * output_rate / 1_000_000,
        8
    )


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "AI Resume Analyzer"
    }


@app.post("/analyze")
async def analyze(
    resume_file: UploadFile | None = File(default=None),
    resume_text: str | None = Form(default=None),
    job_description: str = Form(...)
):
    if not job_description.strip():
        raise HTTPException(
            status_code=400,
            detail="Job description cannot be empty."
        )

    if bool(resume_file) == bool(
        resume_text and resume_text.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one resume file or resume_text."
        )

    if resume_file:
        filename = resume_file.filename or ""
        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail="Only PDF and TXT files are supported."
            )

        content = await resume_file.read(MAX_FILE_SIZE + 1)

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Resume file exceeds the 5 MB limit."
            )

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded resume is empty."
            )

        # Validate PDF signature.
        if extension == ".pdf" and not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file."
            )

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as temp:
                temp.write(content)
                temp_path = Path(temp.name)

            resume = read_resume(temp_path)

        except (ResumeReadError, OSError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to read resume: {exc}"
            )

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    else:
        resume = resume_text.strip()

    if not resume.strip():
        raise HTTPException(
            status_code=400,
            detail="Resume contains no readable text."
        )

    client = get_client()

    # Step 1: Extract resume information.
    candidate, extraction_usage = extract_resume(
        resume, client
    )

    # Step 2: Match candidate against job description.
    match_prompt = (
        ROOT / "prompts/match_v1.md"
    ).read_text(encoding="utf-8")

    call = make_live_caller(client)

    result = match_once(
        call,
        match_prompt,
        json.dumps(candidate, ensure_ascii=False),
        job_description
    )

    if not result:
        raise HTTPException(
            status_code=502,
            detail="Job matching failed."
        )

    # Collect token usage from matching attempts.
    matching_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0
    }

    for attempt in result["log"]:
        tokens = attempt.get("tokens") or {}
        matching_usage["prompt_tokens"] += tokens.get("prompt", 0)
        matching_usage["completion_tokens"] += tokens.get(
            "completion", 0
        )

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
        usage["prompt_tokens"] + usage["completion_tokens"]
    )

    return {
        "candidate_name": candidate.get("candidate_name"),
        "score": result["score"],
        "matched_skills": result["matched"],
        "missing_skills": result["missing"],
        "reasoning": result["reasoning"],
        "candidate_details": candidate,
        "token_usage": usage,
        "estimated_cost_usd": calculate_cost(usage)
    }

