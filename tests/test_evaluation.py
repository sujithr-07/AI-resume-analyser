
import json
import re

from pathlib import Path


DATASET_PATH = Path(__file__).parent / "golden_set.json"


def normalize(skill):

    return re.sub(
        r"\s+",
        " ",
        skill.strip().lower()
    )


def calculate_metrics(expected, predicted):

    expected = {
        normalize(skill) for skill in expected
    }

    predicted = {
        normalize(skill) for skill in predicted
    }

    true_positive = len(expected & predicted)

    false_positive = len(predicted - expected)

    false_negative = len(expected - predicted)

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive else 0
    )

    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative else 0
    )

    accuracy = (
        true_positive / len(expected | predicted)
        if expected | predicted else 1
    )

    return {
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative
    }


def test_golden_dataset_exists():

    assert DATASET_PATH.exists()

    dataset = json.loads(
        DATASET_PATH.read_text(encoding="utf-8")
    )

    assert len(dataset) == 8

    for item in dataset:

        assert item["resume"]

        assert item["expected_skills"]


def test_metric_calculation():

    expected = [
        "Python",
        "SQL",
        "Django"
    ]

    predicted = [
        "Python",
        "SQL",
        "Flask"
    ]

    metrics = calculate_metrics(
        expected,
        predicted
    )

    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1

    assert round(metrics["precision"], 2) == 0.67
    assert round(metrics["recall"], 2) == 0.67


def calculate_average_score_difference(scores_run_1, scores_run_2):

    if len(scores_run_1) != len(scores_run_2):
        raise ValueError("Both runs must have the same number of scores.")

    if not scores_run_1:
        raise ValueError("Score lists cannot be empty.")

    differences = [
        abs(a - b)
        for a, b in zip(scores_run_1, scores_run_2)
    ]

    return sum(differences) / len(differences)
