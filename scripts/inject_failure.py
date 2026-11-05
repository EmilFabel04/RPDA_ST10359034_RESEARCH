"""Step 3 — inject the 15 failure scenarios and capture their dbt artefacts.

    python scripts/inject_failure.py              # all 15 scenarios
    python scripts/inject_failure.py SD01 NR02    # only these
    python scripts/inject_failure.py --as-of "2026-10-13 12:00:00"
    python scripts/inject_failure.py --force      # overwrite existing scenarios
    python scripts/inject_failure.py --pilot      # the calibration scenario PL01 -> data/pilot/

Existing scenarios are never overwritten without --force: regenerating changes
timestamps and therefore the prompts, which would invalidate LLM runs already
made on the old version (Step 5 logs a hash of every prompt).

For each scenario (definitions in core/scenario_defs.py):
  1. copy dbt_project/ to a temp folder and generate the seeds (shared as_of)
  2. baseline run: dbt seed + dbt build on clean data ("yesterday's" warehouse)
  3. apply ONE fault (data, model SQL or YAML config)
  4. fault run: dbt seed --full-refresh, dbt build, dbt source freshness
  5. save to data/scenarios/<id>/:
       scenario.json        prompt parts 1-4 as text + gold-standard remediation
       ground_truth.json    root cause, fault, expected vs observed failures,
                            fix targets, valid entity names (hallucination check)
       run_results.json, sources.json, manifest_nodes.json, compiled/, logs/,
       relation_columns.json, fault.diff (code/config faults)
Then prints the CHECKPOINT 3 table and writes data/scenarios/index.csv.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core` importable

import duckdb  # noqa: E402

from core import config  # noqa: E402
from core.dbt_runner import BUILD, FRESHNESS, INGEST, read_json, run_dbt  # noqa: E402
from core.scenario_defs import (NOISE, PILOT_SCENARIOS, SCENARIOS, Scenario, base_facts,  # noqa: E402
                                commit_hash)
from core.seed_data import TS_FMT, default_as_of, read_csv, write_seeds  # noqa: E402

BAD_BUILD = {"error", "fail", "warn", "runtime error"}
BAD_FRESHNESS = {"error", "warn", "runtime error"}
RAW_TABLES = ("raw_customers", "raw_orders", "raw_payments")
# How the transformation command is shown in prompts. Seeds stand in for the
# ingestion jobs (D13), so in the simulated project the scheduled job is plain
# `dbt build`; "--exclude resource_type:seed" would expose the simulation (D19).
BUILD_AS_SHOWN = "dbt build"

# Designed column-level lineage of the clean project (documentation, like a
# catalog would show). Faults do not update it.
COLUMN_LINEAGE = {
    "stg_customers": [("customer_id", "raw_customers.customer_id"),
                      ("first_name, last_name, created_at, loaded_at", "raw_customers (same names)"),
                      ("email", "raw_customers.email (lower-cased)"),
                      ("country_code", "raw_customers.country (upper-cased)")],
    "stg_orders": [("order_id, customer_id, status, loaded_at", "raw_orders (same names)"),
                   ("order_date", "raw_orders.order_date (cast to date)")],
    "stg_payments": [("payment_id, order_id, payment_method, loaded_at", "raw_payments (same names)"),
                     ("amount", "raw_payments.amount (integer cents / 100)")],
    "dim_customers": [("customer_id, first_name, last_name, email, country_code, created_at",
                       "stg_customers (same names)"),
                      ("first_order_date, most_recent_order_date, number_of_orders",
                       "stg_orders.order_date / order_id, per customer_id"),
                      ("lifetime_value", "stg_payments.amount joined via stg_orders.order_id, "
                                         "non-cancelled orders, per customer_id")],
    "fct_orders": [("order_id, customer_id, order_date, status", "stg_orders (same names)"),
                   ("credit_card_amount, bank_transfer_amount, voucher_amount, gift_card_amount",
                    "stg_payments.amount by payment_method, per order_id"),
                   ("amount", "stg_payments.amount, total per order_id")],
}


# ---------------------------------------------------------------- small helpers
def short_id(uid: str) -> str:
    """test.ecommerce.not_null_x.ab12 -> test.not_null_x ; source.ecommerce.raw.t -> source.raw.t"""
    p = uid.split(".")
    return f"source.{p[2]}.{p[3]}" if p[0] == "source" else f"{p[0]}.{p[2]}"


def display(uid: str) -> str:
    """Human label: 'model stg_orders', 'source raw.raw_orders', 'test unique_x'."""
    kind, _, rest = short_id(uid).partition(".")
    return f"{kind} {rest}"


def fmt_ts(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC") if iso else "unknown"


def freshness_rule(criteria: dict) -> str:
    """{'warn_after': {'count': 6, 'period': 'hour'}, ...} -> 'warn after 6 hours, error after 12 hours'"""
    return ", ".join(f"{k.replace('_after', '')} after {v['count']} {v['period']}{'s' if v['count'] != 1 else ''}"
                     for k, v in criteria.items() if k.endswith("_after") and v and v.get("count"))


def seed_summary(before: dict[str, list[dict]], after: dict[str, list[dict]]) -> dict:
    """What a data fault changed in each raw table (rows/columns), for ground_truth.json."""
    out = {}
    for table in before:
        b, a = before[table], after[table]
        cols_b, cols_a = list(b[0]), list(a[0])
        if b == a:
            continue
        rows_b = Counter(tuple(r.values()) for r in b) if cols_b == cols_a else None
        rows_a = Counter(tuple(r.values()) for r in a) if cols_b == cols_a else None
        out[table] = {
            "rows_before": len(b), "rows_after": len(a),
            "columns_added": [c for c in cols_a if c not in cols_b],
            "columns_removed": [c for c in cols_b if c not in cols_a],
            "rows_only_before": sum((rows_b - rows_a).values()) if rows_b is not None else None,
            "rows_only_after": sum((rows_a - rows_b).values()) if rows_b is not None else None,
        }
    return out


def fill(text: str, facts: dict) -> str:
    return Template(text).substitute(facts)


def text_files(proj: Path) -> dict[str, str]:
    """All project files except seeds and build output, for the fault diff."""
    out = {}
    for f in sorted(proj.rglob("*")):
        rel = f.relative_to(proj).as_posix()
        if f.is_file() and not rel.startswith(("target/", "logs/", "seeds/")) and f.suffix in (".sql", ".yml"):
            out[rel] = f.read_text()
    return out


def relation_columns(db: Path) -> dict[str, list[list[str]]]:
    with duckdb.connect(str(db), read_only=True) as con:
        rows = con.execute(
            "select table_schema, table_name, column_name, data_type from information_schema.columns "
            "where table_schema in ('raw', 'main') order by table_schema, table_name, ordinal_position"
        ).fetchall()
    out: dict[str, list[list[str]]] = {}
    for schema, table, col, dtype in rows:
        out.setdefault(f"{schema}.{table}", []).append([col, dtype])
    return out


def manifest_subset(manifest: dict) -> dict:
    """Models, tests, sources and exposures of this project (no macros/internals)."""
    nodes = {}
    for uid, n in manifest["nodes"].items():
        if n["package_name"] != "ecommerce" or n["resource_type"] not in ("model", "test"):
            continue
        item = {k: n.get(k) for k in ("unique_id", "resource_type", "name", "original_file_path", "description",
                                      "raw_code", "compiled_code", "attached_node", "column_name")}
        item["materialized"] = n["config"].get("materialized")
        item["depends_on"] = n["depends_on"]["nodes"]
        item["columns"] = {c: v.get("description", "") for c, v in n.get("columns", {}).items()}
        if n.get("test_metadata"):
            item["test_metadata"] = {"name": n["test_metadata"]["name"], "kwargs": n["test_metadata"]["kwargs"]}
        nodes[uid] = {k: v for k, v in item.items() if v not in (None, "", {}, [])}
    for uid, s in manifest["sources"].items():
        cfg = s.get("config", {})
        nodes[uid] = {"unique_id": uid, "resource_type": "source", "source_name": s["source_name"],
                      "name": s["name"], "description": s.get("description", ""),
                      "relation_name": s.get("relation_name"),
                      "loaded_at_field": s.get("loaded_at_field") or cfg.get("loaded_at_field"),
                      "freshness": s.get("freshness") or cfg.get("freshness"),
                      "columns": {c: v.get("description", "") for c, v in s.get("columns", {}).items()}}
    for uid, e in manifest["exposures"].items():
        nodes[uid] = {"unique_id": uid, "resource_type": "exposure", "name": e["name"], "label": e.get("label"),
                      "type": e.get("type"), "description": e.get("description", ""),
                      "owner": e.get("owner", {}).get("name"), "depends_on": e["depends_on"]["nodes"]}
    keep = set(nodes)
    sub = lambda m: {k: [v for v in vs if v in keep] for k, vs in m.items() if k in keep}  # noqa: E731
    return {"nodes": nodes, "parent_map": sub(manifest["parent_map"]), "child_map": sub(manifest["child_map"])}


def walk(start: list[str], graph: dict[str, list[str]]) -> list[str]:
    seen, stack = [], list(start)
    while stack:
        for nxt in graph.get(stack.pop(), []):
            if nxt not in seen and not nxt.startswith("test."):
                seen.append(nxt)
                stack.append(nxt)
    return seen


# ---------------------------------------------------------------- prompt part renderers
def test_args(node: dict) -> str:
    kwargs = node.get("test_metadata", {}).get("kwargs", {})
    args = []
    for k, v in kwargs.items():
        if k in ("model", "column_name"):
            continue
        if isinstance(v, str) and "ref(" in v:
            v = v.split("ref(")[1].split(")")[0].strip("'\"")
        args.append(f"{k}={v}")
    name = node.get("test_metadata", {}).get("name", node["name"])
    return f"{name}({', '.join(args)})" if args else name


def render_failure(build_rc, results, fresh_rc, freshness, nodes) -> str:
    counts = Counter(r["status"] for r in results)
    lines = [f"Command: {BUILD_AS_SHOWN}  (exit code {build_rc})",
             f"Result: {counts['success'] + counts['pass']} passed, {counts['fail']} failed, "
             f"{counts['error']} errors, {counts['warn']} warnings, {counts['skipped']} skipped"]
    for r in results:
        if r["status"] not in BAD_BUILD:
            continue
        node = nodes.get(r["unique_id"], {})
        if r["unique_id"].startswith("test."):
            attached = node.get("attached_node", "")
            target = attached.split(".")[-1] + (f".{node['column_name']}" if node.get("column_name") else "")
            lines.append(f"- {r['status'].upper()}: test {node.get('name', short_id(r['unique_id']))} "
                         f"[{test_args(node)}] on {target}")
            lines.append(f"  Message: {(r.get('message') or '').strip()}")
            if node.get("compiled_code"):
                sql = "\n".join(f"    {ln}" for ln in node["compiled_code"].strip().splitlines() if ln.strip())
                lines.append(f"  Compiled test SQL:\n{sql}")
        else:
            lines.append(f"- {r['status'].upper()}: {display(r['unique_id'])} ({node.get('original_file_path', '')})")
            msg = "\n".join(f"    {ln}" for ln in (r.get("message") or "").strip().splitlines())
            lines.append(msg)
    skipped = [r["unique_id"] for r in results if r["status"] == "skipped"]
    if skipped:
        models = [display(u) for u in skipped if u.startswith("model.")]
        n_tests = sum(u.startswith("test.") for u in skipped)
        what = models + ([f"{n_tests} tests"] if n_tests else [])
        lines.append(f"- SKIPPED because an upstream node failed: {', '.join(what)}")
    lines += ["", f"Command: dbt {' '.join(FRESHNESS)}  (exit code {fresh_rc})"]
    for r in freshness:
        crit = r.get("criteria") or {}
        rule = freshness_rule(crit)
        age = r.get("max_loaded_at_time_ago_in_s")
        age_txt = f"{age / 3600:.1f} h before the check" if age is not None else "age unknown"
        lines.append(f"- {r['status'].upper()}: {display(r['unique_id'])}: max(loaded_at) = "
                     f"{fmt_ts(r.get('max_loaded_at'))}, {age_txt} ({rule})")
    return "\n".join(lines)


def column_lines(name_cols: dict[str, str], warehouse: list[list[str]] | None, tests: dict[str, list[str]]):
    types = dict(map(tuple, warehouse)) if warehouse else {}
    out = []
    for col, desc in name_cols.items():
        dtype = types.get(col, "missing from warehouse table" if warehouse else "type unknown")
        t = f" · tests: {', '.join(tests[col])}" if tests.get(col) else ""
        out.append(f"- {col} · {dtype} · {desc}{t}")
    for col, dtype in (warehouse or []):
        if col not in name_cols:
            out.append(f"- {col} · {dtype} · (not documented)")
    return out


def render_node_metadata(uid: str, nodes: dict, relcols: dict) -> str:
    n = nodes[uid]
    if n["resource_type"] == "source":
        fr = n.get("freshness") or {}
        rule = freshness_rule(fr)
        lines = [f"### Source {n['source_name']}.{n['name']}",
                 f"Table: {n['relation_name']}",
                 f"Description: {n['description'].strip()}",
                 f"Freshness: measured on `{n['loaded_at_field']}`; {rule}",
                 "Columns (name · type in warehouse · description):"]
        lines += column_lines(n["columns"], relcols.get(f"raw.{n['name']}"), {})
        return "\n".join(lines)

    col_tests: dict[str, list[str]] = {}
    model_tests = []
    for t in nodes.values():
        if t["resource_type"] == "test" and t.get("attached_node") == uid:
            if t.get("column_name"):
                col_tests.setdefault(t["column_name"], []).append(test_args(t))
            else:
                model_tests.append(test_args(t))
    lines = [f"### Model {n['name']}",
             f"File: {n['original_file_path']} · materialized as {n['materialized']}",
             f"Description: {n['description'].strip()}",
             "Columns (name · type in warehouse · description · tests):"]
    lines += column_lines(n["columns"], relcols.get(f"main.{n['name']}"), col_tests)
    if model_tests:
        lines.append(f"Model-level tests: {', '.join(model_tests)}")
    lines += [f"SQL ({n['original_file_path']}):", "```sql", n["raw_code"].strip(), "```"]
    return "\n".join(lines)


def render_lineage(focus: list[str], manifest_sub: dict, relcols: dict) -> str:
    nodes, parents, children = manifest_sub["nodes"], manifest_sub["parent_map"], manifest_sub["child_map"]
    up, down = walk(focus, parents), walk(focus, children)
    in_scope = set(focus) | set(up) | set(down)
    edges = sorted({(p, c) for c in in_scope for p in parents.get(c, []) if p in in_scope},
                   key=lambda e: (e[0].split(".")[0] != "source", e))
    lines = ["DAG edges (upstream → downstream; tests omitted):"]
    lines += [f"- {display(p)} → {display(c)}" for p, c in edges]

    upstream = [u for u in up if u not in focus]
    if upstream:
        lines.append("Upstream nodes and their current warehouse columns:")
        for u in sorted(upstream, key=lambda x: (not x.startswith("source"), x)):
            n = nodes[u]
            rel = f"raw.{n['name']}" if n["resource_type"] == "source" else f"main.{n['name']}"
            cols = ", ".join(f"{c} {t}" for c, t in relcols.get(rel, [])) or "relation not found"
            kind = "source table" if n["resource_type"] == "source" else n.get("materialized", "")
            lines.append(f"- {display(u)} ({kind}): {cols}")
    downstream = [d for d in down if d not in focus and d not in up]  # a node between two focus nodes is upstream
    if downstream:
        lines.append("Downstream nodes (affected if the failing node is wrong or skipped):")
        for d in downstream:
            n = nodes[d]
            if n["resource_type"] == "exposure":
                lines.append(f"- exposure {n['name']} ({n['type']}, owner: {n['owner']}): {n['description']}")
            else:
                lines.append(f"- {display(d)} ({n.get('materialized', '')}): {n['description']}")
    models = [nodes[u]["name"] for u in [*focus, *up, *down] if u.startswith("model.")]
    if models:
        lines.append("Column-level lineage (as designed):")
        for m in dict.fromkeys(models):
            for cols, src in COLUMN_LINEAGE.get(m, []):
                lines.append(f"- {m}.{{{cols}}} ← {src}" if "," in cols else f"- {m}.{cols} ← {src}")
    return "\n".join(lines)


def render_history(sc: Scenario, facts: dict) -> str:
    entries = list(sc.changes) + [NOISE[i] for i in sc.noise]
    lines = ["Recent changes (newest first):"]
    for days_ago, kind, text in sorted(entries, key=lambda e: e[0]):
        when = facts[f"d{days_ago}"]
        label = f"commit {commit_hash(sc.id, text)}" if kind == "commit" else kind
        lines.append(f"- {when} · {label} · {fill(text, facts)}")
    lines.append("Previous incidents:")
    lines += [f"- {fill(t, facts)}" for t in sc.incidents]
    lines.append("Recent run history:")
    lines += [f"- {fill(t, facts)}" for t in sc.run_history]
    return "\n".join(lines)


def render_gold(sc: Scenario, facts: dict) -> dict:
    gold = {k: fill(v, facts) for k, v in sc.gold.items()}
    parts = [f"Root cause: {gold['root_cause']}", f"Fix: {gold['fix']}", f"Verification: {gold['verification']}"]
    if gold.get("notes"):
        parts.append(f"Notes: {gold['notes']}")
    gold["text"] = "\n\n".join(parts)
    return gold


# ---------------------------------------------------------------- one scenario
def run_scenario(sc: Scenario, as_of: datetime, out_root: Path) -> dict:
    out = out_root / sc.id
    if out.exists():
        shutil.rmtree(out)
    (out / "logs").mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix=f"rdpa_{sc.id}_") as tmp:
        proj = Path(tmp) / "dbt_project"
        shutil.copytree(config.DBT_PROJECT_DIR, proj, ignore=shutil.ignore_patterns(
            "target", "logs", "dbt_packages", "*.duckdb", "*.duckdb.wal", "*.csv"))
        write_seeds(proj / "seeds", as_of=as_of)

        def clean(text: str) -> str:  # hide the temp path in saved artefacts
            for p in {str(proj.resolve()), str(proj)}:
                text = text.replace(p + "/", "").replace(p, "dbt_project")
            return text

        # 2. baseline: yesterday's successful run, so the warehouse has tables
        for cmd in (INGEST, BUILD):
            r = run_dbt(cmd, proj)
            assert r.returncode == 0, f"{sc.id}: baseline `dbt {' '.join(cmd)}` failed:\n{r.stdout[-2000:]}"

        # 3. apply ONE fault
        facts = base_facts(proj, as_of)
        before = text_files(proj)
        seeds_before = {t: read_csv(proj / "seeds" / f"{t}.csv") for t in RAW_TABLES}
        facts.update(sc.apply(proj, as_of))
        after = text_files(proj)
        data_change = seed_summary(seeds_before, {t: read_csv(proj / "seeds" / f"{t}.csv") for t in RAW_TABLES})
        diff = "".join("".join(difflib.unified_diff(before.get(f, "").splitlines(True), after[f].splitlines(True),
                                                    f"a/{f}", f"b/{f}"))
                       for f in after if before.get(f) != after[f])

        # 4. fault run
        seed = run_dbt(INGEST, proj)
        assert seed.returncode == 0, f"{sc.id}: ingestion failed:\n{seed.stdout[-2000:]}"
        build = run_dbt(BUILD, proj)
        run_results = json.loads(clean((proj / "target/run_results.json").read_text()))
        manifest = json.loads(clean((proj / "target/manifest.json").read_text()))
        shutil.copytree(proj / "target/compiled/ecommerce", out / "compiled")
        fresh = run_dbt(FRESHNESS, proj)
        sources_json = json.loads(clean((proj / "target/sources.json").read_text()))
        relcols = relation_columns(proj / "ecommerce.duckdb")
        files = sorted(text_files(proj))
        for name, proc in (("dbt_seed", seed), ("dbt_build", build), ("dbt_source_freshness", fresh)):
            (out / "logs" / f"{name}.log").write_text(clean(proc.stdout))

    # ages as measured by `dbt source freshness`, so the history/gold text matches part 1 exactly
    for r in sources_json["results"]:
        if r.get("max_loaded_at_time_ago_in_s") is not None:
            facts[f"age_{r['unique_id'].split('.')[-1]}"] = f"{r['max_loaded_at_time_ago_in_s'] / 3600:.0f}"

    # ---- failures observed
    sub = manifest_subset(manifest)
    nodes = sub["nodes"]
    failing = [r["unique_id"] for r in run_results["results"] if r["status"] in BAD_BUILD]
    failing += [r["unique_id"] for r in sources_json["results"] if r["status"] in BAD_FRESHNESS]
    observed = [short_id(u) for u in failing]
    missing = sorted(set(sc.expected_failures) - set(observed))
    unexpected = sorted(set(observed) - set(sc.expected_failures))

    # nodes the failure points at (derived from the failure only, never from the root cause)
    focus: list[str] = []
    for uid in failing:
        if uid.startswith("test."):
            deps = nodes[uid]["depends_on"]
            attached = nodes[uid].get("attached_node")
            focus += [attached] + [d for d in deps if d != attached and d.startswith("model.")]
        else:
            focus.append(uid)
    focus = list(dict.fromkeys(f for f in focus if f))

    parts = {
        "failure_description": render_failure(build.returncode, run_results["results"],
                                              fresh.returncode, sources_json["results"], nodes),
        "model_metadata": "\n\n".join(render_node_metadata(u, nodes, relcols) for u in focus),
        "lineage": render_lineage(focus, sub, relcols),
        "historical_context": render_history(sc, facts),
    }
    gold = render_gold(sc, facts)
    public_facts = {k: v for k, v in facts.items() if not (k[0] == "d" and k[1:].isdigit())}

    scenario = {
        "scenario_id": sc.id, "category": sc.category, "as_of": as_of.strftime(TS_FMT), "seed": config.GLOBAL_SEED,
        "dbt_commands": ["dbt " + " ".join(INGEST), "dbt " + " ".join(BUILD), "dbt " + " ".join(FRESHNESS)],
        "focus_nodes": focus,
        **parts,
        "historical_context_synthetic": True,
        "gold_standard_remediation": gold,
        "approx_tokens": {k: len(v) // 4 for k, v in parts.items()},
    }
    ground_truth = {
        "scenario_id": sc.id, "category": sc.category, "title": sc.title,
        "root_cause_type": sc.root_cause_type, "root_cause": sc.root_cause,
        "fault": {"kind": sc.root_cause_type, "diff": diff or None, "data_change": data_change or None,
                  "facts": public_facts},
        "expected_failures": sc.expected_failures, "observed_failures": observed,
        "validation": {"matches_expected": not missing and not unexpected,
                       "missing": missing, "unexpected": unexpected},
        "fix_targets": sc.fix_targets, "key_entities": sc.key_entities,
        "valid_entities": {
            "models": sorted(n["name"] for n in nodes.values() if n["resource_type"] == "model"),
            "sources": sorted(f"{n['source_name']}.{n['name']}" for n in nodes.values()
                              if n["resource_type"] == "source"),
            "exposures": sorted(n["name"] for n in nodes.values() if n["resource_type"] == "exposure"),
            "tests": sorted(n["name"] for n in nodes.values() if n["resource_type"] == "test"),
            "columns": {rel: [c for c, _ in cols] for rel, cols in relcols.items()},
            "documented_columns": {n["name"]: sorted(n.get("columns", {})) for n in nodes.values()
                                   if n["resource_type"] in ("model", "source")},
            "files": files,
        },
    }

    dump = lambda obj, name: (out / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")  # noqa: E731
    dump(scenario, "scenario.json")
    dump(ground_truth, "ground_truth.json")
    dump(run_results, "run_results.json")
    dump(sources_json, "sources.json")
    dump(sub, "manifest_nodes.json")
    dump(relcols, "relation_columns.json")
    if diff:
        (out / "fault.diff").write_text(diff)
    return {"scenario": scenario, "ground_truth": ground_truth}


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="scenario ids (default: all 15)")
    parser.add_argument("--as-of", help=f"UTC reference time '{TS_FMT}' (default: now, to the hour)")
    parser.add_argument("--force", action="store_true", help="overwrite scenarios that already exist")
    parser.add_argument("--pilot", action="store_true", help="build the calibration scenario instead")
    args = parser.parse_args()
    as_of = datetime.strptime(args.as_of, TS_FMT) if args.as_of else default_as_of()
    pool, out_root = (PILOT_SCENARIOS, config.PILOT_DIR) if args.pilot else (SCENARIOS, config.SCENARIOS_DIR)
    chosen = [s for s in pool if not args.ids or s.id in args.ids]
    existing = [s.id for s in chosen if (out_root / s.id / "scenario.json").exists()]
    if existing and not args.force:
        print(f"Refusing to overwrite existing scenarios {existing}; use --force to regenerate them.")
        return 1

    print(f"as_of = {as_of:%Y-%m-%d %H:%M} UTC, {len(chosen)} scenario(s)\n")
    rows = []
    for sc in chosen:
        res = run_scenario(sc, as_of, out_root)
        gt, scn = res["ground_truth"], res["scenario"]
        ok = gt["validation"]["matches_expected"]
        rows.append({"scenario_id": sc.id, "category": sc.category, "root_cause_type": sc.root_cause_type,
                     "title": sc.title, "observed_failures": "; ".join(gt["observed_failures"]),
                     "matches_expected": ok, "approx_tokens_parts_1_4": sum(scn["approx_tokens"].values())})
        flag = "OK " if ok else "MISMATCH"
        print(f"  [{flag}] {sc.id}  {', '.join(gt['observed_failures'])}")
        if not ok:
            print(f"           missing={gt['validation']['missing']} unexpected={gt['validation']['unexpected']}")

    if not args.ids and not args.pilot:
        with (config.SCENARIOS_DIR / "index.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    bad = [r["scenario_id"] for r in rows if not r["matches_expected"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} scenarios fail exactly as designed"
          + (f"; check {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
