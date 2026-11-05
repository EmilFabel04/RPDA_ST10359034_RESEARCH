"""Central configuration.

Loads `.env` once and exposes every experiment setting as a module constant, so
there is exactly one place where model IDs, temperature, token limits and seeds
are defined. Every other script imports from here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------- paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt_project"
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"
PILOT_DIR = PROJECT_ROOT / "data" / "pilot"            # calibration scenario, not part of the results
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
SCORING_DIR = RESULTS_DIR / "scoring"     # blinding key, rater assignments, scoring pages
MOCK_DIR = RESULTS_DIR / "mock"           # MOCK scores for building the analysis; never results

# override=False: a variable already set in your shell wins over .env
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env(name: str, default: str | None = None) -> str | None:
    """Read an env var, treating an empty string as 'not set'."""
    value = os.getenv(name, "").strip()
    return value if value else default


# ---------------------------------------------------------------- pinned models
OPENAI_MODEL_ID = _env("OPENAI_MODEL_ID", "gpt-5.5-2026-04-23")
ANTHROPIC_MODEL_ID = _env("ANTHROPIC_MODEL_ID", "claude-sonnet-5-5")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3:8b")
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_NUM_CTX = int(_env("OLLAMA_NUM_CTX", "8192"))

# ---------------------------------------------------------------- generation settings
TEMPERATURE = float(_env("TEMPERATURE", "1.0"))
MAX_OUTPUT_TOKENS = int(_env("MAX_OUTPUT_TOKENS", "2048"))
OPENAI_REASONING_EFFORT = _env("OPENAI_REASONING_EFFORT", "none")
ANTHROPIC_THINKING = _env("ANTHROPIC_THINKING", "between_tools")

# ---------------------------------------------------------------- reproducibility
GLOBAL_SEED = int(_env("GLOBAL_SEED", "42"))

# ---------------------------------------------------------------- model registry
# The short key (left) is what appears in results files; it stays stable even
# if a pinned ID changes. The exact version string is logged separately per call.
MODELS = {
    "gpt": {"provider": "openai", "model_id": OPENAI_MODEL_ID},
    "claude": {"provider": "anthropic", "model_id": ANTHROPIC_MODEL_ID},
    "llama": {"provider": "ollama", "model_id": OLLAMA_MODEL},
}

# USD per 1M tokens (input, output), from provider pricing pages on 2026-10-12.
# Used only for the cost estimate printed before the experiment runs.
PRICES_PER_MTOK = {
    "gpt": (5.00, 30.00),     # gpt-5.5
    "claude": (2.00, 10.00),  # claude-sonnet-5-5
    "llama": (0.0, 0.0),      # local
}


def generation_settings() -> dict:
    """Snapshot of the settings that must be identical across models (logged with results)."""
    return {
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "openai_reasoning_effort": OPENAI_REASONING_EFFORT,
        "anthropic_thinking": ANTHROPIC_THINKING,
        "ollama_num_ctx": OLLAMA_NUM_CTX,
    }
