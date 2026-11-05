"""Each context level must contain exactly its parts, cumulatively, with one shared task text."""
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config  # noqa: E402
from core.scenario_defs import CATEGORIES  # noqa: E402
from prompts.builder import (HEADINGS, LEVELS, TASK, build_prompt, load_scenario,  # noqa: E402
                             prompt_sha256)

# A fake scenario whose parts are easy to find in the prompt
FAKE = {"scenario_id": "T00", "as_of": "2026-10-13 18:00:00",
        "failure_description": "BODY-1", "model_metadata": "BODY-2",
        "lineage": "BODY-3", "historical_context": "BODY-4"}

EXPECTED_PARTS = {"minimal": {1, 5}, "partial": {1, 2, 5}, "full": {1, 2, 3, 4, 5}}

SCENARIO_IDS = sorted(p.name for p in config.SCENARIOS_DIR.iterdir() if (p / "scenario.json").exists())


@pytest.mark.parametrize("level", list(EXPECTED_PARTS))
def test_level_contains_exactly_its_parts(level):
    prompt = build_prompt(FAKE, level)
    for part in (1, 2, 3, 4):
        assert (f"BODY-{part}" in prompt) == (part in EXPECTED_PARTS[level]), (level, part)
    for part, heading in HEADINGS.items():
        assert (heading in prompt) == (part in EXPECTED_PARTS[level]), (level, heading)


def test_levels_are_cumulative_and_in_order():
    assert LEVELS == {k: tuple(sorted(v)) for k, v in EXPECTED_PARTS.items()}
    minimal, partial, full = (build_prompt(FAKE, lvl) for lvl in ("minimal", "partial", "full"))
    positions = [full.index(f"BODY-{p}") for p in (1, 2, 3, 4)] + [full.index(HEADINGS[5])]
    assert positions == sorted(positions)
    # partial is full without parts 3-4; minimal is partial without part 2
    assert partial.startswith(minimal.split(HEADINGS[5])[0].rstrip())
    assert full.startswith(partial.split(HEADINGS[5])[0].rstrip())


def test_every_prompt_ends_with_the_same_task():
    for level in LEVELS:
        assert build_prompt(FAKE, level).endswith(f"{HEADINGS[5]}\n{TASK}")


def test_prompt_cannot_depend_on_the_model():
    assert list(inspect.signature(build_prompt).parameters) == ["scenario", "level"]


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError):
        build_prompt(FAKE, "medium")


# ---------------------------------------------------------------- the 15 real scenarios
def test_all_15_scenarios_present():
    assert len(SCENARIO_IDS) == 15


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_real_prompts_are_deterministic_and_fit_llama_context(scenario_id):
    scenario = load_scenario(scenario_id)
    for level in LEVELS:
        prompt = build_prompt(scenario, level)
        assert prompt_sha256(prompt) == prompt_sha256(build_prompt(load_scenario(scenario_id), level))
        # 3 characters per token is pessimistic for llama3 (code-heavy text is ~3.5-4)
        assert len(prompt) / 3 + config.MAX_OUTPUT_TOKENS <= config.OLLAMA_NUM_CTX, (scenario_id, level)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_context_parts_do_not_leak_the_answer(scenario_id):
    scenario = load_scenario(scenario_id)
    truth = json.loads((config.SCENARIOS_DIR / scenario_id / "ground_truth.json").read_text())
    context = build_prompt(scenario, "full").split(HEADINGS[5])[0].lower()  # parts 1-4 only

    banned = ["seed", "synthetic", "scenario", "gold", "inject", "root cause", truth["title"].lower()]
    banned += [c for cat in CATEGORIES for c in (cat, cat.replace("_", " "))]
    assert [w for w in banned if w in context] == []

    gold_fix = scenario["gold_standard_remediation"]["fix"]
    sentences = [s.strip().lower() for s in re.split(r"(?<=[.:])\s+", gold_fix) if len(s.strip()) > 40]
    assert [s for s in sentences if s in context] == []
