"""Step 6 — score all 405 answers yourself, as rater researcher_provisional (PROVISIONAL).

    python scripts/score_tool.py              # continue where you stopped
    python scripts/score_tool.py --context    # print the full scenario context with every item

For each item it shows the failure report, the reference fix and the suggestion,
labelled only "Model A/B/C", then asks for the three scores and an optional note.
Each item is appended to results/scores_researcher_provisional.csv as soon as you
finish it, so you can quit at any time and resume later. Items come in your own
shuffled order (results/scoring/assignments.json); run prepare_scoring.py first.

At any score question:  c = full scenario context   r = rubric   q = quit
"""
import argparse
import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core.scoring import PROVISIONAL_LABEL, RESEARCHER, RUBRIC, STATUS, VALID, append_score, read_scores, scores_path  # noqa: E402
from prepare_scoring import ASSIGNMENTS_PATH, KEY_PATH, scenario_view  # noqa: E402
from run_experiment import OUTPUTS, load_records  # noqa: E402

LINE = "=" * 78


class Quit(Exception):
    pass


def section(title: str, text: str) -> str:
    return f"\n--- {title} ---\n{text.strip()}\n"


def rubric_text() -> str:
    out = ["", "RUBRIC", *RUBRIC["general"]]
    for d in RUBRIC["dimensions"]:
        out.append(f"* {d['name']} ({d['scale']}): {d['question']}")
    out.append("Actionability anchors — " + RUBRIC["anchor_failure"])
    out += [f"  {a['score']}: {a['example']}  [{a['why']}]" for a in RUBRIC["anchors"]]
    out += [f"- {r}" for r in RUBRIC["rules"]]
    return "\n".join(textwrap.fill(line, 100, subsequent_indent="    ") for line in out) + "\n"


def ask(question: str, allowed: tuple[str, ...], context: str) -> str:
    aliases = {".5": "0.5", "0,5": "0.5"}
    while True:
        try:
            answer = input(f"{question} [{' / '.join(allowed)}]: ").strip().lower()
        except EOFError:
            raise Quit
        answer = aliases.get(answer, answer)
        if answer in allowed:
            return answer
        if answer == "c":
            print(context)
        elif answer == "r":
            print(rubric_text())
        elif answer == "q":
            raise Quit
        else:
            print(f"  type one of {', '.join(allowed)} (or c / r / q)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", action="store_true", help="print the full scenario context every time")
    parser.add_argument("--out", type=Path, default=scores_path(RESEARCHER), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not (ASSIGNMENTS_PATH.exists() and KEY_PATH.exists()):
        print("Run scripts/prepare_scoring.py first.")
        return 1
    order = json.loads(ASSIGNMENTS_PATH.read_text())[RESEARCHER]
    key = json.loads(KEY_PATH.read_text())["items"]
    texts = {r["run_id"]: r["text"] for r in load_records(OUTPUTS)}
    scenarios = scenario_view()

    done = {int(r["position"]) for r in read_scores(args.out)} if args.out.exists() else set()
    todo = [o for o in order if o["position"] not in done]
    print(f"{LINE}\n{PROVISIONAL_LABEL}\n{len(done)} of {len(order)} scored; saving to "
          f"{args.out.name}. Keys: c = context, r = rubric, q = quit.\n{LINE}")
    try:
        for o in todo:
            item = key[o["item_id"]]
            scn = scenarios[item["scenario_id"]]
            failure, *rest = scn["sections"]
            context = "".join(section(title, text) for title, text, _ in rest)
            print(f"\n{LINE}\nPROVISIONAL · item {o['position']} of {len(order)} · Scenario {item['scenario_id']} · "
                  f"Model {item['label']}   [{o['item_id']}]\n{LINE}")
            print(section(failure[0], failure[1]) + (context if args.context else ""))
            print(section("Reference fix (researcher)", scn["reference"]))
            print(section(f"Suggestion (Model {item['label']})", texts[item["run_id"]]))
            row = {"rater_id": RESEARCHER, "status": STATUS[RESEARCHER], "item_id": o["item_id"],
                   "position": o["position"], "is_repeat": o["is_repeat"]}
            row["technical_accuracy"] = ask("Technical accuracy", VALID["technical_accuracy"], context)
            row["root_cause_correctness"] = ask("Root cause correct", VALID["root_cause_correctness"], context)
            row["actionability"] = ask("Actionability", VALID["actionability"], context)
            try:
                row["notes"] = input("Notes (Enter to skip): ").strip()
            except EOFError:
                raise Quit
            row["scored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            append_score(args.out, row)
            done.add(o["position"])
    except (Quit, KeyboardInterrupt):
        print("\nStopped; the current item was not saved.")
    print(f"{len(done)} of {len(order)} scored ({PROVISIONAL_LABEL}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
