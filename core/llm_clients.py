"""One uniform interface to the three LLMs.

    result = call_model("claude", "your prompt")
    result.text, result.model_version, result.input_tokens, ...

Every provider returns the same `LLMResult` fields, so the experiment runner
never needs provider-specific code. `call_with_retry` wraps `call_model` with
exponential backoff for transient errors (rate limits, 5xx, network).

Design notes
- Plain SDK calls, no LangChain.
- No server-side model fallbacks: if a model refuses, we log the refusal
  (stop_reason) instead of silently answering with a different model, which
  would contaminate the "model" variable of the experiment.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import anthropic
import ollama
import openai

from core import config


@dataclass
class LLMResult:
    model_key: str              # "gpt" | "claude" | "llama"
    model_requested: str        # the pinned ID we asked for
    model_version: str          # the version the provider says actually answered
    text: str                   # the model's answer (visible text only)
    input_tokens: int | None    # provider-reported prompt tokens
    output_tokens: int | None   # provider-reported output tokens
    latency_s: float            # wall-clock seconds for the call
    stop_reason: str | None     # e.g. end_turn / stop / max_tokens / refusal
    provider_response_id: str | None
    request_params: dict        # exactly what we sent (except the prompt)
    extra: dict = field(default_factory=dict)  # provider-specific diagnostics

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- clients (created once)
@lru_cache(maxsize=1)
def _openai_client() -> openai.OpenAI:
    # max_retries=0: retries are handled by call_with_retry so they are logged
    return openai.OpenAI(max_retries=0, timeout=300)


@lru_cache(maxsize=1)
def _anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=0, timeout=300)


@lru_cache(maxsize=1)
def _ollama_client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST, timeout=600)


@lru_cache(maxsize=4)
def ollama_digest(model_id: str) -> str:
    """Short digest of the local model build, e.g. '365c0bd3c000'. This is the
    local equivalent of a pinned version string."""
    for m in _ollama_client().list().models:
        if m.model == model_id:
            return m.digest[:12]
    return "unknown"


# ---------------------------------------------------------------- providers
def _call_openai(model_id: str, prompt: str, temperature: float, max_tokens: int, **_) -> dict:
    params = {"model": model_id, "temperature": temperature, "max_output_tokens": max_tokens}
    if config.OPENAI_REASONING_EFFORT:
        params["reasoning"] = {"effort": config.OPENAI_REASONING_EFFORT}

    t0 = time.perf_counter()
    resp = _openai_client().responses.create(input=prompt, **params)
    latency = time.perf_counter() - t0

    stop = resp.status  # "completed" or "incomplete"
    if resp.status == "incomplete" and resp.incomplete_details:
        stop = f"incomplete:{resp.incomplete_details.reason}"  # e.g. max_output_tokens
    return {
        "model_version": resp.model,
        "text": resp.output_text or "",
        "input_tokens": resp.usage.input_tokens if resp.usage else None,
        "output_tokens": resp.usage.output_tokens if resp.usage else None,
        "latency_s": latency,
        "stop_reason": stop,
        "provider_response_id": resp.id,
        "request_params": params,
    }


def _call_anthropic(model_id: str, prompt: str, temperature: float, max_tokens: int, **_) -> dict:
    params = {"model": model_id, "max_tokens": max_tokens}
    if config.ANTHROPIC_THINKING:
        params["thinking"] = {"type": config.ANTHROPIC_THINKING}

    t0 = time.perf_counter()
    # anthropic SDK 1.x removed `temperature` from the method signature, but the
    # API still accepts the field, so it goes in extra_body (merged into the JSON).
    resp = _anthropic_client().messages.create(
        messages=[{"role": "user", "content": prompt}],
        extra_body={"temperature": temperature},
        **params,
    )
    params["temperature"] = temperature  # log it alongside the other params
    latency = time.perf_counter() - t0

    # The response is a list of blocks; keep only the visible text blocks
    text = "".join(block.text for block in resp.content if block.type == "text")
    return {
        "model_version": resp.model,
        "text": text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "latency_s": latency,
        "stop_reason": resp.stop_reason,
        "provider_response_id": resp.id,
        "request_params": params,
    }


def _call_ollama(model_id: str, prompt: str, temperature: float, max_tokens: int,
                 seed: int | None = None, num_ctx: int | None = None, **_) -> dict:
    num_ctx = num_ctx or config.OLLAMA_NUM_CTX
    # num_ctx MUST be passed explicitly — Ollama's default context is smaller and
    # it truncates long prompts without raising an error.
    options = {"temperature": temperature, "num_ctx": num_ctx, "num_predict": max_tokens}
    if seed is not None:
        options["seed"] = seed  # makes local runs reproducible

    t0 = time.perf_counter()
    resp = _ollama_client().chat(
        model=model_id, messages=[{"role": "user", "content": prompt}], options=options
    )
    latency = time.perf_counter() - t0

    prompt_tokens = resp.prompt_eval_count
    return {
        "model_version": f"{resp.model}@{ollama_digest(model_id)}",
        "text": resp.message.content or "",
        "input_tokens": prompt_tokens,
        "output_tokens": resp.eval_count,
        "latency_s": latency,
        "stop_reason": resp.done_reason,  # "stop" or "length"
        "provider_response_id": None,     # Ollama has no response IDs
        "request_params": {"model": model_id, "options": options},
        "extra": {
            "load_duration_s": (resp.load_duration or 0) / 1e9,
            # If prompt + max output exceed the window, Ollama silently drops tokens
            "context_overflow_risk": bool(prompt_tokens and prompt_tokens + max_tokens > num_ctx),
        },
    }


_PROVIDERS = {"openai": _call_openai, "anthropic": _call_anthropic, "ollama": _call_ollama}


# ---------------------------------------------------------------- public API
def call_model(model_key: str, prompt: str, *, temperature: float | None = None,
               max_tokens: int | None = None, seed: int | None = None,
               num_ctx: int | None = None) -> LLMResult:
    """Send one prompt to one model. Settings default to the pinned config values."""
    spec = config.MODELS[model_key]
    raw = _PROVIDERS[spec["provider"]](
        spec["model_id"],
        prompt,
        temperature=config.TEMPERATURE if temperature is None else temperature,
        max_tokens=max_tokens or config.MAX_OUTPUT_TOKENS,
        seed=seed,
        num_ctx=num_ctx,
    )
    return LLMResult(model_key=model_key, model_requested=spec["model_id"], **raw)


def is_retryable(exc: Exception) -> bool:
    """Transient errors worth retrying: network problems, timeouts, 408/409/429, 5xx."""
    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError,
                        ConnectionError, TimeoutError)):
        return True
    # OpenAI also uses 429 for "no credit left"; waiting does not fix that
    if getattr(exc, "type", None) == "insufficient_quota":
        return False
    status = getattr(exc, "status_code", None)
    return status is not None and (status in (408, 409, 429) or status >= 500)


def call_with_retry(model_key: str, prompt: str, *, max_attempts: int = 6,
                    base_delay_s: float = 2.0, **kwargs) -> LLMResult:
    """call_model with exponential backoff (2s, 4s, 8s, ... capped at 60s).
    Non-retryable errors (e.g. 400 bad request, 401 bad key) are raised immediately."""
    for attempt in range(1, max_attempts + 1):
        try:
            return call_model(model_key, prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001 — we re-raise anything non-transient
            if not is_retryable(exc) or attempt == max_attempts:
                raise
            delay = min(base_delay_s * 2 ** (attempt - 1), 60)
            print(f"  [retry {attempt}/{max_attempts - 1}] {model_key}: "
                  f"{type(exc).__name__} — waiting {delay:.0f}s")
            time.sleep(delay)
    raise RuntimeError("unreachable")
