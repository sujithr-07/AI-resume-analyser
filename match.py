"""
Task 2 (matching): score extracted resumes against job descriptions.

Prereq: python validate_extract.py data/resumes  ->  output/validated/*.json

- Loads validated ResumeData records; unparseable resumes (scanned.pdf) excluded
- 2 jobs from jobs/*.json; prompt prompts/match_v1.md; JSON mode; temperature 0
- EVERY (resume, job) pair is run TWICE -> consistency check on scores
- Model score cross-checked against the rubric recomputed locally
- Every attempt logged with token usage
- Writes output/matching/match_results.json and rankings.md

Usage: python match.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from models import MatchResult
from validate_extract import MAX_ATTEMPTS, format_pydantic_errors, make_live_caller

load_dotenv()

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "match_v1.md"
JOBS_DIR = ROOT / "jobs"
RESUMES_DIR = ROOT / "data" / "resumes"
VALIDATED_DIR = ROOT / "output" / "validated"
OUT_DIR = ROOT / "output" / "matching"

BASE_URL = "https://api.groq.com/openai/v1"
MODEL = os.environ.get("ANALYZER_MODEL", "openai/gpt-oss-120b")
TEMPERATURE = 0
CONSISTENCY_TOLERANCE = 2   # max accepted |run1 - run2| at temp 0
RUBRIC_TOLERANCE = 2        # max accepted |model score - local rubric|


@dataclass
class Job:
    id: str
    title: str
    company: str
    min_years: int
    required: list[str]
    preferred: list[str]
    description: str


def load_jobs() -> list[Job]:
    jobs = []
    for p in sorted(JOBS_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        jobs.append(Job(id=d["id"], title=d["title"], company=d["company"],
                        min_years=int(d["min_years_experience"]),
                        required=list(d["required_skills"]),
                        preferred=list(d["preferred_skills"]),
                        description=d["description"]))
    return jobs


def render_jd(job: Job) -> str:
    return (f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Minimum years of experience: {job.min_years}\n"
            f"Required skills: {', '.join(job.required)}\n"
            f"Preferred skills: {', '.join(job.preferred)}\n"
            f"About the role: {job.description}")


def rubric_score(job: Job, matched: list[str], years) -> int:
    """Local recomputation of the prompt rubric (keep in sync with match_v1.md)."""
    req = len(set(matched) & set(job.required))
    pref = len(set(matched) & set(job.preferred))
    exp = 5 if years is None else (10 if years >= job.min_years else 0)
    return min(100, max(0, 10 * req + 8 * pref + exp))


def match_once(call, system_prompt: str, cand_json: str, job_text: str) -> dict | None:
    """One (resume, job) call with validation + retry. Returns dict or None."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",
         "content": f"CANDIDATE (extracted JSON):\n{cand_json}\n\n"
                    f"JOB DESCRIPTION:\n<job>\n{job_text}\n</job>\n\n"
                    "Return the MatchResult JSON now."},
    ]
    log: list[dict] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw, usage = call(messages)
        tok = (f"tokens: prompt={usage['prompt']}, completion={usage['completion']}, "
               f"total={usage['total']}") if usage else "tokens: n/a"
        try:
            m = MatchResult.model_validate_json(raw)
        except ValidationError as exc:
            msg = format_pydantic_errors(exc)
            log.append({"attempt": attempt, "outcome": "validation_error",
                        "error": msg, "tokens": usage})
            print(f"    Attempt {attempt}: validation error ({msg}) | {tok}")
            if attempt == MAX_ATTEMPTS:
                return None
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                    f"Your JSON failed validation: {msg}. Return corrected JSON only."},
            ]
        else:
            log.append({"attempt": attempt, "outcome": "success", "tokens": usage})
            print(f"    Attempt {attempt}: success | {tok}")
            return {"score": m.score, "matched": m.matched_skills,
                    "missing": m.missing_skills, "reasoning": m.reasoning,
                    "attempts": attempt, "log": log}
    return None


def load_candidates() -> tuple[list[dict], list[str]]:
    records = {}
    for rp in sorted(VALIDATED_DIR.glob("*.validated.json")):
        rec = json.loads(rp.read_text(encoding="utf-8"))
        # validate_extract.py stores the original filename under "source"
        key = rec.get("file") or rec.get("source") or rp.name.replace(".validated.json", "")
        records[key] = rec

    candidates, excluded = [], []
    for name in sorted(p.name for p in RESUMES_DIR.iterdir() if p.is_file()):
        rec = records.get(name)
        if rec and rec.get("status") == "ok" and rec.get("data"):
            candidates.append({"file": name, "data": rec["data"]})
        else:
            why = "no extraction record - run validate_extract.py first"
            if rec:
                why = (rec.get("read_error")
                       or "; ".join(rec.get("errors") or rec.get("validation_errors") or [])
                       or rec.get("status", "?"))
            excluded.append(f"{name} - {why}")
    return candidates, excluded


def write_outputs(results: list[dict], excluded: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "match_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    jobs = {j.id: j for j in load_jobs()}
    tally: dict[str, int] = {}
    lines = ["# Candidate ranking (Task 2 - Job Description Matching)", "",
             "Score = mean of 2 runs at temperature 0 (prompt match_v1; rubric: "
             "10/required skill, 8/preferred, 10/5/0 experience).", ""]

    for job_id, job in jobs.items():
        rows = [r for r in results if r.get("job") == job_id and r.get("status") == "ok"]
        rows.sort(key=lambda r: (-r["mean"], len(r["missing_skills"]), r["candidate"]))
        lines += [f"## {job.title} ({job.company})", "",
                  "| Rank | Candidate | Score | Run1/Run2 (delta) | Matched | Missing required |",
                  "|---|---|---|---|---|---|"]
        rank, prev = 0, None
        for i, r in enumerate(rows, 1):
            if prev is None or r["mean"] != prev:
                rank = i
            prev = r["mean"]
            runs = "/".join(str(s) for s in r["scores"])
            runs += f" ({r['delta']})" if r["delta"] is not None else " (n/a)"
            lines.append(f"| {rank} | {r['candidate']} | {r['mean']:g} | {runs} | "
                         f"{len(r['matched_skills'])} | {', '.join(r['missing_skills']) or '-'} |")
            tally[r["consistency"]] = tally.get(r["consistency"], 0) + 1
        lines.append("")

    lines += ["## Consistency check (2 runs per pair, temperature 0)",
              f"- identical (delta 0): {tally.get('consistent', 0)} pairs",
              f"- minor drift (1-2 pts): {tally.get('minor drift', 0)} pairs",
              f"- INCONSISTENT (>2 pts): {tally.get('INCONSISTENT', 0)} pairs", "",
              "## Excluded resumes"] + [f"- {e}" for e in excluded or ["- none"]] + [
              "", "Fairness review: see qa/fairness_note.md"]

    (OUT_DIR / "rankings.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {OUT_DIR / 'rankings.md'} and {OUT_DIR / 'match_results.json'}")


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Add GROQ_API_KEY to .env, then run validate_extract.py first.")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert "match_v1" in system_prompt, "match prompt must contain PROMPT_ID"

    candidates, excluded = load_candidates()
    if not candidates:
        sys.exit("No validated extractions. Run: python validate_extract.py data/resumes")
    jobs = load_jobs()
    if len(jobs) != 2:
        print(f"warning: expected 2 job descriptions, found {len(jobs)}")

    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    call = make_live_caller(client)
    print(f"model={MODEL} | temperature={TEMPERATURE} | prompt=match_v1 | "
          f"{len(candidates)} candidates x {len(jobs)} jobs x 2 runs\n")

    results: list[dict] = []
    for cand in candidates:
        name = cand["data"].get("candidate_name") or Path(cand["file"]).stem
        cand_json = json.dumps(cand["data"], ensure_ascii=False)
        for job in jobs:
            runs = [match_once(call, system_prompt, cand_json, render_jd(job))
                    for _ in range(2)]
            scores = [r["score"] for r in runs if r]
            if not scores:
                print(f"{name} vs {job.title}: FAILED validation - skipped")
                results.append({"candidate": name, "file": cand["file"],
                                "job": job.id, "job_title": job.title,
                                "status": "failed"})
                continue

            delta = abs(scores[0] - scores[1]) if len(scores) == 2 else None
            verdict = ("one run failed" if delta is None else
                       "consistent" if delta == 0 else
                       "minor drift" if delta <= CONSISTENCY_TOLERANCE else
                       "INCONSISTENT")
            best = runs[0] or runs[1]
            rub = rubric_score(job, best["matched"],
                               cand["data"].get("years_of_experience"))
            rub_ok = "ok" if abs(rub - best["score"]) <= RUBRIC_TOLERANCE else "RUBRIC MISMATCH"
            print(f"{name:15s} vs {job.title:16s} scores={scores} "
                  f"(delta {delta}) | rubric={rub} [{rub_ok}] | "
                  f"matched={len(best['matched'])} missing={len(best['missing'])}")

            results.append({"candidate": name, "file": cand["file"],
                            "job": job.id, "job_title": job.title, "status": "ok",
                            "scores": scores, "mean": sum(scores) / len(scores),
                            "delta": delta, "consistency": verdict,
                            "rubric_score": rub, "rubric_check": rub_ok,
                            "matched_skills": best["matched"],
                            "missing_skills": best["missing"],
                            "reasoning": best["reasoning"],
                            "runs": runs})

    write_outputs(results, excluded)


if __name__ == "__main__":
    main()