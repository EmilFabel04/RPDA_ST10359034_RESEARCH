"""Shared scoring definitions (Step 6): raters, rubric, score-file format and validation.

Every score file has the same columns, whoever produced it:
    results/scores_researcher_provisional.csv   researcher, all 405       status PROVISIONAL
    results/scores_expert_1.csv / _2.csv        experts, 90 each (D30)     status EXPERT
    results/mock/scores_<rater>.MOCK.csv        random placeholders        status MOCK

Score files hold blinded item ids only (e.g. "RC02-05A"); which model and context
level an item came from is in results/blinding_key.json, joined in the analysis.
"""
from __future__ import annotations

import csv
from pathlib import Path

from core import config

RESEARCHER = "researcher_provisional"
EXPERTS = ("expert_1", "expert_2")
RATERS = (RESEARCHER, *EXPERTS)
RATER_LABELS = {RESEARCHER: "Researcher (PROVISIONAL)", "expert_1": "Evaluator 1", "expert_2": "Evaluator 2"}
STATUS = {RESEARCHER: "PROVISIONAL", "expert_1": "EXPERT", "expert_2": "EXPERT"}

PROVISIONAL_LABEL = "Provisional researcher scores — expert evaluation pending"
MOCK_LABEL = "MOCK DATA — random placeholder scores, not real ratings"

COLUMNS = ["rater_id", "status", "item_id", "position", "is_repeat", "technical_accuracy",
           "root_cause_correctness", "actionability", "notes", "scored_at"]
VALID = {"technical_accuracy": ("0", "0.5", "1"),
         "root_cause_correctness": ("0", "1"),
         "actionability": ("1", "2", "3")}

# D30: each expert scores 90 of the 135 expert-set answers: 45 shared by both (agreement) + 45 of their own,
# grouped by scenario, no midpoint repeats. Every one of the 135 gets at least one expert score.
N_SHARED = 45
N_PER_EXPERT = 90

# Rubric wording as given to the evaluators (Evaluator Pack, final) and proposal Appendix A
RUBRIC = {
    "general": [
        "Score what the suggestion actually says, as if you were the on-call engineer receiving it. "
        "Use the reference fix as a guide, not a strict answer key.",
    ],
    "dimensions": [
        {"key": "technical_accuracy", "name": "Technical accuracy", "scale": "0 / 0.5 / 1",
         "question": "Would the suggested fix technically work for this failure? “Partly right” (0.5) means "
                     "on the right track but incomplete, or it fixes the failing test but causes a new problem."},
        {"key": "root_cause_correctness", "name": "Root cause correctness", "scale": "0 / 1",
         "question": "Does the suggestion correctly identify the underlying cause of the failure?"},
        {"key": "actionability", "name": "Actionability", "scale": "1 / 2 / 3",
         "question": "Can a competent engineer implement this without needing further research?"},
    ],
    "anchor_failure": "Example failure (not one of the study scenarios): the accepted_values test on the status "
                      "column of stg_orders failed because the source started sending a new order status, "
                      "‘returned’, that is not in the accepted list.",
    "anchors": [
        {"score": "1", "example": "“Check the upstream source data for unexpected values and consider adding "
                                  "more data quality tests.”",
         "why": "Generic advice with no specific model, column or code reference."},
        {"score": "2", "example": "“The status column in stg_orders is receiving a new value that isn’t in the "
                                  "accepted list. Update the test or the model to handle it and rerun the tests.”",
         "why": "Points to the right column and model, but gives no code, no downstream impact and no way to "
                "verify the fix."},
        {"score": "3", "example": "“Root cause: raw_orders now contains status = 'returned', which stg_orders "
                                  "passes through unchanged, so accepted_values on stg_orders.status fails. Fix: if "
                                  "returns are a valid business state, add 'returned' to the accepted values for "
                                  "status in models/staging/schema.yml (values: ['placed', 'shipped', 'completed', "
                                  "'cancelled', 'returned']) and check that fct_orders handles returned orders "
                                  "correctly in revenue totals. Verify: dbt build --select stg_orders+”",
         "why": "Identifies the root cause, gives the exact fix location with code, names the affected downstream "
                "models and gives a verification step."},
    ],
    "rules": [
        "Between two anchors: a 3 needs all four elements — the root cause, the exact fix location with code, "
        "the affected downstream models, and a verification step. A suggestion that names the right model or "
        "column but is missing any of these scores 2. One that names no specific model, column or code scores 1.",
        "Use the notes field for anything unusual. If a suggestion mentions a model or column that doesn’t exist "
        "in the scenario, note it. If the fix depends on it, score technical accuracy as the fix would actually "
        "behave: a change to a model that doesn’t exist can’t work as written.",
        "Each model was also asked to list the assumptions it made. Don’t score that list separately; use it "
        "only to understand the rest of the suggestion.",
        "If you’re unsure between two scores, pick one and add a note. Unclear cases are discussed afterwards. "
        "If you still disagree after discussion, both scores are kept and the disagreement is reported.",
    ],
}


def scores_path(rater_id: str, mock: bool = False) -> Path:
    if mock:
        return config.MOCK_DIR / f"scores_{rater_id}.MOCK.csv"
    return config.RESULTS_DIR / f"scores_{rater_id}.csv"


def row_problems(row: dict) -> list[str]:
    """Why a score row is invalid (empty list = valid)."""
    problems = [f"missing column {c}" for c in COLUMNS if c not in row]
    if problems:
        return problems
    for col, allowed in VALID.items():
        if str(row[col]) not in allowed:
            problems.append(f"{row['item_id']}: {col}={row[col]!r} not in {allowed}")
    if str(row["is_repeat"]) not in ("0", "1"):
        problems.append(f"{row['item_id']}: is_repeat must be 0 or 1")
    return problems


def read_scores(path: Path) -> list[dict]:
    """All rows of a score file, validated; raises ValueError on any invalid row."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    problems = [p for r in rows for p in row_problems(r)]
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems[:5]))
    return rows


def write_scores(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({c: r[c] for c in COLUMNS} for r in rows)


def append_score(path: Path, row: dict) -> None:
    """Append one row immediately (so a score is never lost), writing the header if new."""
    problems = row_problems(row)
    if problems:
        raise ValueError("; ".join(problems))
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow({c: row[c] for c in COLUMNS})
