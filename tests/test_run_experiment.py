"""The runner's plan, resume and consistency logic (no API calls)."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment as rx  # noqa: E402

from core import config  # noqa: E402


def full_plan():
    return rx.plan_calls(rx.all_scenario_ids(), list(config.MODELS))


def test_plan_is_the_full_design():
    calls = full_plan()
    assert len(calls) == 405 == len({c["run_id"] for c in calls})
    cells = Counter((c["scenario_id"], c["level"], c["model_key"]) for c in calls)
    assert len(cells) == 15 * 3 * 3 and set(cells.values()) == {3}


def test_plan_order_is_seeded_and_mixed():
    a, b = full_plan(), full_plan()
    assert [c["run_id"] for c in a] == [c["run_id"] for c in b]
    first_20 = a[:20]
    assert len({c["level"] for c in first_20}) == 3 and len({c["scenario_id"] for c in first_20}) > 5


def test_same_prompt_for_every_model_and_rep():
    by_cell = {}
    for c in full_plan():
        by_cell.setdefault((c["scenario_id"], c["level"]), set()).add(c["prompt_sha256"])
    assert all(len(shas) == 1 for shas in by_cell.values())


def test_llama_reps_get_different_seeds():
    assert len({rx.llama_seed(r) for r in rx.REPS}) == len(rx.REPS)
    assert rx.llama_seed(1) == config.GLOBAL_SEED


def test_consistency_check_catches_changed_prompt_or_model():
    call = full_plan()[0]
    ok = {"prompt_sha256": call["prompt_sha256"],
          "model_requested": config.MODELS[call["model_key"]]["model_id"]}
    assert rx.check_consistency([call], {call["run_id"]: ok}) == []
    assert rx.check_consistency([call], {call["run_id"]: {**ok, "prompt_sha256": "x"}})
    assert rx.check_consistency([call], {call["run_id"]: {**ok, "model_requested": "other"}})


def test_half_written_line_is_skipped(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_text(json.dumps({"run_id": "A"}) + "\n" + '{"run_id": "B", "te')
    assert [r["run_id"] for r in rx.load_records(path)] == ["A"]


def test_heading_check_accepts_common_formats():
    for fmt in ("### {}", "**{}**", "{}:", "1. {}", "## {}"):
        text = "\n".join(fmt.format(h) + "\nbody" for h in ("Root cause", "Fix", "Verification", "Assumptions"))
        assert rx.has_all_headings(text), fmt
    assert not rx.has_all_headings("### Root cause\nx\n### Fix\ny")
