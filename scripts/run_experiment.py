"""Step 5 — run the experiment: 15 scenarios x 3 context levels x 3 models x 3 reps = 405 calls.

    python scripts/run_experiment.py --dry-run             # plan + cost estimate, no calls
    python scripts/run_experiment.py --scenarios SD01      # CHECKPOINT 5: one scenario (27 calls)
    python scripts/run_experiment.py                       # every call not yet done
    python scripts/run_experiment.py --models llama        # only some models
    python scripts/run_experiment.py --summary             # summarise what has run so far
    python scripts/run_experiment.py --pilot               # calibration scenario PL01, 1 rep (9 calls)

How it works
- Every answer is appended to results/raw_outputs.jsonl (one JSON line) the
  moment it arrives, so nothing is lost if the run stops.
- Resumable: a call whose run_id (e.g. "SD01-full-claude-r2") is already in the
  file is skipped. Failed calls go to results/errors.jsonl instead and are
  simply tried again on the next run.
- If the file holds an answer made with a different prompt (SHA-256) or a
  different pinned model ID, the script refuses to continue: mixing versions
  would contaminate the data.
- Settings come from core/config.py and are identical for every call
  (temperature, max output tokens). Retries with exponential backoff are in
  core/llm_clients.call_with_retry.
- The three models run in parallel (one worker thread each), each working
  through its own calls in a seeded random order, so time-of-day effects
  are not confounded with scenario or context level.
- Before any call it prints a cost estimate and asks for "yes" (or pass --yes).
- Ctrl-C stops cleanly after the calls in progress have been saved.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import random
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core`/`prompts` importable

from core import config  # noqa: E402
from prompts.builder import (LEVELS, PROMPT_VERSION, approx_tokens, build_prompt,  # noqa: E402
                             load_scenario, prompt_sha256)

OUTPUTS = config.RESULTS_DIR / "raw_outputs.jsonl"
ERRORS = config.RESULTS_DIR / "errors.jsonl"
# --pilot: calibration samples for the evaluators (D9); kept apart from the results
PILOT_OUTPUTS = config.RESULTS_DIR / "pilot" / "raw_outputs_pilot.jsonl"
PILOT_ERRORS = config.RESULTS_DIR / "pilot" / "errors_pilot.jsonl"
LOCK = config.RESULTS_DIR / ".run.lock"
REPS = (1, 2, 3)

# Used for the estimate until real answers exist; then the measured means are used.
DEFAULT_OUTPUT_TOKENS = 900
DEFAULT_SECONDS_PER_CALL = {"gpt": 20, "claude": 25, "llama": 45}

TRUNCATED = {"max_tokens", "length", "incomplete:max_output_tokens"}
HEADINGS = ("root cause", "fix", "verification", "assumptions")


# ---------------------------------------------------------------- plan
def all_scenario_ids(scenarios_dir=None) -> list[str]:
    folder = scenarios_dir or config.SCENARIOS_DIR
    return sorted(p.name for p in folder.iterdir() if (p / "scenario.json").exists())


def llama_seed(rep: int) -> int:
    """Different seed per repetition (42, 43, 44), else llama's 3 reps would be identical."""
    return config.GLOBAL_SEED + rep - 1


def plan_calls(scenario_ids: list[str], model_keys: list[str], scenarios_dir=None,
               reps: tuple[int, ...] = REPS) -> list[dict]:
    """Every call of the design, in a seeded random order."""
    calls = []
    for sid in scenario_ids:
        scenario = load_scenario(sid, scenarios_dir)
        for level in LEVELS:
            prompt = build_prompt(scenario, level)
            for model in model_keys:
                for rep in reps:
                    calls.append({"run_id": f"{sid}-{level}-{model}-r{rep}", "scenario_id": sid,
                                  "category": scenario["category"], "level": level,
                                  "model_key": model, "rep": rep, "prompt": prompt,
                                  "prompt_sha256": prompt_sha256(prompt)})
    random.Random(config.GLOBAL_SEED).shuffle(calls)
    return calls


# ---------------------------------------------------------------- results file
def load_records(path: Path) -> list[dict]:
    """All saved answers. A half-written last line (run killed mid-write) is skipped."""
    if not path.exists():
        return []
    records = []
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARNING: {path.name} line {n} is not valid JSON and is ignored "
                  f"(that call will be re-run)")
    return records


def check_consistency(calls: list[dict], done: dict[str, dict]) -> list[str]:
    """Saved answers that were made with a different prompt or model ID than planned now."""
    problems = []
    for c in calls:
        r = done.get(c["run_id"])
        if r is None:
            continue
        if r["prompt_sha256"] != c["prompt_sha256"]:
            problems.append(f"{c['run_id']}: saved answer used a different prompt")
        if r["model_requested"] != config.MODELS[c["model_key"]]["model_id"]:
            problems.append(f"{c['run_id']}: saved answer used model {r['model_requested']}")
    return problems


_write_lock = threading.Lock()


def append_jsonl(path: Path, record: dict) -> None:
    with _write_lock, path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cost_usd(model_key: str, input_tokens: float, output_tokens: float) -> float:
    p_in, p_out = config.PRICES_PER_MTOK[model_key]
    return (input_tokens * p_in + output_tokens * p_out) / 1e6


# ---------------------------------------------------------------- estimate
def print_estimate(todo: list[dict], done: dict[str, dict]) -> float:
    """Cost and time table for the calls still to do. Returns the expected total cost."""
    print(f"\n{'model':7s} {'calls':>5s} {'input tok':>10s} {'output tok':>11s} "
          f"{'expected $':>11s} {'worst $':>8s} {'time':>8s}")
    total, total_worst, hours = 0.0, 0.0, []
    for model in config.MODELS:
        calls = [c for c in todo if c["model_key"] == model]
        if not calls:
            continue
        prev = [r for r in done.values() if r["model_key"] == model and r.get("output_tokens")]
        out_per_call = mean(r["output_tokens"] for r in prev) if prev else DEFAULT_OUTPUT_TOKENS
        sec_per_call = median(r["latency_s"] for r in prev) if prev else DEFAULT_SECONDS_PER_CALL[model]
        # provider tokenizers differ from chars/4 (Claude's counts ~1.5x more); use the measured ratio
        ratio = mean(r["input_tokens"] / approx_tokens("x" * r["prompt_chars"]) for r in prev) if prev else 1.0
        tok_in = round(sum(approx_tokens(c["prompt"]) for c in calls) * ratio)
        tok_out = out_per_call * len(calls)
        expected = cost_usd(model, tok_in, tok_out)
        worst = cost_usd(model, tok_in, config.MAX_OUTPUT_TOKENS * len(calls))
        hours.append(sec_per_call * len(calls) / 3600)
        total, total_worst = total + expected, total_worst + worst
        print(f"{model:7s} {len(calls):5d} {tok_in:10,d} {tok_out:11,.0f} "
              f"{expected:11.2f} {worst:8.2f} {hours[-1]:7.1f}h")
    print(f"{'total':7s} {len(todo):5d} {'':10s} {'':11s} {total:11.2f} {total_worst:8.2f} "
          f"{max(hours, default=0):7.1f}h  (models run in parallel)")
    basis = "measured means of answers so far" if done else f"{DEFAULT_OUTPUT_TOKENS} tokens per answer (guess)"
    in_basis = "chars/4 x measured tokenizer ratio" if done else "chars/4"
    print(f"Input = {in_basis}. Output: {basis}. Worst case = every answer hits "
          f"{config.MAX_OUTPUT_TOKENS} tokens. Prices: core/config.py PRICES_PER_MTOK.")
    return total


# ---------------------------------------------------------------- run
def run_queue(model: str, calls: list[dict], stop: threading.Event, progress: Counter, n_total: int) -> None:
    """Work through one model's calls in order. Stops this model on an error that
    survived all retries (e.g. a bad key), since the next calls would fail too."""
    from core.llm_clients import call_with_retry  # imported here so --dry-run needs no SDKs

    for c in calls:
        if stop.is_set():
            return
        seed = llama_seed(c["rep"]) if model == "llama" else None
        started = utc_now()
        try:
            res = call_with_retry(model, c["prompt"], seed=seed)
        except Exception as exc:  # noqa: BLE001 — logged, then this model stops
            append_jsonl(ERRORS, {"run_id": c["run_id"], "model_key": model, "started_at_utc": started,
                                  "error_type": type(exc).__name__, "error": str(exc)[:2000]})
            print(f"  ERROR {c['run_id']}: {type(exc).__name__}: {str(exc)[:300]}\n"
                  f"  -> stopping {model}; run again later to resume")
            return
        record = {
            "run_id": c["run_id"], "scenario_id": c["scenario_id"], "category": c["category"],
            "level": c["level"], "model_key": model, "rep": c["rep"],
            "prompt_version": PROMPT_VERSION, "prompt_sha256": c["prompt_sha256"],
            "prompt_chars": len(c["prompt"]), "seed": seed, "started_at_utc": started,
            **res.to_dict(),
            "cost_usd": round(cost_usd(model, res.input_tokens or 0, res.output_tokens or 0), 6),
            "generation_settings": config.generation_settings(),
        }
        append_jsonl(OUTPUTS, record)
        with _write_lock:
            progress["done"] += 1
            flag = "  <-- TRUNCATED" if res.stop_reason in TRUNCATED else ""
            print(f"  [{progress['done']:3d}/{n_total}] {c['run_id']:28s} {res.input_tokens or 0:5d} in "
                  f"{res.output_tokens or 0:5d} out {res.latency_s:6.1f}s {res.stop_reason}{flag}")


def run_all(todo: list[dict]) -> None:
    stop, progress = threading.Event(), Counter()
    by_model = defaultdict(list)
    for c in todo:
        by_model[c["model_key"]].append(c)
    threads = [threading.Thread(target=run_queue, args=(m, calls, stop, progress, len(todo)), daemon=True)
               for m, calls in by_model.items()]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        stop.set()
        print("\nStopping after the calls in progress (Ctrl-C again to abort them)...")
        for t in threads:
            t.join()


# ---------------------------------------------------------------- summary
def has_all_headings(text: str) -> bool:
    lines = [ln.strip().lstrip("#*0123456789. ").rstrip(":*").strip().lower() for ln in text.splitlines()]
    return all(h in lines for h in HEADINGS)


def summarize(records: list[dict], planned_ids: set[str]) -> None:
    recs = [r for r in records if r["run_id"] in planned_ids]
    print(f"\n{'=' * 78}\nSummary: {len(recs)} of {len(planned_ids)} planned calls saved\n{'=' * 78}")
    if not recs:
        return
    grid = Counter((r["model_key"], r["level"]) for r in recs)
    print(f"{'':8s}" + "".join(f"{lvl:>9s}" for lvl in LEVELS))
    for m in config.MODELS:
        print(f"{m:8s}" + "".join(f"{grid[(m, lvl)]:9d}" for lvl in LEVELS))

    print("\nper model:   versions answered | stop reasons | mean in/out tokens | mean s | all 4 headings | cost $")
    for m in config.MODELS:
        rs = [r for r in recs if r["model_key"] == m]
        if not rs:
            continue
        versions = ", ".join(sorted({r["model_version"] for r in rs}))
        stops = dict(Counter(r["stop_reason"] for r in rs))
        headed = sum(has_all_headings(r["text"]) for r in rs)
        print(f"  {m:7s} {versions} | {stops} | {mean(r['input_tokens'] or 0 for r in rs):.0f}/"
              f"{mean(r['output_tokens'] or 0 for r in rs):.0f} | {mean(r['latency_s'] for r in rs):.1f} | "
              f"{headed}/{len(rs)} | {sum(r['cost_usd'] for r in rs):.2f}")

    problems = [f"{r['run_id']}: empty answer" for r in recs if not r["text"].strip()]
    problems += [f"{r['run_id']}: truncated ({r['stop_reason']})" for r in recs if r["stop_reason"] in TRUNCATED]
    problems += [f"{r['run_id']}: llama context overflow risk" for r in recs
                 if r.get("extra", {}).get("context_overflow_risk")]
    print("\nflags: " + ("none" if not problems else "\n  " + "\n  ".join(problems)))

    spent = sum(r["cost_usd"] for r in recs)
    print(f"\nspent so far on these calls: ${spent:.2f}")
    if ERRORS.exists():  # only errors whose call still has no saved answer
        saved = {r["run_id"] for r in records}
        open_errors = {e["run_id"] for e in load_records(ERRORS)} - saved
        print(f"errors still without an answer: {len(open_errors)} (history in {ERRORS.name})")


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="+", help="scenario IDs (default: all 15)")
    parser.add_argument("--models", nargs="+", choices=list(config.MODELS), help="default: all 3")
    parser.add_argument("--dry-run", action="store_true", help="show plan and estimate, make no calls")
    parser.add_argument("--summary", action="store_true", help="summarise saved answers and exit")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation question")
    parser.add_argument("--pilot", action="store_true", help="calibration scenario, 1 rep, separate file")
    args = parser.parse_args()

    global OUTPUTS, ERRORS  # the workers append to these
    scenarios_dir, reps = None, REPS
    if args.pilot:
        scenarios_dir, reps, OUTPUTS, ERRORS = config.PILOT_DIR, (1,), PILOT_OUTPUTS, PILOT_ERRORS
        OUTPUTS.parent.mkdir(parents=True, exist_ok=True)
    scenario_ids = args.scenarios or all_scenario_ids(scenarios_dir)
    unknown = set(scenario_ids) - set(all_scenario_ids(scenarios_dir))
    if unknown:
        parser.error(f"unknown scenario(s): {sorted(unknown)}")
    calls = plan_calls(scenario_ids, args.models or list(config.MODELS), scenarios_dir, reps)
    planned_ids = {c["run_id"] for c in calls}

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records(OUTPUTS)
    done = {}
    for r in records:
        done.setdefault(r["run_id"], r)  # keep the first answer if a run_id ever appears twice
    if args.summary:
        summarize(records, planned_ids)
        return 0

    problems = check_consistency(calls, done)
    if problems:
        print("STOP: results/raw_outputs.jsonl contains answers from a different prompt or model:")
        print("  " + "\n  ".join(problems[:10]) + (f"\n  ... {len(problems) - 10} more" if len(problems) > 10 else ""))
        print("Move the file aside (it is a different experiment version) before running again.")
        return 1

    todo = [c for c in calls if c["run_id"] not in done]
    print(f"Plan: {len(scenario_ids)} scenario(s) x {len(LEVELS)} levels x "
          f"{len(args.models or config.MODELS)} model(s) x {len(reps)} reps = {len(calls)} calls; "
          f"{len(calls) - len(todo)} already saved, {len(todo)} to do.")
    print(f"Settings: {config.generation_settings()}, prompt {PROMPT_VERSION}, "
          f"llama seeds {[llama_seed(r) for r in reps]} for reps {list(reps)}")
    print("Models: " + ", ".join(f"{k}={v['model_id']}" for k, v in config.MODELS.items()))
    if not todo:
        summarize(records, planned_ids)
        return 0
    print_estimate(todo, done)
    if args.dry_run:
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            print("Not running: no terminal to confirm in. Re-run with --yes to confirm.")
            return 1
        if input(f"\nStart {len(todo)} calls? Type 'yes' to continue: ").strip().lower() != "yes":
            print("Cancelled; nothing was sent.")
            return 1

    with LOCK.open("w") as lock:
        try:  # stops a second copy of this script from making the same paid calls
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another run_experiment.py is already running. Not starting.")
            return 1
        print(f"\nRunning; appending to {OUTPUTS.relative_to(config.PROJECT_ROOT)}")
        run_all(todo)

    summarize(load_records(OUTPUTS), planned_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
