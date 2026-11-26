"""
Validation + retry extraction (Task: Validation and Retry).

Flow:
  resume file -> read_resume() -> LLM (JSON mode, temp 0)
              -> ResumeData.model_validate_json()
              -> on ValidationError: retry, feeding the error message back
                 (max 3 attempts total) -> else clear failure object.
Every attempt is logged with token usage (console + saved record).

Usage:
  python validate_extract.py --demo                        # deterministic test, no API key
  python validate_extract.py data/resumes/resume_03.pdf    # live, one messy resume
  python validate_extract.py data/resumes                  # live, batch
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pydantic import ValidationError

from models import ResumeData
from resume_reader import ResumeReadError, read_resume

load_dotenv()

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "extract_resume_v1.md"
OUT_DIR = ROOT / "output" / "validated"

BASE_URL = "https://api.groq.com/openai/v1"
MODEL = os.environ.get("ANALYZER_MODEL", "openai/gpt-oss-120b")
TEMPERATURE = 0
MAX_ATTEMPTS = 3   # 3 total attempts (1 initial + 2 retries); fail object after 3rd failure


# ------------------------------------------------------------- error fmt ---

def format_pydantic_errors(exc: ValidationError) -> str:
    """Compact human-readable message, e.g. 'years_of_experience must be <= 50'."""
    parts: list[str] = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "root"
        t = e["type"]
        if t == "less_than_equal":
            parts.append(f"{loc} must be <= {e['ctx']['le']:g}")
        elif t == "greater_than_equal":
            parts.append(f"{loc} must be >= {e['ctx']['ge']:g}")
        elif t == "too_short":
            parts.append(f"{loc} must not be empty")
        elif t == "json_invalid":
            parts.append("response is not valid JSON")
        elif t == "extra_forbidden":
            parts.append(f"unexpected field '{loc}'")
        elif t == "missing":
            parts.append(f"{loc} is required")
        else:
            parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts) or "unknown validation error"


# ------------------------------------------------------------ LLM callers --

def make_live_caller(client: OpenAI) -> Callable[..., tuple[str, dict | None]]:
    """Returns call(messages) -> (text, usage_dict). Retries transient 429s."""
    def call(messages: list[dict]) -> tuple[str, dict | None]:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    temperature=TEMPERATURE,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
            except RateLimitError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
                continue
            u = resp.usage
            usage = ({"prompt": u.prompt_tokens,
                      "completion": u.completion_tokens,
                      "total": u.total_tokens} if u else None)
            return resp.choices[0].message.content or "", usage
        raise RuntimeError("unreachable")
    return call


class MockLLM:
    """Scripted responses -> deterministic tests of the retry mechanism."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    def __call__(self, messages: list[dict]) -> tuple[str, dict | None]:
        if not self._responses:
            raise RuntimeError("MockLLM ran out of scripted responses")
        return self._responses.pop(0), None


# --------------------------------------------------------------- pipeline --

def extract_validated(call, resume_text: str, system_prompt: str, source: str) -> dict:
    """Try up to MAX_ATTEMPTS times; return success object or clear failure object."""
    log: list[dict] = []
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",
         "content": f"Extract this resume into JSON.\n\n<resume>\n{resume_text}\n</resume>"},
    ]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw, usage = call(messages)
        tok = (f"tokens: prompt={usage['prompt']}, completion={usage['completion']}, "
               f"total={usage['total']}") if usage else "tokens: n/a (mock)"

        try:
            data = ResumeData.model_validate_json(raw)      # <- required parse method
        except ValidationError as exc:
            msg = format_pydantic_errors(exc)
            log.append({"attempt": attempt, "outcome": "validation_error",
                        "error": msg, "tokens": usage, "raw": raw})
            print(f"Attempt {attempt}: validation error ({msg}) | {tok}")
            if attempt == MAX_ATTEMPTS:
                return _failure_object(source, log)
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                    f"Your JSON failed validation: {msg}. "
                    "Fix exactly this problem and return the corrected JSON object only."},
            ]
        else:
            log.append({"attempt": attempt, "outcome": "success", "tokens": usage})
            print(f"Attempt {attempt}: success | {tok}")
            return {"status": "ok", "source": source, "stage": "validation",
                    "attempts": attempt, "data": data.model_dump(), "log": log}

    return _failure_object(source, log)  # defensive; loop always returns


def _failure_object(source: str, log: list[dict]) -> dict:
    errors = [e["error"] for e in log if e["outcome"] == "validation_error"]
    last_raw = log[-1].get("raw", "") if log else ""
    print(f"FAILURE after {len(log)} attempt(s): {'; '.join(errors) or 'unknown'}")
    return {"status": "failed", "source": source, "stage": "validation",
            "attempts": len(log), "errors": errors or ["unknown failure"],
            "last_raw_output": last_raw[:500], "log": log}


def save_result(result: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(result["source"]).stem or "result"
    (OUT_DIR / f"{stem}.validated.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ runs ---

def run_resume(call, system_prompt: str, path: Path) -> dict:
    print(f"\n=== {path.name} ===")
    try:
        text = read_resume(path)
    except ResumeReadError as exc:
        print(f"Failure (read stage): {exc}")
        return {"status": "failed", "source": path.name, "stage": "read",
                "attempts": 0, "errors": [str(exc)], "log": []}
    result = extract_validated(call, text, system_prompt, source=path.name)
    print(f"STATUS {result['status']} | attempts={result['attempts']}"
          + (f" | candidate={result['data']['candidate_name']}"
             f" | skills={len(result['data']['skills'])}"
             f" | years={result['data']['years_of_experience']}"
             if result["status"] == "ok" else ""))
    return result


# ------------------------------------------------------------------ demo ---

def demo() -> None:
    """Deterministic test: one messy resume (retry exercised) + one empty resume.
    Reproduces the expected output without needing an API key."""
    print("--- DEMO MODE (scripted mock LLM) ---")
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    # -- messy resume: mock returns invalid years first, then a valid payload --
    messy_path = ROOT / "data" / "resumes" / "resume_03.pdf"
    try:
        messy_text = read_resume(messy_path)
    except ResumeReadError:
        messy_text = "PRIYA NAIR - Product Manager (placeholder messy text)"

    bad = ('{"candidate_name": "Priya Nair", "skills": ["Roadmapping", "SQL"], '
           '"years_of_experience": 120, "education": [], "strengths": [], "gaps": []}')
    good = ('{"candidate_name": "Priya Nair", "skills": ["Roadmapping", "SQL", '
            '"Figma", "Amplitude", "stakeholder management"], '
            '"years_of_experience": 7, "education": [{"degree": "MBA", '
            '"institution": "Boston University", "year": "2018"}], '
            '"strengths": ["lifted activation from 41% to 58%"], '
            '"gaps": ["no certifications listed"]}')
    print(f"\n=== {messy_path.name} (mock, 2 scripted responses) ===")
    result = extract_validated(MockLLM([bad, good]), messy_text, system_prompt,
                               source=messy_path.name)
    print(f"STATUS {result['status']} | attempts={result['attempts']}"
          f" | candidate={result['data']['candidate_name']}"
          f" | skills={len(result['data']['skills'])}"
          f" | years={result['data']['years_of_experience']}")

    # -- empty resume: caught at the read stage, zero LLM calls spent --
    empty_path = ROOT / "data" / "test" / "empty_resume.txt"
    empty_path.parent.mkdir(parents=True, exist_ok=True)
    empty_path.write_text("   \n\n   ", encoding="utf-8")   # whitespace-only
    run_resume(MockLLM([]), system_prompt, empty_path)


# ------------------------------------------------------------------ main ---

def main() -> None:
    argv = sys.argv[1:]
    if "--demo" in argv:
        demo()
        return

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Add GROQ_API_KEY to .env, or run with --demo.")
    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    call = make_live_caller(client)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert "extract_resume_v1" in system_prompt, "prompt file must contain PROMPT_ID"

    targets = [Path(a) for a in argv] or [ROOT / "data" / "resumes"]
    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            exts = {".pdf", ".txt", ".text", ".md"}
            files += sorted(p for p in t.iterdir() if p.is_file() and p.suffix.lower() in exts)
        elif t.is_file():
            files.append(t)
        else:
            sys.exit(f"Path not found: {t}")

    ok = failed = 0
    for f in files:
        result = run_resume(call, system_prompt, f)
        save_result(result)
        ok += result["status"] == "ok"
        failed += result["status"] != "ok"

    print(f"\nDone: {ok} ok, {failed} failed -> {OUT_DIR}")


if __name__ == "__main__":
    main()