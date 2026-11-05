"""Step 6 — check a rater's exported CSV and save it as their score file.

    python scripts/import_scores.py expert_1 ~/Downloads/scores_expert_1.csv
    python scripts/import_scores.py expert_2 ~/Downloads/calibration_expert_2.csv --calibration

Checks that every row belongs to this rater, matches the item at that position
on their page, has valid scores, and appears once. Then saves it as
results/scores_<rater>.csv (calibration: results/pilot/calibration_scores_<rater>.csv).
Each export contains everything scored so far, so a later export replaces the
earlier one; it refuses if the new file has fewer scores than the saved one
(pass --force if that is really intended).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core.scoring import EXPERTS, RATERS, read_scores, scores_path, write_scores  # noqa: E402
from prepare_scoring import ASSIGNMENTS_PATH, CALIBRATION_KEY_PATH  # noqa: E402


def expected_items(rater: str, calibration: bool) -> dict[int, str]:
    """position -> item_id on this rater's page."""
    if calibration:
        ids = sorted(json.loads(CALIBRATION_KEY_PATH.read_text())["items"])
        return {n: i for n, i in enumerate(ids, start=1)}
    return {o["position"]: o["item_id"] for o in json.loads(ASSIGNMENTS_PATH.read_text())[rater]}


def check(rows: list[dict], rater: str, expected: dict[int, str], status: str) -> list[str]:
    problems, seen = [], set()
    for r in rows:
        pos = int(r["position"])
        if r["status"] != status:   # e.g. a MOCK file must never become a real score file
            problems.append(f"position {pos}: status {r['status']!r}, expected {status!r}")
        if r["rater_id"] != rater:
            problems.append(f"position {pos}: rater_id {r['rater_id']!r}, expected {rater!r}")
        if expected.get(pos) != r["item_id"]:
            problems.append(f"position {pos}: item {r['item_id']} is not on this rater's page at that position")
        if pos in seen:
            problems.append(f"position {pos} appears twice")
        seen.add(pos)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rater", choices=RATERS)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--calibration", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, help=argparse.SUPPRESS)  # tests only
    args = parser.parse_args()
    if not args.calibration and args.rater not in EXPERTS:
        parser.error("the researcher's scores come from score_tool.py; only calibration scores are imported")

    rows = read_scores(args.csv)          # validates columns and score values
    expected = expected_items(args.rater, args.calibration)
    problems = check(rows, args.rater, expected, "CALIBRATION" if args.calibration else "EXPERT")
    if problems:
        print("NOT IMPORTED:\n  " + "\n  ".join(problems[:20]))
        return 1

    target = args.out or (config.RESULTS_DIR / "pilot" / f"calibration_scores_{args.rater}.csv" if args.calibration
              else scores_path(args.rater))
    if target.exists() and not args.force:
        before = len(read_scores(target))
        if len(rows) < before:
            print(f"NOT IMPORTED: {args.csv.name} has {len(rows)} scores but {target.name} already has {before}. "
                  "Use the latest export, or --force.")
            return 1
    write_scores(target, sorted(rows, key=lambda r: int(r["position"])))
    repeats = sum(r["is_repeat"] == "1" for r in rows)
    print(f"Imported {len(rows)} of {len(expected)} items ({repeats} consistency repeats) "
          f"-> {target}")
    missing = sorted(set(expected) - {int(r["position"]) for r in rows})
    if missing:
        print(f"Still unscored: {len(missing)} items (positions {missing[:10]}{' ...' if len(missing) > 10 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
