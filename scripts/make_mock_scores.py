"""MOCK scores, so the analysis (Steps 7-8) can be built before the real ratings exist.

    python scripts/make_mock_scores.py

Writes results/mock/scores_<rater>.MOCK.csv for researcher_provisional, expert_1
and expert_2: the same items, positions and columns as the real score files, but
status "MOCK", notes "MOCK" and random values.

- The values never depend on the model or the context level, so mock data
  cannot show a real effect; any "effect" in a mock analysis is noise.
- Raters agree with a shared random value about 75% of the time, and repeat
  their own score about 85% of the time, so kappa and the consistency check
  have something to compute.
- Real score files (results/scores_<rater>.csv) are never read or written here.
  The analysis uses the real files and only falls back to these with --mock,
  labelling every output as MOCK.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core.scoring import RATERS, scores_path, write_scores  # noqa: E402
from prepare_scoring import ASSIGNMENTS_PATH  # noqa: E402

WEIGHTS = {"technical_accuracy": (("0", "0.5", "1"), (3, 3, 4)),
           "root_cause_correctness": (("0", "1"), (4, 6)),
           "actionability": (("1", "2", "3"), (3, 4, 3))}
P_AGREE, P_REPEAT_SAME = 0.75, 0.85


def draw(rng: random.Random) -> dict:
    return {k: rng.choices(values, weights)[0] for k, (values, weights) in WEIGHTS.items()}


def main() -> int:
    if not ASSIGNMENTS_PATH.exists():
        print("Run scripts/prepare_scoring.py first.")
        return 1
    assignments = json.loads(ASSIGNMENTS_PATH.read_text())
    shared_rng = random.Random(f"{config.GLOBAL_SEED}:mock")
    shared = {}   # one random "consensus" per item, drawn in sorted order
    for item_id in sorted({o["item_id"] for order in assignments.values() for o in order}):
        shared[item_id] = draw(shared_rng)

    for rater in RATERS:
        rng = random.Random(f"{config.GLOBAL_SEED}:mock:{rater}")
        rows, first = [], {}
        for o in assignments[rater]:
            if o["is_repeat"]:
                values = first[o["item_id"]] if rng.random() < P_REPEAT_SAME else draw(rng)
            else:
                values = shared[o["item_id"]] if rng.random() < P_AGREE else draw(rng)
                first[o["item_id"]] = values
            rows.append({"rater_id": rater, "status": "MOCK", "item_id": o["item_id"],
                         "position": o["position"], "is_repeat": o["is_repeat"], **values,
                         "notes": "MOCK", "scored_at": ""})
        path = scores_path(rater, mock=True)
        write_scores(path, rows)
        print(f"MOCK  {len(rows):3d} rows -> {path.relative_to(config.PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
