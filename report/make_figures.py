"""Diagrams for the report (Chapter 3): the dbt project's lineage and the study design.

    python report/make_figures.py   -> report/images/lineage.png, report/images/design.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "images"
COLS = {"source": "#e8eef6", "staging": "#e9f3ea", "mart": "#fbefdc", "exposure": "#f3e8f3", "step": "#eef0f2"}


def box(ax, x, y, text, kind, w=2.3, h=0.62):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
                                fc=COLS[kind], ec="#555555", lw=1))
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5, family="Arial")
    return (x, y, w, h)


def arrow(ax, a, b):
    (x1, y1, w1, _), (x2, y2, w2, _) = a, b
    ax.add_patch(FancyArrowPatch((x1 + w1 / 2, y1), (x2 - w2 / 2, y2), arrowstyle="-|>", mutation_scale=11,
                                 color="#555555", lw=1, shrinkA=2, shrinkB=2))


def lineage():
    fig, ax = plt.subplots(figsize=(10, 4.3))
    xs = {"source": 1.4, "staging": 4.5, "mart": 7.6, "exposure": 10.7}
    for kind, label in (("source", "Sources (raw schema)"), ("staging", "Staging views"),
                        ("mart", "Mart tables"), ("exposure", "Exposures")):
        ax.text(xs[kind], 4.15, label, ha="center", fontsize=10, weight="bold", family="Arial")
    n = {}
    for i, t in enumerate(("customers", "orders", "payments")):
        y = 3.2 - i * 1.25
        n["raw_" + t] = box(ax, xs["source"], y, f"raw_{t}", "source")
        n["stg_" + t] = box(ax, xs["staging"], y, f"stg_{t}", "staging")
    n["dim_customers"] = box(ax, xs["mart"], 2.6, "dim_customers", "mart")
    n["fct_orders"] = box(ax, xs["mart"], 0.9, "fct_orders", "mart")
    n["mkt"] = box(ax, xs["exposure"], 2.6, "marketing customer\ndashboard", "exposure", h=0.8)
    n["fin"] = box(ax, xs["exposure"], 0.9, "finance revenue\ndashboard", "exposure", h=0.8)
    for t in ("customers", "orders", "payments"):
        arrow(ax, n["raw_" + t], n["stg_" + t])
    for s in ("stg_customers", "stg_orders", "stg_payments"):
        arrow(ax, n[s], n["dim_customers"])
    for s in ("stg_orders", "stg_payments"):
        arrow(ax, n[s], n["fct_orders"])
    arrow(ax, n["dim_customers"], n["mkt"])
    arrow(ax, n["dim_customers"], n["fin"])
    arrow(ax, n["fct_orders"], n["fin"])
    ax.text(6.05, -0.15, "Ingestion jobs load the raw schema hourly; dbt builds the staging views and mart tables, "
            "runs the tests and checks source freshness.", ha="center", fontsize=8.5, color="#444444", family="Arial")
    ax.set_xlim(0, 12.1)
    ax.set_ylim(-0.4, 4.4)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "lineage.png", dpi=200)
    plt.close(fig)


def design():
    fig, ax = plt.subplots(figsize=(10, 4.6))
    steps = [
        (1.3, 3.4, "15 failure scenarios\n5 categories × 3\n(real dbt runs)"),
        (4.1, 3.4, "3 context levels\nminimal / partial / full\n(identical prompts)"),
        (6.9, 3.4, "3 LLMs × 3 repetitions\nGPT-5.5, Claude Sonnet 5.5,\nllama3:8b"),
        (9.7, 3.4, "405 suggestions\nstored as returned"),
    ]
    prev = None
    for x, y, t in steps:
        b = box(ax, x, y, t, "step", w=2.45, h=1.05)
        if prev:
            arrow(ax, prev, b)
        prev = b
    ev1 = box(ax, 3.1, 1.35, "Automated measures (all 405)\nspecificity · hallucination check\n· hedging · context size",
              "staging", w=3.6, h=1.05)
    ev2 = box(ax, 8.0, 1.35, "Expert evaluation (135 answers,\n1 repetition per condition)\ntechnical accuracy · root cause\n"
              "· actionability (blinded)", "mart", w=3.6, h=1.25)
    for b in (ev1, ev2):
        ax.add_patch(FancyArrowPatch((9.7, 2.82), (b[0], b[1] + b[3] / 2), arrowstyle="-|>", mutation_scale=11,
                                     color="#555555", lw=1))
    ax.text(5.55, 0.12, "Analysis per model: two-way ANOVA (level × category), Tukey HSD, Kruskal-Wallis, Friedman, "
            "Kendall's W, Cohen's kappa", ha="center", fontsize=9, family="Arial", color="#333333")
    ax.set_xlim(0, 11.1)
    ax.set_ylim(-0.2, 4.2)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "design.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    lineage()
    design()
    print("wrote", OUT / "lineage.png", OUT / "design.png")
