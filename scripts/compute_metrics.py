"""Step 7 — automated metrics for every answer.

    python scripts/compute_metrics.py --bands          # first: check the specificity bands on the pilot (D23)
    python scripts/compute_metrics.py                  # all 405 answers
    python scripts/compute_metrics.py --show RC02-05A  # print one blinded answer (for the hallucination review)

Writes
  results/auto_metrics.csv            one row per answer: design factors + metrics (see README)
  results/auto_metrics_meta.json      embedding model and revision, package versions, bands
  results/hallucination_review.csv    one row per hallucination candidate, blinded item ids only.
                                      Fill `verdict` (H / C / N / F, see VERDICTS) and re-run;
                                      filled verdicts are kept.
  results/hallucination_recall_sample.csv   27 answers (3 per model x level, seeded), to read in full
                                      and list what the check missed (written once, never overwritten)
  results/pilot/specificity_bands_check.csv   (--bands) pilot answers vs their own and the 15 study gold standards

Nothing here uses the human scores except --bands, which shows the calibration
scores next to the pilot similarities once they have been imported.
"""
import argparse
import csv
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core import metrics as m  # noqa: E402
from core.scoring import read_scores  # noqa: E402
from prepare_scoring import CALIBRATION_KEY_PATH, KEY_PATH  # noqa: E402
from prompts.builder import LEVELS, PART_FIELDS, load_scenario  # noqa: E402
from run_experiment import OUTPUTS, PILOT_OUTPUTS, has_all_headings, load_records  # noqa: E402

METRICS_PATH = config.RESULTS_DIR / "auto_metrics.csv"
META_PATH = config.RESULTS_DIR / "auto_metrics_meta.json"
REVIEW_PATH = config.RESULTS_DIR / "hallucination_review.csv"
RECALL_PATH = config.RESULTS_DIR / "hallucination_recall_sample.csv"
RECALL_PER_CELL = 3
BANDS_PATH = config.RESULTS_DIR / "pilot" / "specificity_bands_check.csv"
REVIEW_COLUMNS = ["item_id", "entity", "kind", "section", "context", "verdict", "reviewer_note"]
VERDICTS = {"H": "hallucination: stated as an existing entity, but it does not exist",
            "C": "conditional: a hedged guess or example ('if the column is called ...', 'e.g.', 'likely')",
            "N": "new: something the answer proposes to create",
            "F": "false positive: a placeholder, not an entity reference, or the answer says it does not exist"}
NORMAL_STOP = {"end_turn", "completed", "stop"}


def load_truth(scenario_id: str, scenarios_dir: Path) -> dict:
    """ground_truth.json, with what the hallucination check also needs: the scenario's manifest
    nodes (names the project's code defines) and its context parts 1-4 (names the scenario mentions)."""
    folder = scenarios_dir / scenario_id
    truth = json.loads((folder / "ground_truth.json").read_text())
    truth["manifest_nodes"] = json.loads((folder / "manifest_nodes.json").read_text())
    scenario = load_scenario(scenario_id, scenarios_dir)
    truth["context_text"] = "\n".join(scenario[f] for f in PART_FIELDS.values())
    return truth


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def section_of(text: str, pos: int) -> str:
    """Which answer section a character position falls in."""
    current = "preamble"
    offset = 0
    for line in text.splitlines(keepends=True):
        if offset > pos:
            break
        norm = line.strip().lstrip("#*0123456789. ").rstrip(":*").strip().lower()
        if norm in m.HEADINGS:
            current = norm
        offset += len(line)
    return current


# ---------------------------------------------------------------- per-answer metrics
def answer_metrics(rec: dict, truth: dict) -> tuple[dict, list[m.Ref]]:
    """Everything except similarity. Returns the row and the hallucination candidates."""
    text = rec["text"]
    sections = m.split_sections(text)
    known = m.known_entities(truth["valid_entities"], truth["manifest_nodes"], truth["context_text"])
    refs, unknown, parse = m.find_refs(text, known)
    assumptions = sections.get("assumptions", "")
    assumed = [r for r in unknown if m.mentions(assumptions, r.name)]
    candidates = [r for r in unknown if r not in assumed]
    root_cause = sections.get("root cause") or sections.get("preamble", "")
    body = m.similarity_text(text)
    n_words = m.words(body)
    row = {
        "run_id": rec["run_id"], "scenario_id": rec["scenario_id"], "category": rec["category"],
        "root_cause_type": truth["root_cause_type"], "level": rec["level"], "model_key": rec["model_key"],
        "rep": rec["rep"], "input_tokens": rec["input_tokens"], "output_tokens": rec["output_tokens"],
        "words": m.words(text), "all_headings": int(has_all_headings(text)),
        "truncated": int(rec["stop_reason"] not in NORMAL_STOP),
        "key_entity_recall": round(m.key_entity_recall(text, truth["key_entities"]), 4),
        "refs_checked": len(refs), "refs_unknown": len(unknown), "refs_assumed": len(assumed),
        "hallucination_candidates": len(candidates), "hallucination_auto": int(bool(candidates)),
        "sql_parsed": parse["sql_parsed"], "sql_failed": parse["sql_failed"],
        "hedges_root_cause": m.hedges(root_cause),
        "hedges_per_100w": round(100 * m.hedges(body) / n_words, 3) if n_words else 0.0,
        "root_cause_asserted": int(m.hedges(root_cause) == 0),
        "n_assumptions": m.n_assumptions(assumptions),
    }
    return row, candidates


def similarities(embedder: m.Embedder, records: list[dict], golds: dict[str, str]):
    """Matrix of answer x gold-standard cosine similarities, and the gold ids in column order."""
    gold_ids = list(golds)
    answers = embedder.embed([m.similarity_text(r["text"]) for r in records])
    gold_vecs = embedder.embed([golds[g] for g in gold_ids])
    return answers @ gold_vecs.T, gold_ids


# ---------------------------------------------------------------- hallucination review file
def merge_review(new_rows: list[dict]) -> list[dict]:
    """Keep verdicts already filled in; warn about filled rows that are no longer candidates."""
    old = {}
    if REVIEW_PATH.exists():
        with REVIEW_PATH.open(newline="") as f:
            old = {(r["item_id"], r["entity"]): r for r in csv.DictReader(f)}
    keys = {(r["item_id"], r["entity"]) for r in new_rows}
    for row in new_rows:
        prev = old.get((row["item_id"], row["entity"]))
        if prev:
            row["verdict"], row["reviewer_note"] = prev["verdict"].strip().upper(), prev["reviewer_note"]
    lost = [k for k, r in old.items() if k not in keys and r["verdict"].strip()]
    if lost:
        print(f"WARNING: {len(lost)} reviewed rows are no longer candidates and were dropped: {lost[:5]}")
    bad = [r for r in new_rows if r["verdict"] and r["verdict"] not in VERDICTS]
    if bad:
        raise SystemExit(f"Unknown verdicts in {REVIEW_PATH.name} (use {', '.join(VERDICTS)}): "
                         f"{[(r['item_id'], r['entity'], r['verdict']) for r in bad[:5]]}")
    return new_rows


def write_recall_sample(rows: list[dict]) -> None:
    """3 answers per model x level, drawn with the global seed and shuffled, so the file shows
    blinded item ids only. Written once: it holds the researcher's notes."""
    if RECALL_PATH.exists():
        return
    rng = random.Random(f"{config.GLOBAL_SEED}:recall")
    picked = []
    for model in config.MODELS:
        for level in LEVELS:
            cell = sorted(r["item_id"] for r in rows if r["model_key"] == model and r["level"] == level)
            picked += rng.sample(cell, RECALL_PER_CELL)
    rng.shuffle(picked)
    write_csv(RECALL_PATH, [{"item_id": i, "checked": "", "missed_entities": "", "reviewer_note": ""}
                            for i in picked], ["item_id", "checked", "missed_entities", "reviewer_note"])


# ---------------------------------------------------------------- main run
def run_all(embedder: m.Embedder) -> int:
    records = sorted(load_records(OUTPUTS), key=lambda r: r["run_id"])
    run_to_item = {v["run_id"]: k for k, v in json.loads(KEY_PATH.read_text())["items"].items()}
    scenario_ids = sorted({r["scenario_id"] for r in records})
    truths = {sid: load_truth(sid, config.SCENARIOS_DIR) for sid in scenario_ids}
    golds = {sid: m.gold_text(load_scenario(sid)) for sid in scenario_ids}

    print(f"Embedding {len(records)} answers and {len(golds)} gold standards "
          f"({m.EMBED_MODEL} @ {m.EMBED_REVISION[:7]}, CPU) ...")
    sims, gold_ids = similarities(embedder, records, golds)
    n_chunks = [len(embedder.chunks(m.similarity_text(r["text"]))) for r in records]

    rows, review = [], []
    for i, rec in enumerate(records):
        row, candidates = answer_metrics(rec, truths[rec["scenario_id"]])
        own = gold_ids.index(rec["scenario_id"])
        others = [float(s) for j, s in enumerate(sims[i]) if j != own]
        spec = round(float(sims[i, own]), 4)     # the band is taken from the value as written
        item = run_to_item[rec["run_id"]]
        row = {"run_id": rec["run_id"], "item_id": item, **{k: v for k, v in row.items() if k != "run_id"},
               "specificity": spec, "specificity_band": m.band(spec),
               "sim_other_mean": round(statistics.mean(others), 4), "sim_other_max": round(max(others), 4),
               "own_gold_rank": 1 + sum(o > spec for o in others), "chunks": n_chunks[i]}
        rows.append(row)
        for ref in candidates:
            review.append({"item_id": item, "entity": ref.entity, "kind": ref.kind,
                           "section": section_of(rec["text"], ref.pos),
                           "context": m.context(rec["text"], ref.pos), "verdict": "", "reviewer_note": ""})

    review = merge_review(sorted(review, key=lambda r: (r["item_id"], r["entity"])))
    by_item: dict[str, list[str]] = {}
    for r in review:
        by_item.setdefault(r["item_id"], []).append(r["verdict"])
    for row in rows:
        verdicts = by_item.get(row["item_id"], [])
        complete = all(verdicts)
        row["hallucinations_confirmed"] = sum(v == "H" for v in verdicts) if complete else ""

    columns = ["run_id", "item_id", "scenario_id", "category", "root_cause_type", "level", "model_key", "rep",
               "input_tokens", "output_tokens", "words", "all_headings", "truncated",
               "specificity", "specificity_band", "sim_other_mean", "sim_other_max", "own_gold_rank", "chunks",
               "key_entity_recall", "refs_checked", "refs_unknown", "refs_assumed",
               "hallucination_candidates", "hallucination_auto", "hallucinations_confirmed",
               "sql_parsed", "sql_failed",
               "hedges_root_cause", "hedges_per_100w", "root_cause_asserted", "n_assumptions"]
    write_csv(METRICS_PATH, rows, columns)
    write_csv(REVIEW_PATH, review, REVIEW_COLUMNS)
    write_recall_sample(rows)
    META_PATH.write_text(json.dumps({
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "answers": len(rows), "embedding_model": m.EMBED_MODEL, "embedding_revision": m.EMBED_REVISION,
        "max_tokens_per_chunk": embedder.limit, "bands": {name: cut for cut, name in m.BANDS},
        "similarity_text": "answer without its Assumptions section vs gold root_cause + fix + verification",
        "versions": {p: version(p) for p in ("sentence-transformers", "torch", "transformers", "sqlglot")},
        "review_verdicts": VERDICTS,
    }, indent=2) + "\n")

    report(rows, review)
    return 0


def report(rows: list[dict], review: list[dict]) -> None:
    rel = lambda p: p.relative_to(config.PROJECT_ROOT)  # noqa: E731
    print(f"\nWrote {rel(METRICS_PATH)} ({len(rows)} rows), {rel(REVIEW_PATH)} ({len(review)} candidates)")
    multi = sum(r["chunks"] > 1 for r in rows)
    print(f"Answers embedded in more than one chunk: {multi}/{len(rows)}")
    parsed, failed = sum(r["sql_parsed"] for r in rows), sum(r["sql_failed"] for r in rows)
    print(f"SQL statements parsed for the column check: {parsed} ({failed} could not be parsed, skipped)")

    print("\nSpecificity (cosine to own gold standard): median [min-max], and % of answers whose own gold is the closest")
    print(f"{'model':8}" + "".join(f"{lvl:>26}" for lvl in LEVELS))
    for model in config.MODELS:
        cells = []
        for lvl in LEVELS:
            s = [r["specificity"] for r in rows if r["model_key"] == model and r["level"] == lvl]
            top = sum(r["own_gold_rank"] == 1 for r in rows if r["model_key"] == model and r["level"] == lvl)
            cells.append(f"{statistics.median(s):.3f} [{min(s):.2f}-{max(s):.2f}] {100 * top / len(s):3.0f}%")
        print(f"{model:8}" + "".join(f"{c:>26}" for c in cells))
    bands = {b: sum(r["specificity_band"] == b for r in rows) for b in ("high", "moderate", "low")}
    print(f"Bands over all answers: {bands};  off-target similarity: median "
          f"{statistics.median(r['sim_other_mean'] for r in rows):.3f}, max {max(r['sim_other_max'] for r in rows):.3f}")

    print("\nAnswers with at least one hallucination candidate (automated, before review)")
    print(f"{'model':8}" + "".join(f"{lvl:>10}" for lvl in LEVELS))
    for model in config.MODELS:
        cells = [sum(r["hallucination_auto"] for r in rows if r["model_key"] == model and r["level"] == lvl)
                 for lvl in LEVELS]
        print(f"{model:8}" + "".join(f"{c:>7}/45" for c in cells))
    reviewed = sum(bool(r["verdict"]) for r in review)
    with RECALL_PATH.open(newline="") as f:
        recall = list(csv.DictReader(f))
    print(f"Review: {reviewed}/{len(review)} candidates have a verdict; "
          f"recall sample: {sum(bool(r['checked'].strip()) for r in recall)}/{len(recall)} answers read.")

    print("\nRoot cause stated without any hedge word (share of answers)")
    for model in config.MODELS:
        cells = [statistics.mean(r["root_cause_asserted"] for r in rows
                                 if r["model_key"] == model and r["level"] == lvl) for lvl in LEVELS]
        print(f"{model:8}" + "".join(f"{100 * c:>9.0f}%" for c in cells))


# ---------------------------------------------------------------- band check on the pilot (D23)
def band_check(embedder: m.Embedder) -> int:
    pilot = sorted(load_records(PILOT_OUTPUTS), key=lambda r: r["run_id"])
    cal_items = {v["run_id"]: k for k, v in json.loads(CALIBRATION_KEY_PATH.read_text())["items"].items()}
    study_ids = sorted(p.name for p in config.SCENARIOS_DIR.iterdir() if (p / "scenario.json").exists())
    golds = {"PL01": m.gold_text(load_scenario("PL01", config.PILOT_DIR))}
    golds.update({sid: m.gold_text(load_scenario(sid)) for sid in study_ids})
    sims, gold_ids = similarities(embedder, pilot, golds)

    scores = {}
    for path in sorted((config.RESULTS_DIR / "pilot").glob("calibration_scores_*.csv")):
        for s in read_scores(path):
            scores.setdefault(s["item_id"], []).append(
                f"{s['rater_id']}: TA {s['technical_accuracy']} RC {s['root_cause_correctness']} "
                f"ACT {s['actionability']}")

    rows = []
    for n, (rec, sim_row) in enumerate(zip(pilot, sims), start=1):
        own = round(float(sim_row[0]), 4)
        off = [float(s) for s in sim_row[1:]]
        item = cal_items.get(rec["run_id"], "")
        rows.append({"pilot_answer": f"P{n}", "calibration_item": item,
                     "own_similarity": round(own, 4), "own_band": m.band(own),
                     "off_target_median": round(statistics.median(off), 4), "off_target_max": round(max(off), 4),
                     "closest_study_gold": gold_ids[1 + max(range(len(off)), key=off.__getitem__)],
                     "calibration_scores": " | ".join(scores.get(item, []))})
    write_csv(BANDS_PATH, rows, list(rows[0]))

    off_all = [float(s) for row in sims for s in row[1:]]
    print(f"Pilot answers (PL01, n={len(pilot)}): similarity to their own gold standard, and to the "
          f"{len(study_ids)} study gold standards (wrong scenario)")
    print(f"{'answer':7}{'calib.':10}{'own':>7}{'band':>10}{'off med':>9}{'off max':>9}  scores")
    for r in rows:
        print(f"{r['pilot_answer']:7}{r['calibration_item'] or '-':10}{r['own_similarity']:7.3f}{r['own_band']:>10}"
              f"{r['off_target_median']:9.3f}{r['off_target_max']:9.3f}  {r['calibration_scores'] or '(not scored yet)'}")
    own_all = [r["own_similarity"] for r in rows]
    print(f"\nOwn gold:   median {statistics.median(own_all):.3f}, range {min(own_all):.3f}-{max(own_all):.3f}")
    print(f"Wrong gold: median {statistics.median(off_all):.3f}, range {min(off_all):.3f}-{max(off_all):.3f}, "
          f"{100 * sum(s >= 0.5 for s in off_all) / len(off_all):.0f}% at or above 0.5")
    rule = max(off_all) < 0.75 and statistics.median(off_all) < 0.5
    print("Pre-set rule (D26): no wrong-scenario similarity >= 0.75 and median wrong-scenario similarity < 0.5")
    print("-> proposal bands CONFIRMED" if rule else "-> proposal bands NOT confirmed by the rule")
    p95 = statistics.quantiles(off_all, n=20, method="inclusive")[-1]
    print(f"Wrong-scenario 95th percentile: {p95:.3f} -> bands used (D26, option A): "
          + ", ".join(f"{name} >= {cut}" for cut, name in m.BANDS) + ", low below")
    print(f"Wrote {BANDS_PATH.relative_to(config.PROJECT_ROOT)}")
    return 0


def show(item_id: str) -> int:
    key = json.loads(KEY_PATH.read_text())["items"]
    if item_id not in key:
        print(f"Unknown item id {item_id}")
        return 1
    run_id = key[item_id]["run_id"]
    rec = next(r for r in load_records(OUTPUTS) if r["run_id"] == run_id)
    print(f"=== {item_id} ===\n{rec['text']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bands", action="store_true", help="check the specificity bands on the pilot answers")
    parser.add_argument("--show", metavar="ITEM_ID", help="print one blinded answer")
    args = parser.parse_args()
    if args.show:
        return show(args.show)
    embedder = m.Embedder()
    return band_check(embedder) if args.bands else run_all(embedder)


if __name__ == "__main__":
    sys.exit(main())
