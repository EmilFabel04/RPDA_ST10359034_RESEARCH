"""Blinding, rater assignments, scoring pages and score files (Step 6)."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_scoring as ps  # noqa: E402
from run_experiment import OUTPUTS, load_records  # noqa: E402

from core import config  # noqa: E402
from core.scoring import (EXPERTS, N_PER_EXPERT, N_SHARED, RESEARCHER, append_score, read_scores,  # noqa: E402
                          row_problems, scores_path)

RECORDS = load_records(OUTPUTS)
KEY = ps.blind(RECORDS, config.GLOBAL_SEED)


def test_blinding_covers_every_answer_once():
    assert len(KEY) == 405 == len({v["run_id"] for v in KEY.values()})
    assert all(re.fullmatch(r"[A-Z]{2}\d{2}-0[1-9][ABC]", i) for i in KEY)


def test_each_group_is_one_condition_with_three_models():
    groups = {}
    for item_id, v in KEY.items():
        groups.setdefault(item_id[:-1], []).append(v)
    for members in groups.values():
        assert {m["model_key"] for m in members} == set(config.MODELS)
        assert len({(m["level"], m["rep"]) for m in members}) == 1


def test_labels_and_group_numbers_do_not_reveal_model_or_level():
    # every model appears under every label, and group 01 is not always the same level
    assert len({(v["model_key"], v["label"]) for v in KEY.values()}) == 9
    assert len({v["level"] for v in KEY.values() if v["group"] == 1}) == 3


def test_expert_set_is_one_rep_per_scenario_level_model():
    expert = [v for v in KEY.values() if v["expert_set"]]
    assert len(expert) == 135
    assert set(Counter((v["scenario_id"], v["level"], v["model_key"]) for v in expert).values()) == {1}


def test_blinding_is_deterministic_and_matches_saved_key():
    assert ps.blind(RECORDS, config.GLOBAL_SEED) == KEY
    if ps.KEY_PATH.exists():
        assert json.loads(ps.KEY_PATH.read_text())["items"] == KEY


def test_rater_orders():
    ids = list(KEY)
    researcher = ps.rater_order(ids, RESEARCHER, config.GLOBAL_SEED)
    assert sorted(o["item_id"] for o in researcher) == sorted(ids) and not any(o["is_repeat"] for o in researcher)


def test_expert_split_is_balanced_and_grouped():
    orders = ps.expert_orders(KEY, config.GLOBAL_SEED)
    expert_set = {i for i, v in KEY.items() if v["expert_set"]}
    shared = [{o["item_id"] for o in orders[e] if o["shared"]} for e in EXPERTS]
    own = [{o["item_id"] for o in orders[e] if not o["shared"]} for e in EXPERTS]
    assert shared[0] == shared[1] and len(shared[0]) == N_SHARED
    assert not own[0] & own[1] and len(own[0]) == len(own[1]) == N_SHARED
    assert shared[0] | own[0] | own[1] == expert_set                       # all 135 get an expert score
    for part in (shared[0], own[0], own[1]):                               # 15 per model, 15 per level,
        assert set(Counter(KEY[i]["model_key"] for i in part).values()) == {15}
        assert set(Counter(KEY[i]["level"] for i in part).values()) == {15}
        assert set(Counter(KEY[i]["scenario_id"] for i in part).values()) == {3}   # 1 per scenario x level
        assert set(Counter((KEY[i]["scenario_id"], KEY[i]["model_key"]) for i in part).values()) == {1}
    for e in EXPERTS:
        order = orders[e]
        assert len(order) == N_PER_EXPERT and [o["position"] for o in order] == list(range(1, N_PER_EXPERT + 1))
        runs = [KEY[o["item_id"]]["scenario_id"] for o in order]
        blocks = [s for n, s in enumerate(runs) if n == 0 or s != runs[n - 1]]
        assert len(blocks) == 15 and len(set(blocks)) == 15                # grouped: each scenario once, 6 in a row
        assert not any(o["is_repeat"] for o in order)
    assert [o["item_id"] for o in orders["expert_1"]] != [o["item_id"] for o in orders["expert_2"]]


@pytest.mark.skipif(not ps.PAGES_DIR.exists(), reason="run prepare_scoring.py first")
def test_pages_hide_model_and_level():
    for page in ps.PAGES_DIR.glob("*.html"):
        html = page.read_text()
        data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
                          .group(1).replace("<\\/", "</"))
        assert not any(k in item for item in data["items"] for k in ("run_id", "model_key", "level", "rep"))
        assert not re.search(r"gpt-5|claude-sonnet|llama3|\b(SD|NR|RC|RI|FV)\d\d-(minimal|partial|full)-", html)


def test_score_file_validation(tmp_path):
    good = {"rater_id": "expert_1", "status": "EXPERT", "item_id": "SD01-01A", "position": 1, "is_repeat": 0,
            "technical_accuracy": "0.5", "root_cause_correctness": "1", "actionability": "3",
            "notes": 'a "quoted", note', "scored_at": ""}
    assert row_problems(good) == []
    assert row_problems({**good, "technical_accuracy": "0.7"}) and row_problems({**good, "actionability": "4"})
    path = tmp_path / "s.csv"
    append_score(path, good)
    assert read_scores(path)[0]["notes"] == 'a "quoted", note'
    with pytest.raises(ValueError):
        append_score(path, {**good, "root_cause_correctness": "0.5"})


def test_mock_files_are_separate_and_labelled():
    assert scores_path("expert_1", mock=True).parent == config.MOCK_DIR
    assert scores_path("expert_1").parent == config.RESULTS_DIR
    for rater in (RESEARCHER, *EXPERTS):
        path = scores_path(rater, mock=True)
        if path.exists():
            rows = read_scores(path)
            assert {r["status"] for r in rows} == {"MOCK"} and ".MOCK." in path.name
