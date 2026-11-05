"""Step 6 — blind the 405 answers and build everything the raters need.

    python scripts/prepare_scoring.py

Blinding (seeded with GLOBAL_SEED, so re-running gives identical files):
- Per scenario, its 9 (context level, repetition) combinations get random group
  numbers 01-09, and within each group the 3 models get random labels A/B/C.
  Item id = <scenario>-<group><label>, e.g. "RC02-05A". Neither the group nor
  the label says anything about the model or the context level.
- Expert set (D6): per scenario and level one repetition is drawn at random:
  15 x 3 x 3 = 135 items (one per scenario x level x model).
- Expert split (D30): per scenario and level, one of the 3 answers goes to both
  experts (45 shared, for agreement) and each expert gets one of the other two
  (45 each). Each expert scores 90, grouped by scenario (read it once, then its
  6 answers); every model appears once per scenario in each part. No repeats.
- The researcher's 405 come in their own shuffled order.

Writes
  results/blinding_key.json              item id -> run, model, level, rep (never send to raters)
  results/scoring/assignments.json       each rater's items in order
  results/scoring/pages/score_expert_1.html, score_expert_2.html   offline pages to send (90 items each)
  results/scoring/pages/calibration.html the 5 pilot samples for the calibration call
  results/pilot/calibration_key.json     key for those 5 samples
Refuses to run if an existing key would change (scores already made would no longer match).
"""
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core`/`prompts`/scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core.scoring import EXPERTS, N_PER_EXPERT, N_SHARED, RATER_LABELS, RESEARCHER, RUBRIC, STATUS  # noqa: E402
from prompts.builder import HEADINGS, LEVELS, load_scenario  # noqa: E402
from run_experiment import OUTPUTS, PILOT_OUTPUTS, REPS, load_records  # noqa: E402

KEY_PATH = config.RESULTS_DIR / "blinding_key.json"
ASSIGNMENTS_PATH = config.SCORING_DIR / "assignments.json"
PAGES_DIR = config.SCORING_DIR / "pages"
CALIBRATION_KEY_PATH = config.RESULTS_DIR / "pilot" / "calibration_key.json"
TEMPLATE = config.PROJECT_ROOT / "core" / "templates" / "scoring_page.html"
N_CALIBRATION = 5


# ---------------------------------------------------------------- blinding
def blind(records: list[dict], seed: int) -> dict[str, dict]:
    """item_id -> what it really is. Deterministic for a given seed and set of answers."""
    rng = random.Random(seed)
    runs = {(r["scenario_id"], r["level"], r["rep"], r["model_key"]): r["run_id"] for r in records}
    key = {}
    for sid in sorted({r["scenario_id"] for r in records}):
        reps = sorted({r["rep"] for r in records if r["scenario_id"] == sid})
        combos = [(level, rep) for level in LEVELS for rep in reps]
        rng.shuffle(combos)
        for group, (level, rep) in enumerate(combos, start=1):
            models = list(config.MODELS)
            rng.shuffle(models)
            for label, model in zip("ABC", models):
                key[f"{sid}-{group:02d}{label}"] = {
                    "run_id": runs[(sid, level, rep, model)], "scenario_id": sid, "level": level,
                    "rep": rep, "model_key": model, "label": label, "group": group, "expert_set": False}
        for level in LEVELS:   # one repetition per scenario x level goes to the experts
            chosen = rng.choice(reps)
            for item in key.values():
                if item["scenario_id"] == sid and item["level"] == level and item["rep"] == chosen:
                    item["expert_set"] = True
    return key


def rater_order(item_ids: list[str], rater_id: str, seed: int) -> list[dict]:
    """The researcher's items in a shuffled order."""
    rng = random.Random(f"{seed}:{rater_id}")
    ids = sorted(item_ids)
    rng.shuffle(ids)
    return [{"position": n, "item_id": i, "is_repeat": 0} for n, i in enumerate(ids, start=1)]


def expert_orders(key: dict, seed: int) -> dict[str, list[dict]]:
    """D30. Per scenario the 3 models are put in a random order m0 m1 m2; at level i the answer of model
    m_i is shared, expert_1 also gets m_(i+1) and expert_2 m_(i+2). So each expert sees every model once
    per scenario in the shared part and once in their own part. Each expert's answers are grouped by
    scenario (6 per scenario); scenario order and order within a scenario are shuffled per expert."""
    rng = random.Random(f"{seed}:expert-split")
    cell = {(v["scenario_id"], v["level"], v["model_key"]): i for i, v in key.items() if v["expert_set"]}
    blocks = {e: defaultdict(list) for e in EXPERTS}
    for sid in sorted({v["scenario_id"] for v in key.values()}):
        models = list(config.MODELS)
        rng.shuffle(models)
        for i, level in enumerate(LEVELS):
            for k, e in enumerate(EXPERTS, start=1):
                blocks[e][sid] += [(cell[(sid, level, models[i])], 1),
                                   (cell[(sid, level, models[(i + k) % len(models)])], 0)]
    orders = {}
    for e in EXPERTS:
        rng_e = random.Random(f"{seed}:{e}")
        scenarios = sorted(blocks[e])
        rng_e.shuffle(scenarios)
        order = []
        for sid in scenarios:
            block = sorted(blocks[e][sid])
            rng_e.shuffle(block)
            order += [{"item_id": i, "is_repeat": 0, "shared": shared} for i, shared in block]
        orders[e] = [{"position": n, **o} for n, o in enumerate(order, start=1)]
    return orders


# ---------------------------------------------------------------- pages
def scenario_view(scenarios_dir=None) -> dict:
    """What raters see for each scenario: the full context (parts 1-4) and the reference fix.
    The same for every item, so the page never shows which context level an LLM had (D7)."""
    folder = scenarios_dir or config.SCENARIOS_DIR
    view = {}
    for path in sorted(folder.glob("*/scenario.json")):
        s = load_scenario(path.parent.name, folder)
        view[s["scenario_id"]] = {
            "sections": [[HEADINGS[1].lstrip("# "), s["failure_description"], True],
                         [HEADINGS[2].lstrip("# "), s["model_metadata"], False],
                         [HEADINGS[3].lstrip("# "), s["lineage"], False],
                         [HEADINGS[4].lstrip("# "), s["historical_context"], False]],
            "reference": s["gold_standard_remediation"]["text"],
        }
    return view


def write_page(path: Path, page: dict, scenarios: dict, items: list[dict]) -> None:
    used = {it["scenario_id"] for it in items}
    data = {"page": page, "rubric": RUBRIC, "items": items,
            "scenarios": {k: v for k, v in scenarios.items() if k in used}}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # cannot close the <script> tag
    html = TEMPLATE.read_text().replace("__TITLE__", page["title"]).replace("__DATA__", blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def page_items(order: list[dict], key: dict, texts: dict) -> list[dict]:
    """What the page shows per item, with its place among the answers to the same scenario."""
    sizes = Counter(key[o["item_id"]]["scenario_id"] for o in order)
    seen = Counter()
    items = []
    for o in order:
        sid = key[o["item_id"]]["scenario_id"]
        seen[sid] += 1
        items.append({"position": o["position"], "item_id": o["item_id"], "is_repeat": o["is_repeat"],
                      "scenario_id": sid, "label": key[o["item_id"]]["label"], "group_pos": seen[sid],
                      "group_size": sizes[sid], "text": texts[key[o["item_id"]]["run_id"]]})
    return items


def page_id(rater_id: str, order: list[dict]) -> str:
    return rater_id + "-" + hashlib.sha256(json.dumps(order).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- main
def main() -> int:
    seed = config.GLOBAL_SEED
    records = load_records(OUTPUTS)
    expected = 15 * len(LEVELS) * len(config.MODELS) * len(REPS)
    if len({r["run_id"] for r in records}) != expected:
        print(f"Need all {expected} answers in {OUTPUTS.name}; found {len(records)}. Run the experiment first.")
        return 1
    texts = {r["run_id"]: r["text"] for r in records}

    key = blind(records, seed)
    if KEY_PATH.exists():
        old = json.loads(KEY_PATH.read_text())["items"]
        if old != key:
            print(f"STOP: {KEY_PATH.name} exists and would change. Scores made with it would no longer match.")
            return 1
    KEY_PATH.write_text(json.dumps({"seed": seed, "note": "Researcher only. Never send to raters.",
                                    "items": key}, indent=1) + "\n")

    expert_ids = [i for i, v in key.items() if v["expert_set"]]
    assignments = {RESEARCHER: rater_order(list(key), RESEARCHER, seed), **expert_orders(key, seed)}
    config.SCORING_DIR.mkdir(parents=True, exist_ok=True)
    ASSIGNMENTS_PATH.write_text(json.dumps(assignments, indent=1) + "\n")

    scenarios = scenario_view()
    for e in EXPERTS:
        order = assignments[e]
        write_page(PAGES_DIR / f"score_{e}.html", {
            "id": page_id(e, order), "kind": "scoring", "rater_id": e, "status": STATUS[e],
            "file_prefix": "scores_", "title": f"RPDA8411 scoring — {RATER_LABELS[e]}",
            "banner": ("The answers are grouped by scenario: read the scenario once, then score its 6 answers. "
                       "Your scores are saved in this browser as you go. Click <b>Export CSV</b> at the end of "
                       "each session and email the file to the researcher. To continue in another browser, "
                       "use <b>Load CSV</b> with your last export."),
        }, scenarios, page_items(order, key, texts))

    # ---- calibration page: 5 of the 9 pilot answers (PL01), excluded from the results
    pilot = load_records(PILOT_OUTPUTS)
    if len(pilot) != len(LEVELS) * len(config.MODELS):
        print(f"Need the 9 pilot answers in {PILOT_OUTPUTS.name}; run run_experiment.py --pilot first.")
        return 1
    pilot_key = blind(pilot, seed)
    chosen = sorted(random.Random(f"{seed}:calibration").sample(sorted(pilot_key), N_CALIBRATION))
    cal_key = {i: pilot_key[i] for i in chosen}
    CALIBRATION_KEY_PATH.write_text(json.dumps({"seed": seed, "items": cal_key}, indent=1) + "\n")
    cal_order = [{"position": n, "item_id": i, "is_repeat": 0} for n, i in enumerate(chosen, start=1)]
    write_page(PAGES_DIR / "calibration.html", {
        "id": page_id("calibration", cal_order), "kind": "calibration", "rater_id": None,
        "status": "CALIBRATION", "file_prefix": "calibration_", "raters":
            [[r, RATER_LABELS[r]] for r in (*EXPERTS, RESEARCHER)],
        "title": "RPDA8411 calibration — 5 sample outputs",
        "banner": ("Calibration samples from a pilot scenario. They are <b>not part of the results</b>. Choose who "
                   "is scoring at the top, score all 5 on your own, then compare and discuss."),
    }, scenario_view(config.PILOT_DIR), page_items(cal_order, cal_key, {r["run_id"]: r["text"] for r in pilot}))

    by_scn = defaultdict(int)
    for i in expert_ids:
        by_scn[key[i]["scenario_id"]] += 1
    print(f"blinding key: {len(key)} items -> {KEY_PATH.relative_to(config.PROJECT_ROOT)}")
    shared = sum(o["shared"] for o in assignments[EXPERTS[0]])
    print(f"expert set: {len(expert_ids)} items ({sorted(set(by_scn.values()))} per scenario); each expert page "
          f"has {len(assignments[EXPERTS[0]])} items ({shared} shared by both experts)")
    assert shared == N_SHARED and all(len(assignments[e]) == N_PER_EXPERT for e in EXPERTS)
    for p in sorted(PAGES_DIR.glob("*.html")):
        print(f"  {p.relative_to(config.PROJECT_ROOT)}  {p.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
