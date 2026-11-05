"""Step 8 — analysis: descriptives, two-way ANOVA per model, Tukey HSD, checks, rates, kappa, figures.

    python scripts/analyse.py          # real files -> results/analysis/, results/figures/
    python scripts/analyse.py --mock   # MOCK scores and review -> results/mock/analysis/, results/mock/figures/

Each part runs once its inputs are complete; until then the report lists it as pending.
  always (automated)        specificity, context window, hallucination candidates
  researcher scores         results/scores_researcher_provisional.csv, all 405 items
  expert scores             results/scores_expert_1.csv and _2.csv (90 items each: 45 shared + 45 own, D30)
  hallucination review      results/hallucination_review.csv and _recall_sample.csv (Step 7)

Every table has a data_label column and every figure a footer saying what the numbers rest on:
"Provisional researcher scores — expert evaluation pending" for anything built from the
researcher's scores, and "MOCK DATA" on everything made with --mock.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import analysis as a  # noqa: E402
from core import config  # noqa: E402
from core.metrics import BANDS  # noqa: E402
from core.scoring import (EXPERTS, MOCK_LABEL, N_SHARED, PROVISIONAL_LABEL, RESEARCHER, read_scores,  # noqa: E402
                          scores_path)
from compute_metrics import METRICS_PATH, RECALL_PATH, REVIEW_PATH  # noqa: E402
from prepare_scoring import ASSIGNMENTS_PATH, KEY_PATH  # noqa: E402

EXPERT_LABEL_FULL = "Expert scores (one repetition per cell; mean of 2 experts on 45 shared answers, 1 expert on 90)"
EXPERT_LABEL = EXPERT_LABEL_FULL          # replaced in run() when a file is missing or partly scored (D36)
AUTO_LABEL = "Automated metric"
UNIT_NAMES = {"median3": "median of 3 repetitions", "experts": "expert scores, 1 repetition"}
COLORS = {"gpt": "#1b6ca8", "claude": "#d95f02", "llama": "#6a51a3"}


def out_dirs(mock: bool) -> tuple[Path, Path]:
    return (config.MOCK_DIR / "analysis", config.MOCK_DIR / "figures") if mock else \
        (config.RESULTS_DIR / "analysis", config.FIGURES_DIR)


def rel(path: Path) -> str:
    return str(path.relative_to(config.PROJECT_ROOT)) if path.is_relative_to(config.PROJECT_ROOT) else str(path)


def expert_label(experts: list[pd.DataFrame]) -> str:
    """What the expert scores actually cover: the D30 design when both files are complete."""
    ids = [set(a.first_scores(e).index) for e in experts]
    both = len(ids[0] & ids[1]) if len(ids) == 2 else 0
    total = len(set().union(*ids))
    if both == N_SHARED and total == 135:
        return EXPERT_LABEL_FULL
    return (f"Expert scores (one repetition per cell; {total} of 135 answers scored: mean of 2 experts on {both}, "
            f"1 expert on {total - both}; D36)")


def label_for(dv: str | None, unit: str, mock: bool) -> str:
    if mock:
        return MOCK_LABEL
    if dv in a.HUMAN_DVS:
        return PROVISIONAL_LABEL if unit == "median3" else EXPERT_LABEL
    return AUTO_LABEL


# ---------------------------------------------------------------- inputs
def load_rater(rater: str, assignments: dict, mock: bool) -> tuple[pd.DataFrame | None, str]:
    """A rater's scores if every assigned item (and repeat) is scored, else None and why. An expert's
    partly scored file is used as far as it goes (D36); the researcher's must be complete."""
    path = scores_path(rater, mock)
    if not path.exists():
        return None, f"not yet ({rel(path)} missing)"
    rows = read_scores(path)
    want = "MOCK" if mock else ("PROVISIONAL" if rater == RESEARCHER else "EXPERT")
    if any(r["status"] != want for r in rows):
        raise SystemExit(f"{path.name}: every row must have status {want}")
    expected = {(o["item_id"], int(o["is_repeat"])) for o in assignments[rater]}
    got = {(r["item_id"], int(r["is_repeat"])) for r in rows}
    if got != expected:
        if rater != RESEARCHER and got and got <= expected:
            return a.scores_frame(rows), f"PARTIAL ({len(got)}/{len(expected)} scored)"
        return None, f"incomplete ({len(got & expected)}/{len(expected)} scored)"
    return a.scores_frame(rows), f"complete ({len(rows)} rows)"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(path, index=False)


# ---------------------------------------------------------------- statistics per unit
def unit_tests(cells: pd.DataFrame, unit: str, mock: bool) -> dict[str, pd.DataFrame]:
    """ANOVA, assumption checks, Tukey (overall and within each category) and rank-based checks
    for every model x DV with data."""
    anova, checks, tukey, nonpar = [], [], [], []
    for model in a.MODELS:
        for dv in a.DVS:
            data = a.model_data(cells, model, dv)
            if data.empty:
                continue
            base = {"unit": unit, "model_key": model, "dv": dv, "n": len(data)}
            rows, fit, note = a.two_way_anova(data)
            anova += [{**base, **r, "note": note} for r in rows] or [{**base, "effect": "-", "note": note}]
            checks.append({**base, **a.assumption_checks(data, fit)})
            tukey += [{**base, "scope": "all categories", **r} for r in a.tukey_levels(data)]
            for cat, sub in data.groupby("category"):
                tukey += [{**base, "scope": cat, **r} for r in a.tukey_levels(sub)]
            nonpar += [{**base, **r} for r in a.nonparametric(data)]
    out = {"anova": pd.DataFrame(anova), "assumptions": pd.DataFrame(checks),
           "tukey": pd.DataFrame(tukey), "nonparametric": pd.DataFrame(nonpar)}
    if not out["anova"].empty:     # Holm within each model and effect, over the 4 DVs
        out["anova"]["p_holm"] = out["anova"].groupby(["model_key", "effect"])["p"].transform(a.holm)
    for name, df in out.items():
        if not df.empty:
            df["data_label"] = [label_for(dv, unit, mock) for dv in df["dv"]]
            out[name] = a.ordered(df)
    return out


def category_consistency(cells: pd.DataFrame, unit: str, mock: bool) -> pd.DataFrame:
    """RQ3: do the models rank the five categories alike? Kendall's W over the category means."""
    rows = []
    for dv in a.DVS:
        means = cells.dropna(subset=[dv]).groupby(["model_key", "category"])[dv].mean().unstack()
        if len(means) < 2:
            continue
        rows.append({"unit": unit, "dv": dv, "models": len(means), "categories": means.shape[1],
                     **a.kendall_w(means), "data_label": label_for(dv, unit, mock)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- figures
def stamp(fig, labels: list[str], mock: bool) -> None:
    text = "  ·  ".join(dict.fromkeys(x for x in labels if x))
    warn = mock or PROVISIONAL_LABEL in text
    fig.text(0.01, 0.01, text, fontsize=9, color="crimson" if warn else "dimgray", ha="left", va="bottom")
    if mock:
        fig.text(0.5, 0.5, "MOCK DATA", fontsize=70, color="crimson", alpha=0.13, ha="center", va="center",
                 rotation=25, weight="bold")


def pending(ax, what: str) -> None:
    ax.text(0.5, 0.5, f"pending:\n{what}", ha="center", va="center", transform=ax.transAxes, color="gray")
    ax.set_xticks([])
    ax.set_yticks([])


def plot_cells(cells: dict, researcher_scored: bool) -> tuple[pd.DataFrame, str]:
    """What the figures show: specificity always as the median of 3; the human-scored DVs from the
    researcher's median of 3 if there is one, else from the experts' scores (D30)."""
    base = cells["median3"]
    if researcher_scored or "experts" not in cells:
        return base, "median3"
    human = cells["experts"].set_index(a.KEYS)[list(a.HUMAN_DVS)]
    return base.drop(columns=list(a.HUMAN_DVS)).join(human, on=a.KEYS), "experts"


def unit_of(dv: str, human_unit: str) -> str:
    return human_unit if dv in a.HUMAN_DVS else "median3"


def fig_context(cells: pd.DataFrame, path: Path, mock: bool, human_unit: str = "median3") -> None:
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.6))
    labels = []
    for ax, dv in zip(axes, a.DVS):
        ax.set_title(a.DV_NAMES[dv])
        if cells[dv].isna().all():
            pending(ax, "expert scores")
            continue
        labels.append(label_for(dv, unit_of(dv, human_unit), mock))
        for i, model in enumerate(a.MODELS):
            g = cells[cells["model_key"] == model].groupby("level")[dv]
            mean, sem, n = (x.reindex(a.LEVELS) for x in (g.mean(), g.sem(), g.count()))
            ci = sem * stats.t.ppf(0.975, n - 1)
            ax.errorbar(np.arange(3) + (i - 1) * 0.07, mean, yerr=ci, marker="o", capsize=3,
                        color=COLORS[model], label=model)
        ax.set_xticks(range(3), a.LEVELS)
        ax.set_xlabel("context level")
        if dv == "specificity":
            for cut, name in BANDS:
                ax.axhline(cut, ls=":", lw=0.9, color="gray")
                ax.text(2.25, cut, name, fontsize=8, color="gray", va="bottom", ha="right")
    next(ax for ax in axes if ax.lines).legend(frameon=False)
    fig.suptitle(("MOCK DATA — " if mock else "") +
                 "Context level effect: mean of the 45 scenario × level values per model, ±95% CI" +
                 (" (specificity: median of 3 reps; human scores: experts, 1 rep)" if human_unit == "experts"
                  else " (median of 3 reps)"))
    stamp(fig, labels, mock)
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_heatmaps(cells: pd.DataFrame, path: Path, mock: bool, human_unit: str = "median3") -> None:
    ranges = {"technical_accuracy": (0, 1), "root_cause_correctness": (0, 1), "actionability": (1, 3)}
    spec = cells["specificity"]
    ranges["specificity"] = (float(spec.min()), float(spec.max()))
    fig, axes = plt.subplots(len(a.MODELS), len(a.DVS), figsize=(17, 11))
    labels = []
    for r, model in enumerate(a.MODELS):
        for c, dv in enumerate(a.DVS):
            ax = axes[r, c]
            ax.set_title(f"{model} — {a.DV_NAMES[dv]}", fontsize=10)
            sub = cells[cells["model_key"] == model]
            if sub[dv].isna().all():
                pending(ax, "expert scores")
                continue
            labels.append(label_for(dv, unit_of(dv, human_unit), mock))
            grid = sub.groupby(["category", "level"])[dv].mean().unstack().reindex(
                index=list(a.ORDER["category"]), columns=list(a.LEVELS))
            ax.imshow(grid.to_numpy(), cmap="viridis", vmin=ranges[dv][0], vmax=ranges[dv][1], aspect="auto")
            for (i, j), v in np.ndenumerate(grid.to_numpy()):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9,
                        color="white" if v < sum(ranges[dv]) / 2 else "black")
            ax.set_xticks(range(3), a.LEVELS, fontsize=8)
            ax.set_yticks(range(len(grid)), [x.replace("_", " ") for x in grid.index] if c == 0 else [], fontsize=8)
    fig.suptitle(("MOCK DATA — " if mock else "") +
                 "Mean per failure category × context level (3 scenarios each" +
                 ("; specificity: median of 3 reps; human scores: experts, 1 rep)" if human_unit == "experts"
                  else ", median of 3 reps)"))
    stamp(fig, labels, mock)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_specificity(answers: pd.DataFrame, path: Path, mock: bool) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.8))
    pos, data, colors = [], [], []
    for i, model in enumerate(a.MODELS):
        for j, level in enumerate(a.LEVELS):
            pos.append(i * 4 + j)
            data.append(answers.loc[(answers["model_key"] == model) & (answers["level"] == level), "specificity"])
            colors.append(COLORS[model])
    box = ax.boxplot(data, positions=pos, widths=0.7, patch_artist=True)
    for patch, color in zip(box["boxes"], colors):
        patch.set(facecolor=color, alpha=0.35, edgecolor=color)
    ax.set_xticks(pos, [lvl for _ in a.MODELS for lvl in a.LEVELS], fontsize=8)
    for i, model in enumerate(a.MODELS):
        ax.text(i * 4 + 1, 1.0, model, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                color=COLORS[model], weight="bold")
    for cut, name in BANDS:
        ax.axhline(cut, ls=":", lw=0.9, color="gray")
        ax.text(pos[-1] + 0.45, cut, name, fontsize=8, color="gray", va="bottom", ha="right")
    ax.set_ylabel("cosine similarity to the reference fix")
    ax.set_title(("MOCK DATA — " if mock else "") + "Specificity of every answer (n = 405)", pad=18)
    stamp(fig, [label_for("specificity", "median3", mock)], mock)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_reliability(rate_table: pd.DataFrame, path: Path, mock: bool,
                    human_rates: pd.DataFrame | None = None) -> None:
    """Hallucinations from all 405 answers; misdiagnosis and false confidence from the researcher's scores
    (rate_table) or, when given, from the experts' 135 answers (human_rates, D30)."""
    level_rows = lambda t: t[(t["level"] != "all") & (t["category"] == "all")]  # noqa: E731
    by_level = level_rows(rate_table)
    human = level_rows(human_rates) if human_rates is not None else by_level
    human_label = EXPERT_LABEL if human_rates is not None else PROVISIONAL_LABEL
    confirmed = by_level["hallucination_answer_rate"].notna().all()
    panels = [("hallucination_answer_rate" if confirmed else "candidate_answer_rate",
               "Answers with ≥ 1 hallucination" if confirmed else "Answers with ≥ 1 hallucination CANDIDATE\n"
               "(automated, before review)", None, by_level),
              ("misdiagnosis_rate", "Misdiagnosis (root cause scored 0)", "expert scores", human),
              ("wrong_asserted_share", "False confidence: wrong root causes\nstated without any hedge",
               "expert scores", human)]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    labels = []
    for ax, (col, title, needs, table) in zip(axes, panels):
        ax.set_title(title, fontsize=10)
        if table[col].isna().all():
            pending(ax, needs or "review")
            continue
        labels.append(MOCK_LABEL if mock else human_label if needs else AUTO_LABEL)
        for i, model in enumerate(a.MODELS):
            vals = table[table["model_key"] == model].set_index("level")[col].reindex(a.LEVELS)
            ax.bar(np.arange(3) + (i - 1) * 0.27, vals, width=0.27, color=COLORS[model], label=model)
        ax.set_xticks(range(3), a.LEVELS)
        ax.set_ylim(0, 1)
        ax.set_ylabel("share of answers" if col != "wrong_asserted_share" else "share of wrong answers")
    axes[0].legend(frameon=False)
    fig.suptitle(("MOCK DATA — " if mock else "") + "Reliability by context level" +
                 (" (hallucinations: all 405 answers; diagnosis: the experts' 135 answers)" if human_rates is not None
                  else " (all 3 repetitions, 45 answers per bar)"))
    stamp(fig, labels, mock)
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- report
def fmt(v, col: str = "") -> str:
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return ""
        if col == "p" or col.endswith("_p") or col.startswith("p_"):
            return "< .001" if v < 0.001 else f"{v:.3f}"
        return f"{v:.0f}" if float(v).is_integer() and abs(v) >= 10 else f"{v:.3f}"   # token counts etc.
    return str(v)


def md(df: pd.DataFrame, cols: list[str] | None = None, headers: list[str] | None = None) -> str:
    if df is None or df.empty:
        return "_(nothing yet)_\n"
    cols = cols or list(df.columns)
    lines = ["| " + " | ".join(headers or cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(r[c], c) for c in cols) + " |" for _, r in df.iterrows()]
    return "\n".join(lines) + "\n"


def level_table(desc: pd.DataFrame) -> pd.DataFrame:
    """model x dv rows, one 'mean (SD)' column per level."""
    d = desc.assign(cell=[f"{m:.3f} ({s:.3f})" for m, s in zip(desc["mean"], desc["sd"])])
    wide = d.pivot_table(index=["model_key", "dv"], columns="level", values="cell", aggfunc="first")
    return a.ordered(wide.reindex(columns=list(a.LEVELS)).reset_index())


def report(path: Path, inputs: dict, res: dict, mock: bool, figures: list[Path]) -> None:
    human = [d for d in a.HUMAN_DVS if not res["cells"]["median3"][d].isna().all()]
    out = ["# Step 8 — analysis report", ""]
    if mock:
        out += [f"> **{MOCK_LABEL}.** Nothing in this report is a result. Mock scores never depend on model "
                "or level, so any 'effect' here is noise (D25).", ""]
    elif human:
        out += [f"> **{PROVISIONAL_LABEL}.** Technical accuracy, root cause correctness and actionability "
                "below come from the researcher's scores. Specificity, hallucination candidates and context "
                "sizes are automated.", ""]
    out += [f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `scripts/analyse.py"
            f"{' --mock' if mock else ''}`. Methods: decisions log D29.", "", "## Inputs", "",
            md(pd.DataFrame([{"input": k, "status": v} for k, v in inputs.items()])), ""]

    out += ["## 1. Context effect (RQ1, RQ2) — descriptives by level", "",
            "Mean (SD) of the 45 scenario × level values per model (each the median of 3 repetitions).", "",
            md(level_table(res["desc_level"]), ["model_key", "dv", *a.LEVELS]), ""]

    an = res["tests"]["median3"]["anova"]
    out += ["## 2. Two-way ANOVA per model: level × category (median of 3 repetitions)", "",
            "Type II sums of squares; 3 values per cell, residual df 30. p_holm: Holm correction over the 4 DVs "
            "for each model and effect.", "",
            md(an, ["model_key", "dv", "effect", "df", "df_resid", "F", "p", "p_holm", "partial_eta2", "note"]),
            "", "**Assumption checks** (Shapiro-Wilk on residuals; Brown-Forsythe Levene over the 15 cells):", "",
            md(res["tests"]["median3"]["assumptions"],
               ["model_key", "dv", "shapiro_W", "shapiro_p", "levene_W", "levene_p"]), ""]

    tk = res["tests"]["median3"]["tukey"]
    out += ["## 3. Tukey HSD between context levels (all categories)", "",
            "Difference = later level minus earlier. Within-category comparisons (n = 3 per level) are in "
            "`tukey.csv`.", "",
            md(tk[tk["scope"] == "all categories"] if not tk.empty else tk,
               ["model_key", "dv", "from", "to", "mean_diff", "ci_low", "ci_high", "p_adj"]), ""]

    out += ["## 4. Rank-based checks", "",
            "Kruskal-Wallis treats the 45 values as independent, like the ANOVA. Friedman blocks on scenario: "
            "each scenario appears at all three levels, which the ANOVA does not model.", "",
            md(res["tests"]["median3"]["nonparametric"],
               ["model_key", "dv", "test", "factor", "statistic", "p", "effect_size", "effect_measure", "note"]), ""]

    dc = res["desc_category"]
    out += ["## 5. Failure categories (RQ3)", "", "Mean per category (9 values: 3 scenarios × 3 levels).", ""]
    if not dc.empty:
        wide = dc.pivot_table(index=["dv", "category"], columns="model_key", values="mean")
        wide = a.ordered(wide.reindex(columns=list(a.MODELS)).reset_index())
        out += [md(wide, ["dv", "category", *a.MODELS]), ""]
    out += ["Do the models rank the categories alike? Kendall's W (1 = same order, 0 = no agreement):", "",
            md(res["consistency"], ["unit", "dv", "models", "W", "chi2", "df", "p"]), ""]

    rt = res["rates"]
    by_level, by_cat = rt[rt["category"] == "all"], rt[(rt["level"] == "all") & (rt["category"] != "all")]
    diag = ["answers", "misdiagnosis_rate", "false_confidence_rate", "wrong_asserted_share", "right_asserted_share",
            "hedges_when_wrong", "hedges_when_right"]
    hall = ["answers", "candidate_answer_rate", "hallucination_answer_rate", "candidates_per_100_refs",
            "hallucinations_per_100_refs", "refs_checked_median"]
    out += ["## 6. Reliability (RQ4)", "",
            "Per answer, all 3 repetitions (45 answers per model × level, 27 per model × category).", "",
            "**Misdiagnosis and false confidence.** Misdiagnosis = root cause scored 0. False confidence = "
            "misdiagnosed and stated without any hedge word; `wrong_asserted_share` is its share of the "
            "misdiagnoses, `right_asserted_share` the same for correct diagnoses (a well-calibrated model asserts "
            "more when it is right).", "",
            md(by_level, ["model_key", "level", *diag]), "", md(by_cat, ["model_key", "category", *diag]), "",
            "**Hallucinations.** Candidates are automated (Step 7); confirmed rates count reviewed verdicts H only "
            "and stay empty until every candidate has a verdict. Per 100 checked references corrects for "
            "how many entities an answer names.", "",
            md(by_level, ["model_key", "level", *hall]), "", md(by_cat, ["model_key", "category", *hall]), "",
            "Model × level × category: `rates.csv`.", "",
            "**Hallucination check quality** (precision = H / candidates; recall from the sample read in full):",
            "", md(pd.DataFrame([res["check"]])), "",
            "**Context window** (prompt + answer sizes; llama's window is 8,192 tokens):", "",
            md(res["context"]), ""]

    out += ["## 7. Agreement", "", "Cohen's kappa over the full scale (proposal §7.5); quadratic-weighted kappa "
            "for the 3-point scales; % exact agreement. The two experts are compared on the answers both "
            "scored (45 when both files are complete, D30).", "", md(res["agreement"]) if not res["agreement"].empty else "_(nothing yet)_", ""]
    if "rater_difference" in res:
        out += ["**Is one expert more generous?** Mean score of each on the shared answers; difference = "
                "expert_1 − expert_2; Wilcoxon signed-rank test of the paired differences (D34).", "",
                md(res["rater_difference"]), ""]

    if "experts" in res["tests"]:
        ex = res["tests"]["experts"]
        tke = ex["tukey"]
        rte = res["rates_experts"]
        dce = res["desc_category_experts"]
        out += ["## 8. Expert scores (RQ1–RQ4): one repetition per cell", "",
                f"{EXPERT_LABEL}. Up to 45 values per model (3 per level × category cell); n in each table shows "
                "how many were scored.", "",
                "**Means (SD) by level:**", "",
                md(level_table(res["desc_level_experts"]), ["model_key", "dv", *a.LEVELS]), "",
                "**Two-way ANOVA** (p_holm over the 4 DVs):", "",
                md(ex["anova"], ["model_key", "dv", "effect", "df", "df_resid", "F", "p", "p_holm", "partial_eta2",
                                 "note"]), "",
                "**Assumption checks:**", "",
                md(ex["assumptions"], ["model_key", "dv", "shapiro_W", "shapiro_p", "levene_W", "levene_p"]), "",
                "**Tukey HSD between levels (all categories):**", "",
                md(tke[tke["scope"] == "all categories"] if not tke.empty else tke,
                   ["model_key", "dv", "from", "to", "mean_diff", "ci_low", "ci_high", "p_adj"]), "",
                "**Rank-based checks:**", "",
                md(ex["nonparametric"], ["model_key", "dv", "test", "factor", "statistic", "p", "effect_size",
                                         "effect_measure", "note"]), ""]
        if not dce.empty:
            wide = dce.pivot_table(index=["dv", "category"], columns="model_key", values="mean")
            out += ["**Means by category:**", "",
                    md(a.ordered(wide.reindex(columns=list(a.MODELS)).reset_index()), ["dv", "category", *a.MODELS]),
                    ""]
        out += ["**Misdiagnosis and false confidence on the expert scores** (135 answers; root cause 0.5 = the "
                "experts disagree, counted as neither wrong nor right):", "",
                md(rte[rte["category"] == "all"], ["model_key", "level", *diag]), "",
                md(rte[(rte["level"] == "all") & (rte["category"] != "all")], ["model_key", "category", *diag]), ""]
    else:
        out += ["## 8. Expert scores", "", "_Pending: both expert score files._", ""]

    out += ["## Files", "", "Tables (CSV, every row has `data_label`): " +
            ", ".join(f"`{p}`" for p in sorted(x.name for x in path.parent.glob("*.csv"))), "",
            "Figures: " + ", ".join(f"`{rel(f)}`" for f in figures), ""]
    path.write_text("\n".join(out))


# ---------------------------------------------------------------- main
def run(mock: bool) -> dict:
    global EXPERT_LABEL
    EXPERT_LABEL = EXPERT_LABEL_FULL
    tables_dir, fig_dir = out_dirs(mock)
    for d in (tables_dir, fig_dir):
        d.mkdir(parents=True, exist_ok=True)
    key = json.loads(KEY_PATH.read_text())["items"]
    assignments = json.loads(ASSIGNMENTS_PATH.read_text())
    answers = a.answers_frame(key, pd.read_csv(METRICS_PATH))

    inputs = {}
    researcher, inputs["researcher scores (all 405)"] = load_rater(RESEARCHER, assignments, mock)
    experts = {}
    for e in EXPERTS:
        experts[e], inputs[f"{e} scores (90: 45 shared + 45 own)"] = load_rater(e, assignments, mock)
    review, recall = read_rows(REVIEW_PATH), read_rows(RECALL_PATH)
    if mock:
        review, recall = a.mock_review(review, config.GLOBAL_SEED), a.mock_recall(recall, config.GLOBAL_SEED)
    inputs["hallucination review"] = f"{sum(bool(r['verdict'].strip()) for r in review)}/{len(review)} verdicts" + \
        (" (MOCK)" if mock else "")
    inputs["recall sample"] = f"{sum(bool(r['checked'].strip()) for r in recall)}/{len(recall)} read" + \
        (" (MOCK)" if mock else "")

    counts = a.confirmed_counts(review)
    scored = a.with_scores(answers, researcher)
    scored["hallucinations_h"] = scored["item_id"].map(lambda i: counts.get(i, 0.0))

    cells = {"median3": a.median3_cells(scored)}
    expert_scored = None
    available = [experts[e] for e in EXPERTS if experts[e] is not None]
    if available:                           # one expert, or a partly scored file, is used as far as it goes (D36)
        EXPERT_LABEL = expert_label(available)
        cells["experts"] = a.expert_cells(answers, available)
        expert_scored = a.with_expert_scores(answers, available).dropna(subset=list(a.HUMAN_DVS))
        expert_scored["hallucinations_h"] = expert_scored["item_id"].map(lambda i: counts.get(i, 0.0))

    res = {"cells": cells, "tests": {u: unit_tests(c, u, mock) for u, c in cells.items()}}
    lab = lambda df, unit="median3": df.assign(data_label=[label_for(dv, unit, mock) for dv in df["dv"]])  # noqa: E731
    res["desc_level"] = lab(a.describe(cells["median3"], ["level"]))
    res["desc_category"] = lab(a.describe(cells["median3"], ["category"]))
    res["desc_cells"] = lab(a.describe(cells["median3"], ["category", "level"]))
    res["desc_root_cause_type"] = lab(a.describe(cells["median3"], ["root_cause_type", "level"]))
    res["consistency"] = pd.concat([category_consistency(c, u, mock) for u, c in cells.items()], ignore_index=True)
    res["rep_spread"] = lab(a.rep_spread(scored))
    rate_label = MOCK_LABEL if mock else PROVISIONAL_LABEL if researcher is not None else \
        AUTO_LABEL + " (human-score columns pending)"
    res["rates"] = a.rates(scored).assign(data_label=rate_label)
    if expert_scored is not None:
        res["rates_experts"] = a.rates(expert_scored).assign(data_label=MOCK_LABEL if mock else EXPERT_LABEL)
        res["desc_level_experts"] = lab(a.describe(cells["experts"], ["level"]), "experts")
        res["desc_category_experts"] = lab(a.describe(cells["experts"], ["category"]), "experts")
    res["check"] = {**a.check_quality(review, recall), "data_label": MOCK_LABEL if mock else "researcher review (D27)"}
    res["context"] = a.context_window(answers, config.OLLAMA_NUM_CTX, config.MAX_OUTPUT_TOKENS).assign(
        data_label=MOCK_LABEL if mock else AUTO_LABEL)

    agree = []
    expert_lab, researcher_lab = (MOCK_LABEL, MOCK_LABEL) if mock else ("Expert scores", PROVISIONAL_LABEL)
    first = {e: a.first_scores(experts[e]) for e in EXPERTS if experts[e] is not None}
    if len(first) == 2:
        n_shared = len(first["expert_1"].index.intersection(first["expert_2"].index))
        agree += [{**r, "data_label": expert_lab} for r in
                  a.agreement(first["expert_1"], first["expert_2"], f"expert_1 vs expert_2 ({n_shared} shared items)")]
        res["rater_difference"] = pd.DataFrame(
            a.mean_difference(first["expert_1"], first["expert_2"], f"expert_1 vs expert_2 ({n_shared} shared items)")
        ).assign(data_label=expert_lab)
    for e in first:
        if experts[e]["is_repeat"].any():       # midpoint repeats: none since D30, kept for older score files
            agree += [{**r, "data_label": expert_lab}
                      for r in a.agreement(*a.repeat_pairs(experts[e]), f"{e}: first vs midpoint repeat")]
        if researcher is not None:
            agree += [{**r, "data_label": researcher_lab}
                      for r in a.agreement(a.first_scores(researcher), first[e],
                                           f"researcher vs {e} ({len(first[e])} items)")]
    res["agreement"] = pd.DataFrame(agree)

    # ---- write tables
    for unit, tests in res["tests"].items():
        suffix = "" if unit == "median3" else "_experts"
        for name, df in tests.items():
            save(df, tables_dir / f"{name}{suffix}.csv")
    save(cells["median3"].assign(data_label=rate_label), tables_dir / "cells.csv")
    if "experts" in cells:
        save(cells["experts"].assign(data_label=MOCK_LABEL if mock else EXPERT_LABEL), tables_dir / "cells_experts.csv")
    for name in ("desc_level", "desc_category", "desc_cells", "desc_root_cause_type", "consistency", "rep_spread",
                 "rates", "context", "agreement"):
        save(res[name], tables_dir / f"{name.replace('desc_', 'descriptives_')}.csv")
    for name in ("rates_experts", "desc_level_experts", "desc_category_experts", "rater_difference"):
        if name in res:
            save(res[name], tables_dir / f"{name.replace('desc_', 'descriptives_')}.csv")
    save(pd.DataFrame([res["check"]]), tables_dir / "hallucination_check.csv")

    # ---- figures and report
    figures = [fig_dir / n for n in ("fig1_context_effect.png", "fig2_category_level_heatmaps.png",
                                     "fig3_specificity.png", "fig4_reliability.png")]
    shown, human_unit = plot_cells(cells, researcher is not None)
    fig_context(shown, figures[0], mock, human_unit)
    fig_heatmaps(shown, figures[1], mock, human_unit)
    fig_specificity(answers, figures[2], mock)
    fig_reliability(res["rates"], figures[3], mock,
                    res.get("rates_experts") if researcher is None and "rates_experts" in res else None)
    report(tables_dir / "report.md", inputs, res, mock, figures)
    res["inputs"], res["dirs"] = inputs, (tables_dir, fig_dir)
    return res


def summary(res: dict, mock: bool) -> None:
    if mock:
        print(f"*** {MOCK_LABEL} ***")
    for k, v in res["inputs"].items():
        print(f"  {k:36} {v}")
    an = res["tests"]["median3"]["anova"]
    print("\nTwo-way ANOVA, effect of context level (median of 3 reps; p Holm-adjusted within model):")
    for _, r in an[an["effect"] == "level"].iterrows():
        print(f"  {r['model_key']:7} {r['dv']:24} F({r['df']:.0f},{r['df_resid']:.0f}) = {r['F']:6.2f}  "
              f"p_holm = {fmt(r['p_holm'], 'p'):>6}  partial eta2 = {r['partial_eta2']:.2f}   [{r['data_label']}]")
    tables_dir, fig_dir = res["dirs"]
    print(f"\nWrote {rel(tables_dir)}/ (report.md + tables) and {rel(fig_dir)}/ (4 figures)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mock", action="store_true", help="use the MOCK scores (results/mock/); outputs go there")
    args = parser.parse_args(argv)
    res = run(args.mock)
    summary(res, args.mock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
