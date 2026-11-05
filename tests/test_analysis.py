"""Step 8 analysis: the statistics on known data, the rates, and the --mock run end to end."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import analyse  # noqa: E402

from core import analysis as a  # noqa: E402
from core.scoring import MOCK_LABEL  # noqa: E402


def design(y_of) -> pd.DataFrame:
    """One model's 45 values: 5 categories x 3 scenarios x 3 levels, y = y_of(category, scenario, level)."""
    rows = []
    for c, cat in enumerate(a.ORDER["category"]):
        for s in range(3):
            for lvl_i, lvl in enumerate(a.LEVELS):
                rows.append({"scenario_id": f"{cat}{s}", "category": cat, "level": lvl, "y": y_of(c, s, lvl_i)})
    return pd.DataFrame(rows)


def test_anova_finds_a_level_effect_and_sums_of_squares_are_right():
    rng = np.random.default_rng(0)
    data = design(lambda c, s, lvl: lvl + rng.normal(0, 0.2))
    rows, fit, note = a.two_way_anova(data)
    level = next(r for r in rows if r["effect"] == "level")
    assert note == "" and level["p"] < 1e-6 and level["partial_eta2"] > 0.8
    assert (level["df"], level["df_resid"]) == (2, 30)
    means = data.groupby("level")["y"].mean()                      # balanced: SS = n * sum of squared deviations
    assert level["sum_sq"] == pytest.approx(15 * ((means - data["y"].mean()) ** 2).sum())
    checks = a.assumption_checks(data, fit)
    assert 0 <= checks["shapiro_p"] <= 1 and 0 <= checks["levene_p"] <= 1


def test_anova_without_variance_is_reported_not_crashed():
    rows, fit, note = a.two_way_anova(design(lambda c, s, lvl: 1.0))
    assert rows == [] and fit is None and "no variance" in note
    rows, _, note = a.two_way_anova(design(lambda c, s, lvl: float(lvl)))   # cells constant: residual 0
    assert "F not defined" in note and all(np.isnan(r["F"]) for r in rows)


def test_tukey_direction_and_rank_tests():
    rng = np.random.default_rng(1)
    data = design(lambda c, s, lvl: 0.1 * lvl + rng.normal(0, 0.02))
    pairs = {(r["from"], r["to"]): r for r in a.tukey_levels(data)}
    assert pairs[("minimal", "full")]["mean_diff"] == pytest.approx(0.2, abs=0.03)   # later minus earlier
    assert pairs[("minimal", "full")]["p_adj"] < 0.001
    friedman = next(r for r in a.nonparametric(data) if r["test"].startswith("Friedman"))
    assert friedman["effect_size"] == pytest.approx(1.0)           # every scenario rises at every step
    assert a.tukey_levels(design(lambda c, s, lvl: 1.0)) == []


def test_kappa():
    assert a.kappa([0, 0, 1, 1], [0, 1, 1, 1], (0.0, 1.0)) == pytest.approx(0.5)
    assert a.kappa([0, 0.5, 1], [0, 0.5, 1], a.SCALES["technical_accuracy"]) == pytest.approx(1.0)
    assert np.isnan(a.kappa([1, 1], [1, 1], (0.0, 1.0)))
    assert a.landis_koch(0.65) == "substantial" and a.landis_koch(-0.1) == "poor"



def test_mean_difference_finds_a_generous_rater():
    ids = [f"i{n}" for n in range(20)]
    strict = pd.DataFrame({"technical_accuracy": [0.0, 0.5] * 10, "root_cause_correctness": [0, 1] * 10,
                           "actionability": [1, 2] * 10}, index=ids)
    generous = strict.assign(actionability=strict["actionability"] + 1)     # one point higher on every item
    rows = {r["dimension"]: r for r in a.mean_difference(generous, strict, "g vs s")}
    assert rows["actionability"]["difference"] == pytest.approx(1.0) and rows["actionability"]["wilcoxon_p"] < .001
    assert rows["actionability"]["a_higher"] == 20 and rows["actionability"]["b_higher"] == 0
    assert rows["technical_accuracy"]["difference"] == 0 and rows["technical_accuracy"]["wilcoxon_p"] == 1.0

def test_kendall_w():
    same = pd.DataFrame([[1, 2, 3, 4, 5]] * 3)
    assert a.kendall_w(same)["W"] == pytest.approx(1.0)
    assert a.kendall_w(pd.DataFrame([[1, 2, 3], [3, 2, 1]]))["W"] == pytest.approx(0.0)


def test_median3_cells_and_rates():
    base = {"model_key": "gpt", "scenario_id": "SD01", "category": "schema_drift", "root_cause_type": "data",
            "level": "full", "refs_checked": 10, "hallucination_candidates": 0, "hallucination_auto": 0}
    scored = pd.DataFrame([
        {**base, "item_id": "x1", "technical_accuracy": 1.0, "root_cause_correctness": 0.0, "actionability": 3.0,
         "specificity": 0.8, "root_cause_asserted": 1, "hedges_root_cause": 0, "hallucinations_h": 1.0,
         "hallucination_candidates": 2, "hallucination_auto": 1},
        {**base, "item_id": "x2", "technical_accuracy": 0.5, "root_cause_correctness": 1.0, "actionability": 2.0,
         "specificity": 0.7, "root_cause_asserted": 1, "hedges_root_cause": 0, "hallucinations_h": 0.0},
        {**base, "item_id": "x3", "technical_accuracy": 0.5, "root_cause_correctness": 0.0, "actionability": 1.0,
         "specificity": 0.9, "root_cause_asserted": 0, "hedges_root_cause": 2, "hallucinations_h": 0.0},
    ])
    cell = a.median3_cells(scored).iloc[0]
    assert (cell["technical_accuracy"], cell["root_cause_correctness"], cell["actionability"],
            cell["specificity"]) == (0.5, 0.0, 2.0, 0.8)
    r = a.rates(scored).iloc[0]
    assert r["misdiagnosis_rate"] == pytest.approx(2 / 3)
    assert r["false_confidence_rate"] == pytest.approx(1 / 3) and r["wrong_asserted_share"] == pytest.approx(0.5)
    assert r["hallucination_answer_rate"] == pytest.approx(1 / 3)
    assert r["candidates_per_100_refs"] == pytest.approx(100 * 2 / 30)
    pending = a.rates(scored.assign(hallucinations_h=[np.nan, 0.0, 0.0])).iloc[0]
    assert np.isnan(pending["hallucination_answer_rate"]) and pending["candidate_answer_rate"] == pytest.approx(1 / 3)


def test_confirmed_counts_and_check_quality():
    review = [{"item_id": "a", "verdict": "H"}, {"item_id": "a", "verdict": "f"}, {"item_id": "b", "verdict": ""}]
    counts = a.confirmed_counts(review)
    assert counts["a"] == 1 and np.isnan(counts["b"])
    done = [{**r, "verdict": r["verdict"] or "H"} for r in review]
    recall = [{"item_id": "a", "checked": "yes", "missed_entities": "x; y"},
              {"item_id": "c", "checked": "yes", "missed_entities": ""}, {"item_id": "b", "checked": "", "missed_entities": ""}]
    q = a.check_quality(done, recall)
    assert q["precision"] == pytest.approx(2 / 3) and q["recall_read"] == 2
    assert q["recall"] == pytest.approx(1 / 3)                      # 1 found in a, 2 missed
    assert np.isnan(a.check_quality(review, recall)["precision"])   # review not complete


def test_real_run_refuses_mock_rows(tmp_path, monkeypatch):
    path = tmp_path / "scores.csv"
    path.write_text("rater_id,status,item_id,position,is_repeat,technical_accuracy,root_cause_correctness,"
                    "actionability,notes,scored_at\nresearcher_provisional,MOCK,SD01-01A,1,0,1,1,3,MOCK,\n")
    monkeypatch.setattr(analyse, "scores_path", lambda rater, mock=False: path)
    with pytest.raises(SystemExit):
        analyse.load_rater("researcher_provisional", {"researcher_provisional": []}, mock=False)


@pytest.mark.skipif(not (ROOT / "results" / "auto_metrics.csv").exists(), reason="run Steps 6-7 first")
def test_mock_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(analyse, "out_dirs", lambda mock: (tmp_path / "analysis", tmp_path / "figures"))
    res = analyse.run(mock=True)
    anova = res["tests"]["median3"]["anova"]
    assert len(anova) == 3 * 4 * 3 and anova["p"].notna().all()           # 3 models x 4 DVs x 3 effects
    assert len(res["cells"]["median3"]) == 135 and len(res["cells"]["experts"]) == 135
    for csv_path in (tmp_path / "analysis").glob("*.csv"):
        df = pd.read_csv(csv_path)
        assert (df["data_label"] == MOCK_LABEL).all(), csv_path.name   # every row says MOCK
    assert MOCK_LABEL in (tmp_path / "analysis" / "report.md").read_text()
    assert len(list((tmp_path / "figures").glob("*.png"))) == 4
    assert set(res["agreement"]["comparison"]) == {
        "expert_1 vs expert_2 (45 shared items)", "researcher vs expert_1 (90 items)",
        "researcher vs expert_2 (90 items)"}                                   # D30: no midpoint repeats
    assert res["cells"]["experts"]["technical_accuracy"].notna().all()         # all 135 cells expert-scored
    assert (tmp_path / "analysis" / "rates_experts.csv").exists()
    diff = res["rater_difference"]                                             # D34: generosity check
    assert len(diff) == 3 and (diff["n"] == 45).all() and diff["wilcoxon_p"].between(0, 1).all()
    assert (tmp_path / "analysis" / "rater_difference.csv").exists()


@pytest.mark.skipif(not (ROOT / "results" / "auto_metrics.csv").exists(), reason="run Steps 6-7 first")
def test_mock_run_without_researcher_uses_expert_scores(tmp_path, monkeypatch):
    """D30: with no researcher scores, the human-scored results and figures come from the experts."""
    monkeypatch.setattr(analyse, "out_dirs", lambda mock: (tmp_path / "analysis", tmp_path / "figures"))
    real = analyse.load_rater
    monkeypatch.setattr(analyse, "load_rater", lambda rater, assignments, mock:
                        (None, "not yet") if rater == analyse.RESEARCHER else real(rater, assignments, mock))
    res = analyse.run(mock=True)
    assert res["cells"]["median3"]["technical_accuracy"].isna().all()
    shown, unit = analyse.plot_cells(res["cells"], researcher_scored=False)
    assert unit == "experts" and shown["technical_accuracy"].notna().all() and shown["specificity"].notna().all()
    assert res["rates_experts"]["misdiagnosis_rate"].notna().any()
    assert len(list((tmp_path / "figures").glob("*.png"))) == 4


@pytest.mark.skipif(not (ROOT / "results" / "auto_metrics.csv").exists(), reason="run Steps 6-7 first")
@pytest.mark.parametrize("expert_1_rows", [0, 36])          # expert_1 missing, or 6 of 15 scenario groups done
def test_mock_run_with_one_or_a_partial_expert(tmp_path, monkeypatch, expert_1_rows):
    """D36: one expert's scores, or a partly scored file, are used as far as they go."""
    from core.scoring import read_scores, scores_path, write_scores
    monkeypatch.setattr(analyse, "out_dirs", lambda mock: (tmp_path / "analysis", tmp_path / "figures"))
    files = {"expert_2": scores_path("expert_2", mock=True)}
    if expert_1_rows:
        rows = sorted(read_scores(scores_path("expert_1", mock=True)), key=lambda r: int(r["position"]))
        files["expert_1"] = tmp_path / "expert_1.csv"
        write_scores(files["expert_1"], rows[:expert_1_rows])
    real = analyse.scores_path
    monkeypatch.setattr(analyse, "scores_path", lambda rater, mock=False:
                        files.get(rater, tmp_path / "missing.csv") if rater in analyse.EXPERTS else real(rater, mock))
    res = analyse.run(mock=True)
    cells = res["cells"]["experts"]
    scored = cells["technical_accuracy"].notna().sum()
    assert scored == 90 + (expert_1_rows // 2 if expert_1_rows else 0)     # half of a group is expert_1's own
    anova = res["tests"]["experts"]["anova"]
    level = anova[anova["effect"] == "level"]
    assert len(level) == 3 * 4 and level["F"].notna().any()                # 3 models x 4 DVs: still tested
    if not expert_1_rows:
        assert anova["note"].str.contains("main effects only").any()
        assert res["tests"]["experts"]["nonparametric"]["note"].fillna("").str.contains("three levels").any()
        assert "rater_difference" not in res
    else:
        assert (res["rater_difference"]["n"] == expert_1_rows // 2).all()
    assert analyse.EXPERT_LABEL.startswith(f"Expert scores (one repetition per cell; {scored} of 135")
    assert res["rates_experts"]["misdiagnosis_rate"].notna().all()
