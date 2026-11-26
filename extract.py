"""
Task 2: run schema-constrained extraction over all resumes.

Provider : Groq (OpenAI-compatible API), key loaded from .env
Behaviour: JSON mode (response_format=json_object), temperature 0,
           validated against schemas/resume_extraction_v1.json,
           one schema-repair retry per resume.
Output   : one JSON record per resume in output/extractions/
Usage    : python extract.py [resume-folder]   (default: data/resumes)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import OpenAI, RateLimitError

from resume_reader import SUPPORTED_TEXT_EXT, ResumeReadError, read_resume

# ---------------------------------------------------------------- config ---

load_dotenv()  # reads .env in project root -> os.environ

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schemas" / "resume_extraction_v1.json"
PROMPT_PATH = ROOT / "prompts" / "extract_resume_v1.md"
OUT_DIR = ROOT / "output" / "extractions"

PROMPT_VERSION = "extract_resume_v1"   # keep in sync with prompts/CHANGELOG.md
BASE_URL = "https://api.groq.com/openai/v1"
MODEL = os.environ.get("ANALYZER_MODEL", "openai/gpt-oss-120b")
TEMPERATURE = 0
MAX_API_ATTEMPTS = 3                   # for transient errors (429 etc.)
MAX_SCHEMA_ATTEMPTS = 2                # initial call + one repair retry

# ------------------------------------------------------------- helpers -----


def load_system_prompt() -> str:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert PROMPT_VERSION in prompt, f"{PROMPT_PATH.name} must contain its PROMPT_ID"
    return prompt


def chat_with_backoff(client: OpenAI, messages: list[dict]) -> str:
    """Call the model; retry briefly on rate-limit/transient errors."""
    for attempt in range(MAX_API_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                response_format={"type": "json_object"},   # JSON mode
                messages=messages,
            )
            return resp.choices[0].message.content or ""
        except RateLimitError:
            if attempt == MAX_API_ATTEMPTS - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s
            print(f"    rate limited, retrying in {wait}s ...")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def extract_one(client: OpenAI, system_prompt: str, resume_text: str,
                validator: Draft202012Validator) -> tuple[dict | None, list[str], str]:
    """Returns (parsed_dict | None, validation_errors, raw_response)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",
         "content": f"Extract this resume into JSON.\n\n<resume>\n{resume_text}\n</resume>"},
    ]
    raw, errors = "", []

    for _ in range(MAX_SCHEMA_ATTEMPTS):
        raw = chat_with_backoff(client, messages)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors = [f"invalid JSON: {exc}"]
        else:
            errors = [e.message for e in validator.iter_errors(parsed)]
            if not errors:
                return parsed, [], raw

        # ask the model to fix exactly what failed
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
                f"Your JSON had these problems: {errors}. "
                "Return the corrected JSON object only."},
        ]

    return None, errors, raw


def find_resumes(folder: Path) -> list[Path]:
    exts = {".pdf"} | SUPPORTED_TEXT_EXT
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in exts)


def write_record(record: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{Path(record['file']).stem}.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ main ---


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Add GROQ_API_KEY to your .env file (see .env.example).")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    system_prompt = load_system_prompt()
    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "resumes"
    if not folder.is_dir():
        sys.exit(f"Resume folder '{folder}' not found. "
                 "Run: python scripts/create_sample_resumes.py")

    files = find_resumes(folder)
    if not files:
        sys.exit(f"No .pdf/.txt resumes found in '{folder}'.")

    print(f"model={MODEL} | temperature={TEMPERATURE} | "
          f"prompt={PROMPT_VERSION} | {len(files)} file(s)\n")

    ok = schema_failed = read_failed = 0

    for path in files:
        record = {"file": path.name, "prompt_version": PROMPT_VERSION,
                  "model": MODEL, "temperature": TEMPERATURE, "status": "",
                  "extraction": None, "validation_errors": [], "read_error": None}

        try:
            text = read_resume(path)
        except ResumeReadError as exc:
            record["status"], record["read_error"] = "read_error", str(exc)
            print(f"{path.name}: Error - {exc}")
            read_failed += 1
            write_record(record)
            continue

        parsed, errors, _ = extract_one(client, system_prompt, text, validator)

        if parsed is None:
            record["status"] = "schema_error"
            record["validation_errors"] = errors
            print(f"{path.name}: Error - schema validation failed "
                  f"({len(errors)} problems)")
            schema_failed += 1
        else:
            record["status"] = "ok"
            record["extraction"] = parsed
            print(f'{path.name}: OK - {len(parsed["skills"])} skills, '
                  f'{parsed["years_of_experience"]} yrs, '
                  f'{len(parsed["education"])} education entries')
            ok += 1

        write_record(record)

    print(f"\nDone: {ok} ok, {schema_failed} schema_error, "
          f"{read_failed} read_error -> {OUT_DIR}")


if __name__ == "__main__":
    main()