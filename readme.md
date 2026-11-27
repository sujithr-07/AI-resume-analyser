
# AI Resume Analyzer

## 1. Project Purpose

AI Resume Analyzer is an AI-powered application that evaluates resumes against job descriptions.

It extracts candidate information, identifies matching and missing skills, and generates a matching score with reasoning.

The goal is to help recruiters and candidates understand how well a resume matches a particular job role.

## 2. Features

- Upload resumes in PDF or TXT format.
- Accept resume text directly through the API.
- Extract candidate information using an LLM.
- Identify matched and missing skills.
- Generate a job matching score.
- Provide explanations for the matching score.
- Track token usage and estimated API cost.
- Validate uploaded files and file sizes.
- Handle API errors, timeouts and invalid JSON responses.
- Retry temporary LLM failures.
- Generate request IDs for logging.
- Provide automated tests and golden dataset evaluation.

## 3. Architecture

The application uses FastAPI as its backend and Groq API for AI-powered resume extraction and matching.

### Processing Flow

1. User uploads a resume or provides resume text.
2. API validates the resume format and size.
3. Resume reader extracts readable text.
4. LLM extracts structured candidate information.
5. JSON Schema validates the extracted information.
6. Matching module compares the candidate against the job description.
7. API calculates token usage and estimated cost.
8. Structured results are returned to the user.

### Architecture Diagram

```text
       User / Client
             |
             v
       FastAPI API
             |
             v
     Input Validation
             |
             v
       Resume Reader
             |
             v
      LLM Extraction
             |
             v
       JSON Validation
             |
             v
      Matching Module
             |
             v
      Score Calculation
             |
             v
      Structured Result
```

## 4. Technologies Used

- Python
- FastAPI
- Groq API
- OpenAI Python SDK
- JSON Schema
- PyMuPDF
- Pytest
- Pytest-Cov
- Python Dotenv

## 5. Project Structure

```text
AI-resume-analyser/
│
├── api.py
├── resume_reader.py
├── match.py
├── validate_extract.py
│
├── prompts/
│   ├── extract_resume_v1.md
│   ├── extract_resume_original.md
│   └── match_v1.md
│
├── schemas/
│   └── resume_extraction_v1.json
│
├── tests/
│   ├── test_api.py
│   ├── test_evaluation.py
│   ├── golden_set.json
│   ├── run_evaluation.py
│   └── evaluation_report.json
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 6. Installation and Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/sujithr-07/AI-resume-analyser.git

cd AI-resume-analyser
```

### Step 2: Create Virtual Environment

```bash
python -m venv .venv
```

Activate on Windows:

```bash
.venv\Scripts\activate
```

Activate on Linux or macOS:

```bash
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Create a `.env` file using `.env.example` as a template.

Add your Groq API key.

## 7. Environment Configuration

Example `.env.example`:

```env
GROQ_API_KEY=your_groq_api_key_here

ANALYZER_MODEL=openai/gpt-oss-120b

INPUT_COST_PER_MILLION_USD=0
OUTPUT_COST_PER_MILLION_USD=0
```

Configure cost rates according to the selected model's pricing.

Never upload your actual `.env` file or API key to GitHub.

## 8. Running the Application

Start the FastAPI server:

```bash
uvicorn api:app --reload
```

The application will be available at:

http://127.0.0.1:8000

### API Documentation

- Swagger documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## 9. API Usage

### POST /analyze

Accepts a resume file or resume text and a job description.

### Example Using Resume File

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "resume_file=@resume.pdf" \
  -F "job_description=Looking for a Python developer with SQL and FastAPI experience."
```

### Example Using Resume Text

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "resume_text=Python developer with SQL and FastAPI experience." \
  -F "job_description=Looking for a Python developer."
```

### Example Response

```json
{
  "candidate_name": "John Doe",
  "score": 85,
  "matched_skills": [
    "Python",
    "SQL",
    "FastAPI"
  ],
  "missing_skills": [
    "Docker",
    "AWS"
  ],
  "reasoning": "The candidate has strong Python backend development skills but lacks cloud experience.",
  "token_usage": {
    "prompt_tokens": 2500,
    "completion_tokens": 800,
    "total_tokens": 3300
  },
  "estimated_cost_usd": 0.0005
}
```

*Example values are illustrative.*

## 10. Error Handling

| Failure Case                   | HTTP Status |
| ------------------------------ | ----------- |
| Empty resume                   | 400         |
| Invalid PDF                    | 400         |
| Unsupported file format        | 415         |
| File larger than 5 MB          | 413         |
| Resume exceeds token limit     | 413         |
| LLM timeout                    | 503         |
| LLM rate limit                 | 503         |
| Invalid LLM JSON after retries | 502         |
| Matching failure               | 502         |

## 11. Testing and Evaluation

Run automated tests:

```bash
pytest -v
```

Run tests with coverage:

```bash
pytest --cov=api --cov-report=term-missing
```

Generate HTML coverage report:

```bash
pytest --cov=api --cov-report=html
```

Run golden dataset evaluation:

```bash
python -m tests.run_evaluation
```

The evaluation compares:

- Skill extraction precision.
- Skill extraction recall.
- Skill extraction accuracy.
- Average matching score difference across two runs.

## 12. Limitations

- Accuracy depends on resume formatting and text quality.
- Scanned PDFs may require OCR support.
- AI-generated matching scores are estimates, not guarantees of job suitability.
- LLM responses may vary between runs.
- API availability depends on the external AI provider.
- Cost estimates depend on correctly configured model pricing.
- The current golden dataset contains only eight sample resumes and may not represent all resume formats or industries.

## 13. Fairness and Responsible AI

The analyzer evaluates job-related skills and qualifications.

However, AI systems can produce biased or inconsistent results.

To improve fairness:

- Do not use protected characteristics such as age, gender, religion, race or ethnicity when evaluating candidates.
- Focus on relevant job skills and experience.
- Do not use the AI score as the only hiring decision factor.
- Allow human review of AI-generated results.
- Regularly evaluate extraction quality using diverse resume samples.
- Do not assume missing information means a candidate lacks the skill.

The system should be used as a decision-support tool, not as an automated hiring decision-maker.

## 14. Security

- API credentials are stored in environment variables.
- API keys are never returned in API responses.
- Sensitive resume information should not be written to application logs.
- Uploaded temporary files are deleted after processing.
- `.env` is excluded from version control.

## 15. Conclusion

AI Resume Analyzer provides automated resume extraction, skill matching and job-description analysis using LLM technology.

It combines structured extraction, validation, error handling, evaluation and API testing to provide a useful resume analysis service.
