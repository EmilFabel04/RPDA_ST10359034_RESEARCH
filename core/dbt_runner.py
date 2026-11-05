"""Run dbt as a subprocess and read its artefacts (run_results.json, sources.json).

The pipeline is two steps, as in a real warehouse:
  1. ingestion  -> `dbt seed --full-refresh`  (loads the raw_* CSVs into the `raw` schema)
  2. transform  -> `dbt build --exclude resource_type:seed`  (models + tests)
     freshness  -> `dbt source freshness`
Keeping seeds out of step 2 means run_results.json describes only the
transformation job, which is what an engineer (or an LLM) would debug.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DBT = Path(sys.executable).with_name("dbt")  # the dbt installed in this venv

INGEST = ["seed", "--full-refresh"]
BUILD = ["build", "--exclude", "resource_type:seed"]
FRESHNESS = ["source", "freshness"]


def run_dbt(args: list[str], project_dir: Path) -> subprocess.CompletedProcess:
    """Run one dbt command inside `project_dir` (profiles.yml lives there too)."""
    env = {**os.environ, "DO_NOT_TRACK": "1"}
    return subprocess.run(
        [str(DBT), *args, "--project-dir", str(project_dir), "--profiles-dir", str(project_dir)],
        cwd=project_dir, capture_output=True, text=True, env=env,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def node_statuses(run_results: dict) -> list[tuple[str, str, str | None]]:
    """[(unique_id, status, message)] from a run_results.json."""
    return [(r["unique_id"], r["status"], r.get("message")) for r in run_results["results"]]


def freshness_statuses(sources_json: dict) -> list[dict]:
    """[{source, status, max_loaded_at, age_hours}] from a sources.json."""
    out = []
    for r in sources_json["results"]:
        age = r.get("max_loaded_at_time_ago_in_s")
        out.append({
            "source": r["unique_id"],
            "status": r["status"],
            "max_loaded_at": r.get("max_loaded_at"),
            "age_hours": round(age / 3600, 1) if age is not None else None,
        })
    return out


def warnings_in(stdout: str) -> list[str]:
    """Deprecation / warning lines dbt printed (should be empty for a clean project)."""
    return [line for line in stdout.splitlines()
            if "[WARNING]" in line or "Deprecat" in line or " WARN " in line]
