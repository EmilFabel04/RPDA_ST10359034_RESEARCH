"""Step 4 — build the experiment prompt for one scenario at one context level.

    from prompts.builder import build_prompt, load_scenario
    prompt = build_prompt(load_scenario("SD01"), "partial")

The prompt has five parts. Each context level adds parts; it never rewrites them:

    part 1  intro + failure report     (scenario.json: failure_description)
    part 2  model and source metadata  (scenario.json: model_metadata)
    part 3  lineage                    (scenario.json: lineage)
    part 4  recent history             (scenario.json: historical_context)
    part 5  task: what the answer must contain (identical in every prompt)

    minimal = 1 + 5     partial = 1 + 2 + 5     full = 1 + 2 + 3 + 4 + 5

`build_prompt` deliberately takes no model argument: all three LLMs receive the
same text, sent as a single user message (no system prompt), so differences
between models cannot come from the prompt. Headings are unnumbered, so a
minimal prompt does not show that parts 2-4 exist.

If any wording below changes, bump PROMPT_VERSION. Step 5 logs it and a SHA-256
of every prompt next to each answer.
"""
from __future__ import annotations

import hashlib
import json
from string import Template

from core import config

PROMPT_VERSION = "v1"

LEVELS = {
    "minimal": (1, 5),
    "partial": (1, 2, 5),
    "full": (1, 2, 3, 4, 5),
}

# Which scenario.json field fills each context part (part 5 has no field)
PART_FIELDS = {
    1: "failure_description",
    2: "model_metadata",
    3: "lineage",
    4: "historical_context",
}

HEADINGS = {
    1: "## Failure report",
    2: "## Model and source metadata",
    3: "## Lineage",
    4: "## Recent history",
    5: "## Task",
}

# Opens part 1. Describes only what every engineer on this team would know.
INTRO = Template(
    "You are helping the on-call analytics engineer of an online shop. The "
    "shop's data warehouse is built with dbt (dbt-core 1.12, DuckDB adapter). "
    "Ingestion jobs load data from the web shop, the payment provider and the "
    "CRM into the `raw` schema every hour; dbt then builds staging views and "
    "mart tables on top, runs the data tests and checks source freshness.\n\n"
    "The scheduled run on $run_date reported the following."
)

# Part 5: the remediation request. Same text for every scenario, level and model.
TASK = (
    "Diagnose the failure and recommend a remediation. Base your answer on the "
    "information above. Where you need something that is not given, state it "
    "as an assumption rather than as a fact.\n\n"
    "Use exactly these four headings:\n"
    "### Root cause\n"
    "What went wrong and why, in a few sentences.\n"
    "### Fix\n"
    "The specific change to make. Name the exact models, sources, columns, "
    "files or settings involved, and include the SQL or YAML change where one "
    "is needed. If the change belongs outside the dbt project, say what should "
    "change and where.\n"
    "### Verification\n"
    "How to confirm the fix worked: the dbt command(s) or SQL query to run, "
    "and the expected result.\n"
    "### Assumptions\n"
    "Anything you assumed that the information above does not state.\n\n"
    "Keep the answer under 500 words, not counting code."
)


def load_scenario(scenario_id: str, scenarios_dir=None) -> dict:
    """scenarios_dir defaults to the 15 study scenarios; the pilot lives in config.PILOT_DIR."""
    folder = scenarios_dir or config.SCENARIOS_DIR
    return json.loads((folder / scenario_id / "scenario.json").read_text())


def render_part(scenario: dict, part: int) -> str:
    """One part as it appears in the prompt: heading + body."""
    if part == 1:
        intro = INTRO.substitute(run_date=scenario["as_of"][:10])
        return f"{intro}\n\n{HEADINGS[1]}\n{scenario[PART_FIELDS[1]].strip()}"
    if part == 5:
        return f"{HEADINGS[5]}\n{TASK}"
    return f"{HEADINGS[part]}\n{scenario[PART_FIELDS[part]].strip()}"


def build_prompt(scenario: dict, level: str) -> str:
    """The full prompt text for one scenario at one context level."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; expected one of {list(LEVELS)}")
    return "\n\n".join(render_part(scenario, p) for p in LEVELS[level])


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def approx_tokens(text: str) -> int:
    """Rough size (4 characters per token). Providers report exact counts per call."""
    return len(text) // 4
