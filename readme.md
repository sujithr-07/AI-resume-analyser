
# AI Resume Analyzer

An LLM pipeline that reads resumes, turns them into structured data, checks thedata is valid, and scores each candidate against job descriptions.All resume data is fictional; API keys stay in `.env` (never committed).

## Setup

```bash
python -m venv .venv.venv\Scripts\activatepip install -r requirements.txtcopy .env.example .env    # add GROQ_API_KEY and ANALYZER_MODEL=openai/gpt-oss-120b
```

Free API key: console.groq.com. If a model name stops working, Groq deprecated it —check console.groq.com → Models and update `.env`.

---

## Task 1 — Resume Input Handling

**Files:** `resume_reader.py`, `analyze.py`, `scripts/create_sample_resumes.py`

Reads resumes and turns messy PDF/text into clean text the LLM can use.

* Generates 8 dummy resumes (5 PDFs + 3 text), including one **image-only "scanned" PDF** on purpose.
* `read_resume(path)` uses PyMuPDF for PDFs, plain read for `.txt`.
* Cleans text: removes page numbers, repeated headers/footers, extra spaces.
* Empty or scanned files fail with a clear message instead of blank text.
* Reports characters and tokens for every resume.

```bash
python scripts/create_sample_resumes.pypython analyze.py data/resumes
```

**Output:** a report like `resume_01.pdf: 1350 characters, 320 tokens` — and`scanned.pdf: Error - no text found (scanned file)` (this error is the test).

---

## Task 2 — Extraction Prompt and Schema

**Files:** `schemas/resume_extraction_v1.json`, `prompts/extract_resume_v1.md`, `extract.py`

Turns each cleaned resume into structured JSON (name, skills, years ofexperience, education, strengths, gaps) using an LLM.

* The JSON Schema defines the exact shape; the versioned prompt defines the rules: **never invent facts** , use `null` when information is missing, JSON only.
* Runs with **JSON mode and temperature 0** for reproducible output.
* Every response is validated against the schema; one repair-retry if invalid.
* Includes a manual QA step: 3 resumes checked by hand, errors counted(`qa/qa_protocol.md`, `qa/qa_report.md`).

```bash
python extract.py data/resumes
```

**Output:** `output/extractions/*.json` — one record per resume with theextraction, model, and prompt version used.

---

## Task 3 — Validation and Retry

**Files:** `models.py`, `validate_extract.py`

A stricter, typed version of Task 2 using Pydantic.

* `ResumeData` enforces real constraints: `years_of_experience` between 0 and 50,`skills` list not empty, no unknown fields.
* Parses with `model_validate_json`; on a validation error, the **error message issent back to the model** and it retries — up to 3 attempts.
* After 3 failures it returns a clear failure object instead of crashing.
* Every attempt is logged with  **token usage** .
* `--demo` mode uses a scripted mock LLM, so the retry logic can be testedwith no API key.

```bash
python validate_extract.py --demo          # offline test of the retry mechanismpython validate_extract.py data/resumes    # live run (writes the files Task 4 needs)
```

**Output:** `output/validated/*.json` — validated data + attempt logs + token counts.

---

## Task 4 — Job Description Matching

**Files:** `jobs/*.json`, `prompts/match_v1.md`, `match.py`, `qa/fairness_note.md`

Scores every candidate against 2 job descriptions (Python Developer, Data Analyst).

* The prompt uses an **exact rubric** (10 pts per required skill, 8 per preferred,10/5/0 for experience) so scores are explainable, and returns`score`, `matched_skills`, `missing_skills`, `reasoning`.
* Each (resume, job) pair is run **twice at temperature 0** to check consistency;the rubric is also recomputed locally as a cross-check.
* Produces ranked candidate lists per job.
* `qa/fairness_note.md` documents the fairness risks (wording bias, compoundingerrors, proxy signals) and why a human must review scores near any cut-off.

```bash
python match.py    # requires Task 3's output
```

**Output:** `output/matching/rankings.md` (submission tables) and`match_results.json` (both runs, deltas, reasoning per pair).
