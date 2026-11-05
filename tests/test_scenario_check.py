"""Scenario check page (O1): all 15 scenarios, no LLM answers, and the summary lists what was flagged."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import make_scenario_check as sc  # noqa: E402


def test_page_has_all_scenarios_and_no_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "PAGE_PATH", tmp_path / "scenario_check.html")
    html = sc.build().read_text()
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
                      .group(1).replace("<\\/", "</"))
    assert [it["scenario_id"] for it in data["items"]] == sc.scenario_order() and len(data["items"]) == 15
    assert set(data["scenarios"]) == set(sc.scenario_order())
    assert all("text" not in it and "label" not in it for it in data["items"])      # no LLM answers, no labels
    assert [q["key"] for q in data["questions"]] == ["realistic", "fix_correct"]


def test_summary_lists_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sc.config, "SCORING_DIR", tmp_path)
    monkeypatch.setattr(sc.config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "scenario_check_expert_1.csv").write_text(
        "rater_id,scenario_id,position,realistic,fix_correct,comments,checked_at\n"
        "expert_1,SD01,1,Yes,Yes,,\nexpert_1,SD02,2,No,Yes,too neat,\n")
    sc.summary()
    out = capsys.readouterr().out
    assert "2 of 15 checked, 1 flagged" in out and "SD02: realistic=No" in out and "not returned yet" in out
