"""Step 8 statistics: pure functions on pandas tables (no file reading or writing).

Unit of analysis (D29): one value per model x scenario x context level.
  median3   median of the 3 repetitions (researcher scores; automated specificity)
  experts   the one repetition both experts scored, mean of the two experts
Per model that is 45 values per dependent variable: 5 categories x 3 scenarios x 3 levels,
i.e. 3 values in each of the 15 level x category cells.
"""
from __future__ import annotations

import random
import re
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from sklearn.metrics import cohen_kappa_score
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multitest import multipletests

from core.scenario_defs import CATEGORIES

LEVELS = ("minimal", "partial", "full")
MODELS = ("gpt", "claude", "llama")
HUMAN_DVS = ("technical_accuracy", "root_cause_correctness", "actionability")
DVS = (*HUMAN_DVS, "specificity")
DV_NAMES = {"technical_accuracy": "Technical accuracy (0-1)", "root_cause_correctness": "Root cause correct (0/1)",
            "actionability": "Actionability (1-3)", "specificity": "Specificity (cosine)"}
SCALES = {"technical_accuracy": (0.0, 0.5, 1.0), "root_cause_correctness": (0.0, 1.0),
          "actionability": (1.0, 2.0, 3.0)}
KEYS = ["model_key", "scenario_id", "category", "root_cause_type", "level"]
EFFECTS = {"C(level)": "level", "C(category)": "category", "C(level):C(category)": "level x category"}
ORDER = {"model_key": MODELS, "level": LEVELS, "category": tuple(CATEGORIES), "dv": DVS}


def ordered(df: pd.DataFrame) -> pd.DataFrame:
    """Sort rows by model, dv, level and category in design order (not alphabetically)."""
    cols = [c for c in ("model_key", "dv", "level", "category") if c in df.columns]
    rank = {c: df[c].map({v: i for i, v in enumerate(ORDER[c])}).fillna(len(ORDER[c])) for c in cols}
    return df.assign(**{f"_{c}": r for c, r in rank.items()}).sort_values(
        [f"_{c}" for c in cols], kind="stable").drop(columns=[f"_{c}" for c in cols]).reset_index(drop=True)


# ---------------------------------------------------------------- building the tables
def answers_frame(key_items: dict, auto: pd.DataFrame) -> pd.DataFrame:
    """One row per answer: design factors and automated metrics, plus whether the experts score it."""
    key = pd.DataFrame([{"item_id": k, "expert_set": bool(v["expert_set"])} for k, v in key_items.items()])
    return auto.merge(key, on="item_id", validate="1:1")


def scores_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    return df.astype({**{dv: float for dv in HUMAN_DVS}, "is_repeat": int, "position": int})


def first_scores(scores: pd.DataFrame) -> pd.DataFrame:
    """Each item's first score (the midpoint repeats are only for the consistency check)."""
    return scores[scores["is_repeat"] == 0].set_index("item_id")[list(HUMAN_DVS)]


def with_scores(answers: pd.DataFrame, researcher: pd.DataFrame | None) -> pd.DataFrame:
    """Answers with the researcher's per-answer scores joined (NaN when there are none yet)."""
    if researcher is None:
        return answers.assign(**{dv: np.nan for dv in HUMAN_DVS})
    return answers.join(first_scores(researcher), on="item_id")


def median3_cells(scored: pd.DataFrame) -> pd.DataFrame:
    """Median of the 3 repetitions per model x scenario x level (the proposal's unit of analysis)."""
    cells = scored.groupby(KEYS, observed=True)[list(DVS)].median().reset_index()
    return ordered(cells)


def with_expert_scores(answers: pd.DataFrame, experts: list[pd.DataFrame]) -> pd.DataFrame:
    """The 135 expert-set answers with the experts' scores: the mean of both for the 45 shared answers,
    the one expert's score for the other 90 (D30). Disagreements are kept, not resolved (D9), so a
    mean of 0 and 1 gives 0.5."""
    mean = pd.concat([first_scores(e) for e in experts]).groupby(level=0).mean()
    return answers[answers["expert_set"]].join(mean, on="item_id")


def expert_cells(answers: pd.DataFrame, experts: list[pd.DataFrame]) -> pd.DataFrame:
    """One value per model x scenario x level from the experts (one repetition per cell)."""
    return ordered(with_expert_scores(answers, experts)[KEYS + list(DVS)].reset_index(drop=True))


def describe(cells: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """n, mean, SD, median and quartiles of every DV per model and grouping."""
    long = cells.melt(id_vars=KEYS, value_vars=list(DVS), var_name="dv").dropna(subset=["value"])
    out = (long.groupby(["model_key", "dv", *by], observed=True)["value"]
           .agg(n="count", mean="mean", sd="std", median="median",
                q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75)).reset_index())
    return ordered(out)


# ---------------------------------------------------------------- ANOVA and follow-ups
def model_data(cells: pd.DataFrame, model: str, dv: str) -> pd.DataFrame:
    """One model's 45 values of one DV, as columns scenario_id, level, category, y."""
    data = cells.loc[cells["model_key"] == model, ["scenario_id", "level", "category", dv]].dropna()
    return data.rename(columns={dv: "y"}).astype({"level": str, "category": str}).reset_index(drop=True)


def two_way_anova(data: pd.DataFrame) -> tuple[list[dict], object | None, str]:
    """Type II two-way ANOVA  y ~ level * category  (balanced, so Type I/II/III agree; Type II also
    suits the unbalanced data of partly scored expert sets). When a level x category cell has no
    value the interaction cannot be estimated, so only the main effects are fitted (D36).
    Returns one row per effect, the fitted model, and a note when a test is not defined."""
    if data["y"].nunique() < 2:
        return [], None, "no variance: every value is the same"
    empty = data["level"].nunique() * data["category"].nunique() - data.groupby(["level", "category"]).ngroups
    formula = "y ~ C(level) * C(category)" if empty == 0 else "y ~ C(level) + C(category)"
    fit = smf.ols(formula, data=data).fit()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # F is undefined when residual SS is 0
        table = anova_lm(fit, typ=2)
    ss_res, df_res = table.loc["Residual", "sum_sq"], int(table.loc["Residual", "df"])
    no_resid = ss_res < 1e-12
    rows = []
    for term, effect in EFFECTS.items():
        if term not in table.index:           # interaction not fitted
            rows.append({"effect": effect, "df": 0, "df_resid": df_res, "sum_sq": np.nan, "F": np.nan,
                         "p": np.nan, "partial_eta2": np.nan})
            continue
        ss = float(table.loc[term, "sum_sq"])
        rows.append({"effect": effect, "df": int(table.loc[term, "df"]), "df_resid": df_res, "sum_sq": ss,
                     "F": np.nan if no_resid else float(table.loc[term, "F"]),
                     "p": np.nan if no_resid else float(table.loc[term, "PR(>F)"]),
                     "partial_eta2": ss / (ss + ss_res) if ss + ss_res > 0 else np.nan})
    notes = (["no variance within cells: F not defined"] if no_resid else []) + \
        ([f"interaction not estimable ({empty} empty level x category cells): main effects only"] if empty else [])
    return rows, fit, "; ".join(notes)


def assumption_checks(data: pd.DataFrame, fit) -> dict:
    """Shapiro-Wilk on the residuals (normality) and Brown-Forsythe Levene over the 15 cells
    (equal variances). With 3 values per cell both have little power; read with the plots."""
    out = {"shapiro_W": np.nan, "shapiro_p": np.nan, "levene_W": np.nan, "levene_p": np.nan}
    if fit is not None and np.ptp(fit.resid) > 1e-12:
        out["shapiro_W"], out["shapiro_p"] = stats.shapiro(fit.resid)
    groups = [g["y"].to_numpy() for _, g in data.groupby(["level", "category"])]
    if any(np.ptp(g) > 0 for g in groups):
        out["levene_W"], out["levene_p"] = stats.levene(*groups, center="median")
    return {k: float(v) for k, v in out.items()}


def tukey_levels(data: pd.DataFrame) -> list[dict]:
    """Tukey HSD between the three context levels (difference = later level minus earlier)."""
    groups = [data.loc[data["level"] == lvl, "y"].to_numpy(float) for lvl in LEVELS]
    if any(len(g) < 2 for g in groups) or all(np.ptp(g) == 0 for g in groups):
        return []
    res = stats.tukey_hsd(*groups)
    ci = res.confidence_interval(0.95)
    rows = []
    for i, j in ((0, 1), (1, 2), (0, 2)):
        rows.append({"from": LEVELS[i], "to": LEVELS[j], "n_per_level": len(groups[i]),
                     "mean_diff": float(res.statistic[j, i]), "ci_low": float(ci.low[j, i]),
                     "ci_high": float(ci.high[j, i]), "p_adj": float(res.pvalue[j, i])})
    return rows


def nonparametric(data: pd.DataFrame) -> list[dict]:
    """Rank-based checks of the ANOVA: Kruskal-Wallis for level and for category, and Friedman for
    level with scenarios as blocks (the same 15 scenarios appear at every level, which the ANOVA ignores)."""
    rows = []
    for factor in ("level", "category"):
        groups = [g["y"].to_numpy() for _, g in data.groupby(factor)]
        n = sum(len(g) for g in groups)
        try:
            h, p = stats.kruskal(*groups)
            rows.append({"test": "Kruskal-Wallis", "factor": factor, "statistic": h, "p": p,
                         "effect_size": h / (n - 1), "effect_measure": "epsilon2", "note": ""})
        except ValueError as exc:          # all values identical
            rows.append({"test": "Kruskal-Wallis", "factor": factor, "note": str(exc)})
    wide = data.pivot(index="scenario_id", columns="level", values="y").dropna()
    if len(wide) >= 2 and np.ptp(wide.to_numpy()) > 0 and all(lvl in wide for lvl in LEVELS):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            chi2, p = stats.friedmanchisquare(*(wide[lvl] for lvl in LEVELS))
        w = chi2 / (len(wide) * (len(LEVELS) - 1))
        rows.append({"test": "Friedman (blocks: scenario)", "factor": "level", "statistic": chi2, "p": p,
                     "effect_size": w, "effect_measure": "Kendall W", "note": ""})
    else:
        complete = len(wide) if all(lvl in wide for lvl in LEVELS) else 0
        rows.append({"test": "Friedman (blocks: scenario)", "factor": "level",
                     "note": f"only {complete} scenarios scored at all three levels" if complete < 2 else "no variance"})
    return rows


def holm(p: pd.Series) -> pd.Series:
    """Holm-adjusted p-values (NaN stays NaN)."""
    out = pd.Series(np.nan, index=p.index)
    ok = p.notna()
    if ok.any():
        out[ok] = multipletests(p[ok], method="holm")[1]
    return out


# ---------------------------------------------------------------- RQ3: are category patterns consistent?
def kendall_w(table: pd.DataFrame) -> dict:
    """Kendall's W for m raters (rows) ranking n items (columns), average ranks for ties, tie-corrected.
    Here: do the three models rank the five failure categories in the same order?"""
    m, n = table.shape
    ranks = table.rank(axis=1)
    r = ranks.sum(axis=0)
    s = float(((r - r.mean()) ** 2).sum())
    ties = sum(float((c ** 3 - c).sum()) for c in (row.value_counts().to_numpy() for _, row in table.iterrows()))
    denom = m ** 2 * (n ** 3 - n) - m * ties
    if denom <= 0:
        return {"W": np.nan, "chi2": np.nan, "df": n - 1, "p": np.nan}
    w = 12 * s / denom
    chi2 = m * (n - 1) * w
    return {"W": w, "chi2": chi2, "df": n - 1, "p": float(stats.chi2.sf(chi2, n - 1))}


# ---------------------------------------------------------------- agreement
def kappa(a, b, scale, weights=None) -> float:
    """Cohen's kappa over the full rating scale; NaN when only one value is used by both raters."""
    index = {v: i for i, v in enumerate(scale)}           # 0 / 0.5 / 1 -> 0 / 1 / 2 (sklearn wants classes)
    a, b = [index[float(v)] for v in a], [index[float(v)] for v in b]
    if len(set(a) | set(b)) < 2:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(cohen_kappa_score(a, b, labels=list(range(len(scale))), weights=weights))


def landis_koch(k: float) -> str:
    if np.isnan(k):
        return "not defined"
    for cut, name in ((0.8, "almost perfect"), (0.6, "substantial"), (0.4, "moderate"), (0.2, "fair"),
                      (0.0, "slight")):
        if k > cut:
            return name
    return "poor"


def agreement(a: pd.DataFrame, b: pd.DataFrame, comparison: str) -> list[dict]:
    """Agreement between two sets of scores on the items both have (indexed by item_id)."""
    both = a.join(b, how="inner", lsuffix="_a", rsuffix="_b")
    rows = []
    for dv in HUMAN_DVS:
        x, y = both[f"{dv}_a"], both[f"{dv}_b"]
        k = kappa(x, y, SCALES[dv])
        rows.append({"comparison": comparison, "dimension": dv, "n": len(both),
                     "pct_agree": float((x == y).mean()) if len(both) else np.nan, "kappa": k,
                     "kappa_quadratic": kappa(x, y, SCALES[dv], "quadratic") if len(SCALES[dv]) > 2 else np.nan,
                     "interpretation": landis_koch(k)})
    return rows


def mean_difference(a: pd.DataFrame, b: pd.DataFrame, comparison: str) -> list[dict]:
    """Is one rater consistently more generous? Mean of each on the shared items, and a Wilcoxon
    signed-rank test of the paired differences (kappa alone does not show a one-sided shift)."""
    both = a.join(b, how="inner", lsuffix="_a", rsuffix="_b")
    rows = []
    for dv in HUMAN_DVS:
        x, y = both[f"{dv}_a"].astype(float), both[f"{dv}_b"].astype(float)
        d = x - y
        p = float(stats.wilcoxon(x, y).pvalue) if (d != 0).any() else 1.0    # all equal: no shift
        rows.append({"comparison": comparison, "dimension": dv, "n": len(both), "mean_a": x.mean(),
                     "mean_b": y.mean(), "difference": d.mean(), "a_higher": int((d > 0).sum()),
                     "b_higher": int((d < 0).sum()), "wilcoxon_p": p})
    return rows


def repeat_pairs(scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A rater's first and repeated scores for the items they re-scored at the midpoint."""
    rep = scores[scores["is_repeat"] == 1].set_index("item_id")[list(HUMAN_DVS)]
    return first_scores(scores).loc[rep.index], rep


def rep_spread(scored: pd.DataFrame) -> pd.DataFrame:
    """How much the 3 repetitions differ: mean range per cell, share of cells where all 3 agree."""
    rows = []
    for dv in DVS:
        g = scored.dropna(subset=[dv]).groupby(KEYS, observed=True)[dv]
        if not len(g):
            continue
        cell = pd.DataFrame({"range": g.max() - g.min()}).reset_index()
        for model, c in cell.groupby("model_key"):
            rows.append({"model_key": model, "dv": dv, "cells": len(c), "mean_range": c["range"].mean(),
                         "max_range": c["range"].max(),
                         "all_three_equal": float((c["range"] == 0).mean()) if dv in HUMAN_DVS else np.nan})
    return ordered(pd.DataFrame(rows))


# ---------------------------------------------------------------- RQ4: reliability rates
def confirmed_counts(review: list[dict]) -> dict[str, float]:
    """Confirmed hallucinations (verdict H) per item; NaN while any of the item's candidates is unreviewed."""
    by_item: dict[str, list[str]] = {}
    for r in review:
        by_item.setdefault(r["item_id"], []).append(r["verdict"].strip().upper())
    return {i: float(sum(v == "H" for v in vs)) if all(vs) else np.nan for i, vs in by_item.items()}


def _rates(g: pd.DataFrame) -> dict:
    rc = g["root_cause_correctness"]
    scored = rc.notna().all()
    wrong, right, asserted = rc == 0, rc == 1, g["root_cause_asserted"] == 1
    reviewed = g["hallucinations_h"].notna()
    refs = g["refs_checked"].sum()
    return {
        "answers": len(g),
        "misdiagnosis_rate": float(wrong.mean()) if scored else np.nan,
        "false_confidence_rate": float((wrong & asserted).mean()) if scored else np.nan,
        "wrong_asserted_share": float((wrong & asserted).sum() / wrong.sum()) if scored and wrong.any() else np.nan,
        "right_asserted_share": float((right & asserted).sum() / right.sum()) if scored and right.any() else np.nan,
        "hedges_when_wrong": float(g.loc[wrong, "hedges_root_cause"].mean()) if scored and wrong.any() else np.nan,
        "hedges_when_right": float(g.loc[right, "hedges_root_cause"].mean()) if scored and right.any() else np.nan,
        "asserted_rate": float(asserted.mean()),
        "candidate_answer_rate": float(g["hallucination_auto"].mean()),
        "candidates_per_100_refs": float(100 * g["hallucination_candidates"].sum() / refs) if refs else np.nan,
        "reviewed_answers": int(reviewed.sum()),
        "hallucination_answer_rate": float((g["hallucinations_h"] > 0).mean()) if reviewed.all() else np.nan,
        "hallucinations_per_100_refs": float(100 * g["hallucinations_h"].sum() / refs)
        if reviewed.all() and refs else np.nan,
        "refs_checked_median": float(g["refs_checked"].median()),
    }


def rates(scored: pd.DataFrame) -> pd.DataFrame:
    """Per-answer rates per model, overall, by level, by category and both; 'all' marks a margin.
    Needs columns hallucinations_h (NaN = review pending) and root_cause_correctness (NaN = not scored
    yet). With expert means, 0.5 (the two experts disagree) counts as neither wrong nor right."""
    rows = []
    for by in (["model_key"], ["model_key", "level"], ["model_key", "category"], ["model_key", "level", "category"]):
        for keys, g in scored.groupby(by, observed=True):
            rows.append({"level": "all", "category": "all", **dict(zip(by, keys)), **_rates(g)})
    return ordered(pd.DataFrame(rows))


def check_quality(review: list[dict], recall: list[dict]) -> dict:
    """Precision of the automated check (H / reviewed candidates) and recall estimated on the sample
    of answers read in full: H found / (H found + entities the reader says were missed)."""
    verdicts = [r["verdict"].strip().upper() for r in review]
    reviewed = [v for v in verdicts if v]
    out = {"candidates": len(review), "reviewed": len(reviewed),
           **{f"verdict_{v}": reviewed.count(v) for v in "HCNF"},
           "precision": reviewed.count("H") / len(reviewed) if reviewed and len(reviewed) == len(review) else np.nan}
    read = [r["item_id"] for r in recall if r["checked"].strip()]
    counts = confirmed_counts(review)
    found = [counts.get(i, 0.0) for i in read]
    missed = sum(len([x for x in re.split(r"[;,]", r["missed_entities"]) if x.strip()])
                 for r in recall if r["checked"].strip())
    complete = read and not any(np.isnan(f) for f in found)
    out.update({"recall_sample": len(recall), "recall_read": len(read),
                "recall_found_H": float(sum(found)) if complete else np.nan, "recall_missed": missed,
                "recall": sum(found) / (sum(found) + missed) if complete and sum(found) + missed else np.nan})
    return out


def context_window(answers: pd.DataFrame, num_ctx: int, max_output: int) -> pd.DataFrame:
    """Prompt and answer sizes per model and level; for llama, the share of its window used."""
    rows = []
    for (model, level), g in answers.groupby(["model_key", "level"], observed=True):
        rows.append({"model_key": model, "level": level, "answers": len(g),
                     "input_tokens_median": float(g["input_tokens"].median()),
                     "input_tokens_max": int(g["input_tokens"].max()),
                     "output_tokens_median": float(g["output_tokens"].median()),
                     "output_tokens_max": int(g["output_tokens"].max()),
                     "words_median": float(g["words"].median()), "truncated": int(g["truncated"].sum()),
                     "all_headings_share": float(g["all_headings"].mean()),
                     "window_used_max": (g["input_tokens"].max() + max_output) / num_ctx if model == "llama"
                     else np.nan})
    return ordered(pd.DataFrame(rows))


# ---------------------------------------------------------------- MOCK fill-ins for --mock
def mock_review(review: list[dict], seed: int) -> list[dict]:
    rng = random.Random(f"{seed}:mock:review")
    return [{**r, "verdict": rng.choices("HCNF", (5, 2, 1, 2))[0], "reviewer_note": "MOCK"} for r in review]


def mock_recall(recall: list[dict], seed: int) -> list[dict]:
    rng = random.Random(f"{seed}:mock:recall")
    return [{**r, "checked": "yes", "missed_entities": "MOCK_missed" if rng.random() < 0.2 else "",
             "reviewer_note": "MOCK"} for r in recall]
