"""Submit + poll helper for ohdeere-llm-gateway, built on OhDeereClient.

Gateway is async with serial processing: submit via POST /api/v1/jobs,
poll GET /api/v1/jobs/{id} until status is DONE / FAILED / CANCELLED.
``run_prompt`` wraps this into a blocking call that returns the model's
response string or raises a typed error.

Stateless. Thread-safety inherits from OhDeereClient (singleton with
per-scope locks).
"""
import logging
import time

from spiderfoot.ohdeere_client import (
    OhDeereClient,
    OhDeereClientError,
    get_client,
)

_log = logging.getLogger("spiderfoot.ohdeere_llm")

_PROMPT_HARD_CAP = 200_000
_POLL_BACKOFF_SEQUENCE = (1.0, 2.0, 4.0, 8.0, 10.0)


class OhDeereLLMError(RuntimeError):
    """Base class for LLM-helper failures."""


class OhDeereLLMTimeout(OhDeereLLMError):
    """Raised when polling exceeds ``timeout_s`` without a terminal status."""


class OhDeereLLMFailure(OhDeereLLMError):
    """Raised when the gateway reports FAILED or CANCELLED status."""


def run_prompt(
    prompt: str,
    *,
    base_url: str,
    model: str = "gemma3:4b",
    options: "dict | None" = None,
    timeout_s: int = 300,
    client: "OhDeereClient | None" = None,
) -> str:
    """Submit ``prompt`` to the gateway, poll until complete, return the result.

    Args:
        prompt: The user prompt. Truncated to 200 000 chars with a WARNING log
            if longer.
        base_url: Base URL of ohdeere-llm-gateway.
        model: Ollama model tag. Defaults to ``gemma3:4b``.
        options: Optional pass-through options dict for the gateway.
        timeout_s: Wall-clock budget in seconds before raising OhDeereLLMTimeout.
        client: Optional OhDeereClient to inject (mainly for tests).

    Returns:
        The model's response string from the DONE job payload.

    Raises:
        OhDeereClientError: The client helper is disabled (env vars unset).
        OhDeereLLMTimeout: Polling exceeded ``timeout_s``.
        OhDeereLLMFailure: Gateway reported FAILED or CANCELLED.
    """
    c = client if client is not None else get_client()
    if c.disabled:
        raise OhDeereClientError(
            "OhDeere client disabled — OHDEERE_CLIENT_ID/SECRET not set"
        )

    if len(prompt) > _PROMPT_HARD_CAP:
        _log.warning(
            "prompt truncated from %d to %d chars",
            len(prompt), _PROMPT_HARD_CAP,
        )
        prompt = prompt[:_PROMPT_HARD_CAP]

    body = {"model": model, "prompt": prompt, "options": options or {}}
    submit_resp = c.post(
        "/api/v1/jobs",
        body,
        base_url,
        "llm:query",
    )
    job_id = submit_resp.get("id")
    if not job_id:
        raise OhDeereLLMFailure(
            f"submit returned no job id: {submit_resp}"
        )

    started = time.monotonic()
    backoff_index = 0
    while True:
        if time.monotonic() - started > timeout_s:
            raise OhDeereLLMTimeout(
                f"job {job_id} did not terminate within {timeout_s}s"
            )
        poll_resp = c.get(
            f"/api/v1/jobs/{job_id}",
            base_url,
            "llm:query",
        )
        status = poll_resp.get("status")
        _log.debug(
            "polled job_id=%s status=%s elapsed=%.1fs",
            job_id, status, time.monotonic() - started,
        )
        if status == "DONE":
            return poll_resp.get("result", "")
        if status == "FAILED":
            raise OhDeereLLMFailure(
                f"job {job_id} failed: {poll_resp.get('error', '')}"
            )
        if status == "CANCELLED":
            raise OhDeereLLMFailure(f"job {job_id} cancelled")

        delay = _POLL_BACKOFF_SEQUENCE[
            min(backoff_index, len(_POLL_BACKOFF_SEQUENCE) - 1)
        ]
        backoff_index += 1
        time.sleep(delay)
