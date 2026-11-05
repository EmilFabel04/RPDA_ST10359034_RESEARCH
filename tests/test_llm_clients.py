"""Which API errors are retried (no network calls)."""
import sys
from pathlib import Path

import httpx
import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.llm_clients import is_retryable  # noqa: E402


def openai_error(status: int, body: dict) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    cls = openai.RateLimitError if status == 429 else openai.InternalServerError
    return cls("error", response=response, body=body)


def test_rate_limit_and_server_errors_are_retried():
    assert is_retryable(openai_error(429, {"type": "requests", "code": "rate_limit_exceeded"}))
    assert is_retryable(openai_error(500, {"type": "server_error"}))


def test_out_of_credit_is_not_retried():
    assert not is_retryable(openai_error(429, {"type": "insufficient_quota",
                                               "code": "credit_balance_exhausted"}))
