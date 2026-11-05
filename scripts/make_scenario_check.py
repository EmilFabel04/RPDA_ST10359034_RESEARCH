"""Scenario check (proposal §7.2, open item O1): the two evaluators judge whether each of the 15
scenarios is realistic and whether the researcher's reference fix is correct.

    python scripts/make_scenario_check.py             # writes results/scoring/pages/scenario_check.html
    python scripts/make_scenario_check.py --summary   # reads the returned CSVs and lists what was flagged

The page shows each scenario exactly as the scoring pages do (failure report, model and source details,
lineage, recent history) plus the reference fix. No LLM answers are shown. The evaluator picks
"Evaluator 1" or "Evaluator 2", answers two questions per scenario and emails the exported CSV.
Save the returned files as results/scoring/scenario_check_expert_1.csv and ..._expert_2.csv.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core.scoring import EXPERTS, RATER_LABELS  # noqa: E402
from prepare_scoring import PAGES_DIR, scenario_view  # noqa: E402

TEMPLATE = config.PROJECT_ROOT / "core" / "templates" / "scenario_check.html"
PAGE_PATH = PAGES_DIR / "scenario_check.html"
QUESTIONS = [
    {"key": "realistic", "question": "Is this a realistic dbt failure, as described?",
     "hint": "Could this plausibly happen in a production dbt project, and do the error, history and lineage "
             "look like what you would actually see?", "choices": ["Yes", "Mostly", "No"]},
    {"key": "fix_correct", "question": "Is the reference fix correct?",
     "hint": "Is the root cause right, and would the fix and verification step work? Partly = right idea "
             "but something is missing or wrong.", "choices": ["Yes", "Partly", "No"]},
]
BANNER = ("Please check all 15 scenarios (about 1–1.5 hours). For each one, read the scenario on the left and "
          "the researcher's reference fix on the right, then answer the two questions. If something is "
          "unrealistic or wrong, say what in the comments. Your answers are saved in this browser as you go. "
          "When you are done, click <b>Export CSV</b> and email the file to the researcher.")


def scenario_order() -> list[str]:
    with (config.SCENARIOS_DIR / "index.csv").open(newline="") as f:
        return [r["scenario_id"] for r in csv.DictReader(f)]


def build() -> Path:
    order = scenario_order()
    items = [{"position": n, "scenario_id": s} for n, s in enumerate(order, start=1)]
    page = {"id": "scenario-check-" + hashlib.sha256(json.dumps(items).encode()).hexdigest()[:10],
            "title": "RPDA8411 scenario check — 15 scenarios", "banner": BANNER,
            "raters": [[e, RATER_LABELS[e]] for e in EXPERTS]}
    data = {"page": page, "questions": QUESTIONS, "items": items,
            "scenarios": {k: v for k, v in scenario_view().items() if k in order}}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # cannot close the <script> tag
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGE_PATH.write_text(TEMPLATE.read_text().replace("__TITLE__", page["title"]).replace("__DATA__", blob),
                         encoding="utf-8")
    return PAGE_PATH


def summary() -> int:
    """Every scenario an evaluator did not answer 'Yes' to, with the comment."""
    found = False
    for e in EXPERTS:
        path = config.SCORING_DIR / f"scenario_check_{e}.csv"
        if not path.exists():
            print(f"{RATER_LABELS[e]}: not returned yet ({path.relative_to(config.PROJECT_ROOT)})")
            continue
        found = True
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        flagged = [r for r in rows if r["realistic"] != "Yes" or r["fix_correct"] != "Yes"]
        print(f"\n{RATER_LABELS[e]}: {len(rows)} of 15 checked, {len(flagged)} flagged")
        for r in flagged:
            print(f"  {r['scenario_id']}: realistic={r['realistic']}, fix={r['fix_correct']}  {r['comments']}")
    if found:
        print("\nA scenario judged unrealistic needs its 27 calls re-run before scoring (O1); "
              "a corrected reference fix only changes the specificity score.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--summary", action="store_true", help="list what the returned checks flagged")
    if parser.parse_args().summary:
        return summary()
    path = build()
    print(f"Wrote {path.relative_to(config.PROJECT_ROOT)} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
