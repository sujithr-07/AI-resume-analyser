
import json
import re
from pathlib import Path

from api import (
    get_client,
    extract_resume,
    match_once,
    make_live_caller
)

ROOT = Path(__file__).resolve().parent.parent

DATASET = ROOT / "tests" / "golden_set.json"

ORIGINAL_PROMPT = (
    ROOT / "prompts" / "extract_resume_original.md"
)

IMPROVED_PROMPT = (
    ROOT / "prompts" / "extract_resume_v1.md"
)

JOB_DESCRIPTION = """
We are looking for a technical professional with
relevant programming, software development,
database, cloud, and problem-solving skills.

Candidates should demonstrate experience with
the technologies and tools mentioned in their resumes.
"""


def normalize(skill):
    return re.sub(r"\s+", " ", skill.strip().lower())


def calculate_metrics(expected, predicted):

    expected = {normalize(s) for s in expected}
    predicted = {normalize(s) for s in predicted}

    tp = len(expected & predicted)
    fp = len(predicted - expected)
    fn = len(expected - predicted)

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0

    accuracy = (
        tp / (tp + fp + fn)
        if tp + fp + fn else 1
    )

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy
    }


def get_skills(candidate):
    # Change this key if your JSON schema uses
    # a different field name for extracted skills.
    return candidate.get("skills", [])


def evaluate_prompt(client, prompt_path, dataset):

    total = {
        "tp": 0,
        "fp": 0,
        "fn": 0
    }

    print(f"\nRunning prompt: {prompt_path.name}")

    for item in dataset:

        candidate, usage = extract_resume(
            item["resume"],
            client,
            prompt_path=prompt_path
        )

        predicted = get_skills(candidate)

        metrics = calculate_metrics(
            item["expected_skills"],
            predicted
        )

        total["tp"] += metrics["tp"]
        total["fp"] += metrics["fp"]
        total["fn"] += metrics["fn"]

        print(
            f"Resume {item['id']}: "
            f"Precision={metrics['precision']:.2f}, "
            f"Recall={metrics['recall']:.2f}"
        )

    tp = total["tp"]
    fp = total["fp"]
    fn = total["fn"]

    return {
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
        "accuracy": (
            tp / (tp + fp + fn)
            if tp + fp + fn else 1
        ),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn
    }


def evaluate_score_consistency(client, dataset):

    call = make_live_caller(client)

    prompt = (
        ROOT / "prompts" / "match_v1.md"
    ).read_text(encoding="utf-8")

    differences = []

    print("\nChecking score consistency...")

    for item in dataset:

        candidate, _ = extract_resume(
            item["resume"],
            client,
            prompt_path=IMPROVED_PROMPT
        )

        candidate_json = json.dumps(
            candidate,
            ensure_ascii=False
        )

        result1 = match_once(
            call,
            prompt,
            candidate_json,
            JOB_DESCRIPTION
        )

        result2 = match_once(
            call,
            prompt,
            candidate_json,
            JOB_DESCRIPTION
        )

        score1 = result1["score"]
        score2 = result2["score"]

        difference = abs(score1 - score2)

        differences.append(difference)

        print(
            f"Resume {item['id']}: "
            f"Run 1={score1}, "
            f"Run 2={score2}, "
            f"Difference={difference}"
        )

    return sum(differences) / len(differences)


def main():

    if not ORIGINAL_PROMPT.exists():
        raise FileNotFoundError(
            "Original prompt not found: "
            f"{ORIGINAL_PROMPT}"
        )

    if not IMPROVED_PROMPT.exists():
        raise FileNotFoundError(
            "Improved prompt not found: "
            f"{IMPROVED_PROMPT}"
        )

    dataset = json.loads(
        DATASET.read_text(encoding="utf-8")
    )

    if len(dataset) != 8:
        raise ValueError(
            "Golden dataset must contain exactly 8 resumes."
        )

    client = get_client()

    # BEFORE prompt improvement
    before = evaluate_prompt(
        client,
        ORIGINAL_PROMPT,
        dataset
    )

    # AFTER prompt improvement
    after = evaluate_prompt(
        client,
        IMPROVED_PROMPT,
        dataset
    )

    # Two matching runs for each resume
    score_difference = evaluate_score_consistency(
        client,
        dataset
    )

    report = {
        "before_prompt_improvement": before,
        "after_prompt_improvement": after,
        "average_score_difference": score_difference
    }

    output_path = ROOT / "tests" / "evaluation_report.json"

    output_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8"
    )

    print("\n========== EVALUATION REPORT ==========")

    print(
        f"Before Precision: {before['precision']:.2f}"
    )

    print(
        f"After Precision:  {after['precision']:.2f}"
    )

    print(
        f"Before Recall:    {before['recall']:.2f}"
    )

    print(
        f"After Recall:     {after['recall']:.2f}"
    )

    print(
        f"Before Accuracy:  {before['accuracy']:.2f}"
    )

    print(
        f"After Accuracy:   {after['accuracy']:.2f}"
    )

    print(
        f"Average Score Difference: "
        f"{score_difference:.2f}"
    )

    print("\nReport saved to:", output_path)


if __name__ == "__main__":
    main()
