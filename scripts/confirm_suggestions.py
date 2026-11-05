"""Confirm or change the AI-suggested hallucination verdicts, one at a time (D27, AI-assisted review).

    python scripts/confirm_suggestions.py            # the 62 flagged references
    python scripts/confirm_suggestions.py --recall   # the 27 recall-sample answers (read each in full)

Each row shows the evidence and the suggestion. Press Enter to accept it, or type your own answer.
Your answer goes into results/hallucination_review.csv (verdict) or
results/hallucination_recall_sample.csv (checked, missed_entities), and the note records whether you
accepted or changed the suggestion. Saved after every row; rows you already answered are skipped,
so you can stop (q) and come back. Blinded item ids only.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from compute_metrics import RECALL_PATH, REVIEW_COLUMNS, REVIEW_PATH, VERDICTS, write_csv  # noqa: E402
from prepare_scoring import KEY_PATH  # noqa: E402
from run_experiment import OUTPUTS, load_records  # noqa: E402

SUGGESTIONS = config.RESULTS_DIR / "hallucination_suggestions.csv"
RECALL_SUGGESTIONS = config.RESULTS_DIR / "hallucination_recall_suggestions.csv"
RECALL_COLUMNS = ["item_id", "checked", "missed_entities", "reviewer_note"]


def read(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def note(old: str, suggested: str, answer: str) -> str:
    """Audit trail: did the researcher accept the suggestion or change it?"""
    shown = suggested or "nothing"
    text = f"suggested {shown}, accepted" if answer == suggested else f"suggested {shown}, changed to {answer or 'nothing'}"
    return f"{old}; {text}" if old.strip() else text


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def review_flags() -> int:
    rows = read(REVIEW_PATH)
    suggested = {(s["item_id"], s["entity"]): s for s in read(SUGGESTIONS)}
    todo = [r for r in rows if not r["verdict"].strip()]
    print(f"{len(rows) - len(todo)} of {len(rows)} done. Verdicts:")
    for v, meaning in VERDICTS.items():
        print(f"  {v}  {meaning}")
    for n, row in enumerate(todo, start=1):
        s = suggested[(row["item_id"], row["entity"])]
        print(f"\n--- {n}/{len(todo)}  {row['item_id']}  `{row['entity']}`  ({row['kind']}, {row['section']} section)")
        print(f"... {row['context']} ...")
        print(f"Suggested: {s['suggested_verdict']}  ({s['reason']})")
        while True:
            answer = ask("Enter = accept, or H / C / N / F, s = skip, q = quit: ").upper()
            if answer in ("", *VERDICTS, "S", "Q"):
                break
        if answer == "Q":
            break
        if answer == "S":
            continue
        verdict = answer or s["suggested_verdict"]
        row["verdict"] = verdict
        row["reviewer_note"] = note(row["reviewer_note"], s["suggested_verdict"], verdict)
        write_csv(REVIEW_PATH, rows, REVIEW_COLUMNS)
    left = sum(1 for r in rows if not r["verdict"].strip())
    print(f"\nSaved. {len(rows) - left} of {len(rows)} done." + ("" if left else " All reviewed: re-run analyse.py."))
    return 0


def review_recall() -> int:
    rows = read(RECALL_PATH)
    suggested = {s["item_id"]: s for s in read(RECALL_SUGGESTIONS)}
    flagged = {}
    for r in read(REVIEW_PATH):
        flagged.setdefault(r["item_id"], []).append(f"{r['entity']} ({r['verdict'] or 'no verdict yet'})")
    key = json.loads(KEY_PATH.read_text())["items"]
    texts = {rec["run_id"]: rec["text"] for rec in load_records(OUTPUTS)}
    todo = [r for r in rows if not r["checked"].strip()]
    print(f"{len(rows) - len(todo)} of {len(rows)} done. Read each answer in full and list every model, column,\n"
          "file, dbt setting or SQL function it states as existing that does not exist and is NOT already flagged.\n"
          "Ignore hedged examples, things it proposes to create, and anything under Assumptions.")
    for n, row in enumerate(todo, start=1):
        s = suggested[row["item_id"]]
        print(f"\n{'=' * 70}\n{n}/{len(todo)}  {row['item_id']}\n{'=' * 70}")
        print(texts[key[row["item_id"]]["run_id"]])
        print(f"\nAlready flagged: {', '.join(flagged.get(row['item_id'], [])) or 'nothing'}")
        print(f"Suggested missed: {s['suggested_missed'] or 'nothing'}  ({s['reason']})")
        answer = ask("Enter = accept, '-' = nothing missed, or type the missed names separated by ';', "
                     "s = skip, q = quit: ")
        if answer.lower() == "q":
            break
        if answer.lower() == "s":
            continue
        missed = s["suggested_missed"] if answer == "" else ("" if answer == "-" else answer)
        row["checked"] = "yes"
        row["missed_entities"] = missed
        row["reviewer_note"] = note(row["reviewer_note"], s["suggested_missed"], missed)
        write_csv(RECALL_PATH, rows, RECALL_COLUMNS)
    left = sum(1 for r in rows if not r["checked"].strip())
    print(f"\nSaved. {len(rows) - left} of {len(rows)} done." + ("" if left else " All read: re-run analyse.py."))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--recall", action="store_true", help="the recall sample instead of the flagged references")
    args = parser.parse_args()
    return review_recall() if args.recall else review_flags()


if __name__ == "__main__":
    sys.exit(main())
