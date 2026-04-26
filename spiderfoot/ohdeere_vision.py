"""Submit + poll helper for ohdeere-llm-gateway vision jobs.

Same async-serial gateway as text completions: POST /api/v1/jobs with
JSON ``{model, prompt, image}`` (image base64-encoded), then poll
GET /api/v1/jobs/{id}. ``describe_image`` wraps this into a blocking
call that returns the model's description string or raises a typed
error from :mod:`spiderfoot.ohdeere_llm`.

Single image per job by gateway design; Gemma4 resizes internally to
896×896, so caller-side downscaling is unnecessary. Hard cap on raw
input is 10 MB to stay below the gateway's ~14M base64-char limit.
"""
import base64
import logging
import time

from spiderfoot.ohdeere_client import (
    OhDeereClient,
    OhDeereClientError,
    get_client,
)
from spiderfoot.ohdeere_llm import (
    OhDeereLLMError,
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
)

_log = logging.getLogger("spiderfoot.ohdeere_vision")

_IMAGE_HARD_CAP_BYTES = 10 * 1024 * 1024
_PROMPT_HARD_CAP = 200_000
_POLL_BACKOFF_SEQUENCE = (1.0, 2.0, 4.0, 8.0, 10.0)


class OhDeereVisionImageTooLarge(OhDeereLLMError):
    """Raised when ``image_data`` exceeds the gateway's size limit."""


def describe_image(
    image_data: bytes,
    prompt: str = "Describe this image.",
    *,
    base_url: str,
    model: str = "gemma4:e4b",
    options: "dict | None" = None,
    timeout_s: int = 300,
    client: "OhDeereClient | None" = None,
) -> str:
    """Submit ``image_data`` + ``prompt`` to the gateway, return the description.

    Args:
        image_data: Raw image bytes (PNG, JPEG, etc). Hard cap 10 MB.
        prompt: Instruction text accompanying the image.
        base_url: Base URL of ohdeere-llm-gateway.
        model: Ollama multimodal model tag. Defaults to ``gemma4:e4b``.
        options: Optional pass-through options dict for the gateway.
        timeout_s: Wall-clock budget in seconds before raising OhDeereLLMTimeout.
        client: Optional OhDeereClient to inject (mainly for tests).

    Returns:
        The model's description string from the DONE job payload.

    Raises:
        OhDeereClientError: The client helper is disabled (env vars unset).
        OhDeereVisionImageTooLarge: ``image_data`` exceeds 10 MB.
        OhDeereLLMTimeout: Polling exceeded ``timeout_s``.
        OhDeereLLMFailure: Gateway reported FAILED or CANCELLED.
    """
    c = client if client is not None else get_client()
    if c.disabled:
        raise OhDeereClientError(
            "OhDeere client disabled — OHDEERE_CLIENT_ID/SECRET not set"
        )

    if len(image_data) > _IMAGE_HARD_CAP_BYTES:
        raise OhDeereVisionImageTooLarge(
            f"image is {len(image_data)} bytes, "
            f"exceeds {_IMAGE_HARD_CAP_BYTES}-byte cap"
        )

    if len(prompt) > _PROMPT_HARD_CAP:
        _log.warning(
            "prompt truncated from %d to %d chars",
            len(prompt), _PROMPT_HARD_CAP,
        )
        prompt = prompt[:_PROMPT_HARD_CAP]

    encoded = base64.b64encode(image_data).decode("ascii")
    body = {
        "model": model,
        "prompt": prompt,
        "image": encoded,
        "options": options or {},
    }
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
