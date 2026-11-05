"""CHECKPOINT 1 — check that all three models answer, and verify the settings
the experiment depends on.

    python scripts/test_connection.py

Checks
  1. Pinned model IDs exist (asks each provider's models endpoint / Ollama).
  2. Hello test: the same short prompt to all 3 models with the experiment's
     real settings (temperature, max tokens, reasoning level). Prints replies.
  3. Temperature probe: is temperature=0.7 accepted by the cloud models?
     (Evidence for the temperature decision in docs/decisions_log.md.)
  4. llama3 context-window check: a ~6,000-token prompt with a code word early
     in the log (line 61 of 451), sent once with num_ctx=2048 and once with the
     configured num_ctx. Shows whether long prompts get truncated.

Exit code is 0 only if checks 1, 2 and 4 pass (check 3 is informational).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core` importable

from core import config  # noqa: E402
from core.llm_clients import _anthropic_client, _ollama_client, _openai_client, call_model, ollama_digest  # noqa: E402

HELLO_PROMPT = (
    "In one sentence, what does the command `dbt build` do? "
    "Start your answer with the word READY."
)


def header(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def key_present(model_key: str) -> bool:
    provider = config.MODELS[model_key]["provider"]
    if provider == "openai":
        return bool(config._env("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(config._env("ANTHROPIC_API_KEY"))
    return True  # Ollama needs no key


# ---------------------------------------------------------------- check 1
def check_model_ids() -> dict[str, bool]:
    header("1. Pinned model IDs exist")
    ok = {}
    for key, spec in config.MODELS.items():
        mid = spec["model_id"]
        if not key_present(key):
            print(f"  [SKIP] {key:7s} {mid}: API key missing in .env")
            ok[key] = False
            continue
        try:
            if spec["provider"] == "openai":
                info = _openai_client().models.retrieve(mid)
                detail = f"owned_by={info.owned_by}"
            elif spec["provider"] == "anthropic":
                info = _anthropic_client().models.retrieve(mid)
                detail = f"display_name='{info.display_name}'"
            else:
                digest = ollama_digest(mid)
                if digest == "unknown":
                    raise RuntimeError(f"not pulled — run: ollama pull {mid}")
                detail = f"digest={digest}"
            print(f"  [PASS] {key:7s} {mid}  ({detail})")
            ok[key] = True
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {key:7s} {mid}: {type(exc).__name__}: {exc}")
            ok[key] = False
    return ok


# ---------------------------------------------------------------- check 2
def check_hello(available: dict[str, bool]) -> dict[str, bool]:
    header(f"2. Hello test (temperature={config.TEMPERATURE}, max_tokens={config.MAX_OUTPUT_TOKENS})")
    print(f"  Prompt: {HELLO_PROMPT}")
    ok = {}
    for key in config.MODELS:
        if not available.get(key):
            ok[key] = False
            continue
        try:
            r = call_model(key, HELLO_PROMPT, seed=config.GLOBAL_SEED)
            passed = bool(r.text.strip())
            print(f"\n  [{'PASS' if passed else 'FAIL'}] {key} -> answered by: {r.model_version}")
            print(f"     tokens in/out: {r.input_tokens}/{r.output_tokens}   "
                  f"latency: {r.latency_s:.1f}s   stop_reason: {r.stop_reason}")
            print(f"     params sent: {r.request_params}")
            print(f"     reply: {r.text.strip()[:400]}")
            ok[key] = passed
        except Exception as exc:  # noqa: BLE001
            print(f"\n  [FAIL] {key}: {type(exc).__name__}: {exc}")
            ok[key] = False
    return ok


# ---------------------------------------------------------------- check 3
def probe_temperature(available: dict[str, bool]) -> dict[str, str]:
    header("3. Temperature probe: is temperature=0.7 accepted? (informational)")
    out = {}
    for key in ("gpt", "claude"):
        if not available.get(key):
            out[key] = "skipped"
            continue
        try:
            r = call_model(key, "Say OK.", temperature=0.7, max_tokens=32)
            out[key] = f"ACCEPTED (reply: {r.text.strip()[:40]!r})"
        except Exception as exc:  # noqa: BLE001
            out[key] = f"REJECTED — {type(exc).__name__}: {str(exc)[:250]}"
        print(f"  {key:7s} {config.MODELS[key]['model_id']}: {out[key]}")
    return out


# ---------------------------------------------------------------- check 4
def check_llama_context() -> bool:
    header(f"4. llama3 context window (num_ctx={config.OLLAMA_NUM_CTX}) — truncation check")
    # Ollama keeps the first few tokens (num_keep) and the END of an over-long
    # prompt and silently drops the MIDDLE — exactly where our context parts 2-4
    # will sit. So the code word goes in the middle, like real context would.
    lines = [f"Log line {i:04d}: dbt job finished with status success." for i in range(1, 451)]
    lines.insert(60, "IMPORTANT: the code word is PELICAN-42.")
    prompt = (
        "Read the following dbt job log carefully.\n\n"
        + "\n".join(lines)
        + "\n\nQuestion: what code word appeared in the log above? Answer with the code word only."
    )
    print(f"  Prompt length: {len(prompt):,} characters (~{len(prompt) // 4:,} tokens); "
          "code word is on line 61 of the log")
    results = {}
    # 2048 first, configured value last, so the model stays loaded with the real setting
    for num_ctx in (2048, config.OLLAMA_NUM_CTX):
        r = call_model("llama", prompt, temperature=0.0, max_tokens=20, seed=config.GLOBAL_SEED, num_ctx=num_ctx)
        recalled = "PELICAN" in r.text.upper()
        results[num_ctx] = (r.input_tokens, recalled)
        print(f"  num_ctx={num_ctx:5d}: tokens the model actually read={r.input_tokens:5d}  "
              f"code word recalled={recalled}  reply={r.text.strip()[:40]!r}")

    small_tokens, _ = results[2048]
    full_tokens, full_recalled = results[config.OLLAMA_NUM_CTX]
    passed = full_tokens > small_tokens and full_recalled
    if passed:
        print(f"  -> With num_ctx=2048, {full_tokens - small_tokens:,} of {full_tokens:,} prompt tokens "
              "were silently dropped.\n     With the configured num_ctx the whole prompt is read.")
    else:
        print("  -> FAIL: the configured num_ctx did not read the full prompt (or the model missed the word).")
    return passed


def main() -> int:
    header("Configuration")
    for key, spec in config.MODELS.items():
        print(f"  {key:7s} provider={spec['provider']:9s} model_id={spec['model_id']}")
    print(f"  settings: {config.generation_settings()}")

    available = check_model_ids()
    hello = check_hello(available)
    probe = probe_temperature(available)
    ctx_ok = check_llama_context() if available.get("llama") else False

    header("Summary")
    for key in config.MODELS:
        print(f"  {key:7s} model id: {'PASS' if available.get(key) else 'FAIL'}   "
              f"answers: {'PASS' if hello.get(key) else 'FAIL'}")
    print(f"  llama context window: {'PASS' if ctx_ok else 'FAIL'}")
    for key, verdict in probe.items():
        print(f"  temperature=0.7 on {key}: {verdict.split(' ')[0]}")

    all_ok = all(available.values()) and all(hello.values()) and ctx_ok
    print(f"\n  CHECKPOINT 1: {'ALL 3 MODELS ANSWER' if all_ok else 'NOT YET — see failures above'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
