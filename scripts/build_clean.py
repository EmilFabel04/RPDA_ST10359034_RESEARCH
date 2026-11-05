"""CHECKPOINT 2 — build the clean dbt project and show that everything passes.

    python scripts/build_clean.py                        # timestamps relative to now
    python scripts/build_clean.py --as-of "2026-10-13 12:00:00"   # reproduce a run

Steps
  1. Generate the raw_* seed CSVs (seeded; timestamps relative to --as-of).
  2. Ingest:    dbt seed --full-refresh
  3. Transform: dbt build --exclude resource_type:seed   (models + all tests)
  4. Freshness: dbt source freshness
Prints every model/test status, freshness ages and table row counts.
Exit code 0 only if every step passes with no warnings.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core` importable

import duckdb  # noqa: E402

from core import config  # noqa: E402
from core.dbt_runner import (BUILD, FRESHNESS, INGEST, freshness_statuses, node_statuses,  # noqa: E402
                             read_json, run_dbt, warnings_in)
from core.seed_data import TS_FMT, write_seeds  # noqa: E402

PROJECT = config.DBT_PROJECT_DIR


def header(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", help=f"UTC reference time, format '{TS_FMT}' (default: now)")
    args = parser.parse_args()
    as_of = datetime.strptime(args.as_of, TS_FMT) if args.as_of else None

    header("1. Generate seeds")
    info = write_seeds(PROJECT / "seeds", as_of=as_of)
    print(f"  as_of={info['as_of']} UTC  seed={info['seed']}  rows={info['row_counts']}")

    (PROJECT / "ecommerce.duckdb").unlink(missing_ok=True)  # start from an empty warehouse
    ok, all_warnings = True, []

    header("2. Ingest: dbt " + " ".join(INGEST))
    seed = run_dbt(INGEST, PROJECT)
    all_warnings += warnings_in(seed.stdout)
    print(f"  exit code {seed.returncode}")
    ok &= seed.returncode == 0

    header("3. Transform: dbt " + " ".join(BUILD))
    build = run_dbt(BUILD, PROJECT)
    all_warnings += warnings_in(build.stdout)
    results = node_statuses(read_json(PROJECT / "target" / "run_results.json"))
    for uid, status, msg in results:
        flag = "" if status in ("success", "pass", "no-op") else f"   <-- {msg}"
        print(f"  {status:8s} {uid}{flag}")
    print(f"  exit code {build.returncode}; {len(results)} nodes")
    ok &= build.returncode == 0

    header("4. Freshness: dbt " + " ".join(FRESHNESS))
    fresh = run_dbt(FRESHNESS, PROJECT)
    all_warnings += warnings_in(fresh.stdout)
    for r in freshness_statuses(read_json(PROJECT / "target" / "sources.json")):
        print(f"  {r['status']:6s} {r['source']:32s} max_loaded_at={r['max_loaded_at']}  "
              f"age={r['age_hours']}h")
    print(f"  exit code {fresh.returncode}")
    ok &= fresh.returncode == 0

    header("Row counts")
    with duckdb.connect(str(PROJECT / "ecommerce.duckdb"), read_only=True) as con:
        for schema, table in con.execute(
            "select table_schema, table_name from information_schema.tables "
            "order by table_schema desc, table_name"
        ).fetchall():
            n = con.execute(f'select count(*) from "{schema}"."{table}"').fetchone()[0]
            print(f"  {schema}.{table:16s} {n:5d}")

    if all_warnings:
        header("Warnings")
        for w in all_warnings:
            print(f"  {w}")
    ok &= not all_warnings

    if not ok:
        print("\n--- dbt build output (tail) ---\n" + "\n".join(build.stdout.splitlines()[-30:]))
    print(f"\nCHECKPOINT 2: {'CLEAN BUILD PASSES' if ok else 'NOT YET — see above'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
