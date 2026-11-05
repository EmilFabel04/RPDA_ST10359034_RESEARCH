"""CHECKPOINT 4 — print one scenario's three prompts and check every prompt's size.

    python scripts/show_prompts.py                    # SD01
    python scripts/show_prompts.py RC03
    python scripts/show_prompts.py --measure-llama    # exact llama3 token counts (local, free)

Writes the three prompts to docs/prompt_examples/<ID>_<level>.txt (appendix
material) and prints a size table for all 15 scenarios x 3 levels.
--measure-llama sends every full prompt to Ollama with max 1 output token and
reads back the exact prompt token count, to prove the largest prompt plus the
answer fits llama's context window.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core`/`prompts` importable

from core import config  # noqa: E402
from prompts.builder import (LEVELS, PROMPT_VERSION, approx_tokens, build_prompt,  # noqa: E402
                             load_scenario, prompt_sha256)

OUT_DIR = config.PROJECT_ROOT / "docs" / "prompt_examples"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_id", nargs="?", default="SD01")
    parser.add_argument("--measure-llama", action="store_true")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for level, parts in LEVELS.items():
        prompt = build_prompt(scenario, level)
        path = OUT_DIR / f"{args.scenario_id}_{level}.txt"
        path.write_text(prompt + "\n")
        print(f"\n{'=' * 78}\n{args.scenario_id} · {level} · parts {'+'.join(map(str, parts))} · "
              f"~{approx_tokens(prompt)} tokens · sha256 {prompt_sha256(prompt)[:12]} · "
              f"prompt {PROMPT_VERSION}\n{'=' * 78}\n{prompt}")
    print(f"\nSaved to {OUT_DIR.relative_to(config.PROJECT_ROOT)}/")

    ids = sorted(p.name for p in config.SCENARIOS_DIR.iterdir() if (p / "scenario.json").exists())
    print(f"\nPrompt sizes, ~tokens (chars/4){'; llama = exact llama3 count of full' if args.measure_llama else ''}")
    print(f"  {'id':5s} {'minimal':>8s} {'partial':>8s} {'full':>8s}" + (f" {'llama':>8s}" if args.measure_llama else ""))
    worst = 0
    for sid in ids:
        s = load_scenario(sid)
        sizes = [approx_tokens(build_prompt(s, lvl)) for lvl in LEVELS]
        row = f"  {sid:5s} " + " ".join(f"{n:8d}" for n in sizes)
        if args.measure_llama:
            from core.llm_clients import call_model  # only needed here
            n = call_model("llama", build_prompt(s, "full"), max_tokens=1, seed=config.GLOBAL_SEED).input_tokens
            worst = max(worst, n)
            row += f" {n:8d}"
        print(row)

    if args.measure_llama:
        need = worst + config.MAX_OUTPUT_TOKENS
        ok = need <= config.OLLAMA_NUM_CTX
        print(f"\nLargest llama prompt {worst} + max output {config.MAX_OUTPUT_TOKENS} = {need} "
              f"of num_ctx {config.OLLAMA_NUM_CTX}: {'FITS' if ok else 'DOES NOT FIT'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
