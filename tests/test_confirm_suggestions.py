"""AI-assisted hallucination review: accepting or changing a suggestion is saved, with an audit note."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import confirm_suggestions as cs  # noqa: E402


def write(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


def answers(monkeypatch, *typed):
    it = iter(typed)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def test_flags_accept_change_and_resume(tmp_path, monkeypatch):
    base = {"kind": "name", "section": "fix", "context": "...", "reviewer_note": ""}
    review = write(tmp_path / "review.csv", [{"item_id": "A", "entity": "x", **base, "verdict": ""},
                                             {"item_id": "A", "entity": "y", **base, "verdict": ""},
                                             {"item_id": "B", "entity": "z", **base, "verdict": ""}])
    sugg = write(tmp_path / "sugg.csv", [{"item_id": i, "entity": e, "suggested_verdict": "H", "reason": "r"}
                                         for i, e in (("A", "x"), ("A", "y"), ("B", "z"))])
    monkeypatch.setattr(cs, "REVIEW_PATH", review)
    monkeypatch.setattr(cs, "SUGGESTIONS", sugg)
    answers(monkeypatch, "", "c", "q")                      # accept, change, quit before the third
    cs.review_flags()
    rows = list(csv.DictReader(review.open()))
    assert [r["verdict"] for r in rows] == ["H", "C", ""]
    assert rows[0]["reviewer_note"] == "suggested H, accepted"
    assert rows[1]["reviewer_note"] == "suggested H, changed to C"
    answers(monkeypatch, "f")                                # resume: only the third is asked
    cs.review_flags()
    assert [r["verdict"] for r in csv.DictReader(review.open())] == ["H", "C", "F"]


def test_recall_accept_none_and_typed(tmp_path, monkeypatch):
    recall = write(tmp_path / "recall.csv", [{"item_id": i, "checked": "", "missed_entities": "", "reviewer_note": ""}
                                             for i in ("A", "B", "C")])
    sugg = write(tmp_path / "rsugg.csv", [{"item_id": "A", "suggested_missed": "foo", "reason": "r"},
                                          {"item_id": "B", "suggested_missed": "", "reason": "r"},
                                          {"item_id": "C", "suggested_missed": "bar", "reason": "r"}])
    review = write(tmp_path / "review.csv", [{"item_id": "A", "entity": "x", "kind": "", "section": "",
                                              "context": "", "verdict": "H", "reviewer_note": ""}])
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"items": {i: {"run_id": f"run-{i}"} for i in "ABC"}}))
    monkeypatch.setattr(cs, "RECALL_PATH", recall)
    monkeypatch.setattr(cs, "RECALL_SUGGESTIONS", sugg)
    monkeypatch.setattr(cs, "REVIEW_PATH", review)
    monkeypatch.setattr(cs, "KEY_PATH", key)
    monkeypatch.setattr(cs, "load_records", lambda path: [{"run_id": f"run-{i}", "text": "answer"} for i in "ABC"])
    answers(monkeypatch, "", "-", "baz; qux")
    cs.review_recall()
    rows = list(csv.DictReader(recall.open()))
    assert [r["checked"] for r in rows] == ["yes"] * 3
    assert [r["missed_entities"] for r in rows] == ["foo", "", "baz; qux"]
    assert rows[1]["reviewer_note"] == "suggested nothing, accepted"
    assert rows[2]["reviewer_note"] == "suggested bar, changed to baz; qux"
