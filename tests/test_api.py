
import io
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


@pytest.fixture
def mock_client(monkeypatch):

    fake_client = MagicMock()

    monkeypatch.setattr(
        api,
        "get_client",
        lambda: fake_client
    )

    monkeypatch.setattr(
        api,
        "make_live_caller",
        lambda client: MagicMock()
    )

    monkeypatch.setattr(
        api,
        "match_once",
        lambda *args: {
            "score": 85,
            "matched": ["Python", "SQL"],
            "missing": ["Docker"],
            "reasoning": "Good technical match.",
            "log": []
        }
    )

    return fake_client


def mock_response(content):

    response = MagicMock()

    response.choices[0].message.content = content

    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150

    return response


# 1. Successful analysis

def test_successful_analysis(mock_client, monkeypatch):

    candidate = {
        "candidate_name": "John Doe",
        "skills": ["Python", "SQL"]
    }

    monkeypatch.setattr(
        api,
        "extract_resume",
        lambda *args: (
            candidate,
            {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        )
    )

    monkeypatch.setattr(
        api,
        "validate_resume_tokens",
        lambda text: None
    )

    response = client.post(
        "/analyze",
        data={
            "resume_text": "Python developer with SQL experience.",
            "job_description": "Looking for Python and SQL developer."
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["candidate_name"] == "John Doe"
    assert data["score"] == 85
    assert "Python" in data["matched_skills"]
    assert "Docker" in data["missing_skills"]
    assert data["token_usage"]["total_tokens"] == 150

    assert "X-Request-ID" in response.headers


# 2. Invalid JSON followed by valid JSON

def test_invalid_json_then_success(mock_client):

    schema = {
        "type": "object",
        "required": ["candidate_name"],
        "properties": {
            "candidate_name": {"type": "string"}
        }
    }

    api.ROOT.joinpath("schemas").mkdir(
        parents=True,
        exist_ok=True
    )

    # Use the real project schema and prompt files.
    first_response = mock_response("INVALID JSON")

    second_response = mock_response(
        json.dumps({
            "candidate_name": "John Doe"
        })
    )

    mock_client.chat.completions.create.side_effect = [
        first_response,
        second_response
    ]

    # Replace schema loading with a small test schema.
    from unittest.mock import mock_open

    original_read_text = api.Path.read_text

    def fake_read_text(path, *args, **kwargs):

        if path.name == "resume_extraction_v1.json":
            return json.dumps(schema)

        if path.name == "extract_resume_v1.md":
            return "Extract resume information."

        return original_read_text(path, *args, **kwargs)

    # Avoid changing Path globally for other tests.
    from unittest.mock import patch

    with patch.object(api.Path, "read_text", fake_read_text):

        result, usage = api.extract_resume(
            "Python developer",
            mock_client
        )

    assert result["candidate_name"] == "John Doe"
    assert mock_client.chat.completions.create.call_count == 2
    assert usage["total_tokens"] == 300


# 3. Empty file upload

def test_empty_file():

    response = client.post(
        "/analyze",
        data={
            "job_description": "Python developer required."
        },
        files={
            "resume_file": (
                "resume.txt",
                b"",
                "text/plain"
            )
        }
    )

    assert response.status_code == 400

    assert "empty" in response.json()["detail"].lower()


# 4. Unsupported file type

def test_wrong_file_type():

    response = client.post(
        "/analyze",
        data={
            "job_description": "Python developer required."
        },
        files={
            "resume_file": (
                "resume.docx",
                b"Sample content",
                "application/octet-stream"
            )
        }
    )

    assert response.status_code == 415

    assert "PDF and TXT" in response.json()["detail"]
