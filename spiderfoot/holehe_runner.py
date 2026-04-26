"""Asyncio bridge + provider adapter for holehe.

holehe ships ~120 small async modules that each probe one service for
account existence. This module:

- Discovers all of them via holehe's own ``import_submodules`` /
  ``get_functions`` helpers (cached after first call).
- Runs them concurrently against a single email under one shared
  ``httpx.AsyncClient``.
- Wraps the gather in ``asyncio.wait_for`` so a slow provider can't
  exceed the caller's wall-clock budget.
- Catches per-provider exceptions so one broken upstream module can't
  kill the rest.

No SpiderFoot imports — testable as a standalone unit.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

_log = logging.getLogger("spiderfoot.holehe_runner")

# Providers that holehe upstream marks broken or that consistently 5xx
# on Apple Silicon / GHA runners. Extend conservatively; user can also
# add via the ``skip_providers`` module option.
_DEFAULT_SKIP = frozenset({
    # Empty by default; populate as we learn which providers add noise.
})

_provider_funcs_cache: "list | None" = None


@dataclass(frozen=True)
class HoleheHit:
    """One confirmed account hit returned by a holehe provider."""
    provider: str
    domain: str


def _get_provider_funcs():
    """Discover and cache the holehe provider coroutine list.

    Imports lazily so a missing holehe install only fails when the
    runner is actually invoked, not at module-import time.

    Returns:
        List of holehe provider async functions.
    """
    global _provider_funcs_cache
    if _provider_funcs_cache is None:
        from holehe.core import import_submodules, get_functions
        mods = import_submodules("holehe.modules")
        _provider_funcs_cache = get_functions(mods)
    return _provider_funcs_cache  # noqa: R504


def _provider_name(func) -> str:
    """Return the short provider name from a holehe func.

    Args:
        func: A holehe provider coroutine (its ``__module__`` ends in the name).

    Returns:
        Short provider name, e.g. ``github``.
    """
    return func.__module__.rsplit(".", 1)[-1]


async def _probe_email_async(email: str, funcs, timeout_s: float) -> list:
    """Run all ``funcs`` concurrently against ``email``.

    Args:
        email: Address to probe.
        funcs: Iterable of holehe provider coroutines.
        timeout_s: Wall-clock cap for the whole batch.

    Returns:
        Raw ``out`` list as populated by the providers (dicts).
    """
    import httpx

    out: list = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        async def _safe(f):
            try:
                await f(email, client, out)
            except Exception as exc:
                _log.debug("provider %s raised: %s", _provider_name(f), exc)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(_safe(f) for f in funcs)),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            _log.debug("probe of %s timed out after %.1fs", email, timeout_s)
    return out


def probe_email(
    email: str,
    *,
    skip: "Iterable[str]",
    timeout_s: float,
) -> "list[HoleheHit]":
    """Probe ``email`` against every holehe provider not in ``skip``.

    Providers that raise, time out, return ``rateLimit=True``, or report
    ``exists != True`` are silently omitted (debug-logged). The whole
    batch is bounded by ``timeout_s``.

    Args:
        email: Address to probe.
        skip: Provider names to skip (unioned with the built-in skip list).
        timeout_s: Wall-clock cap in seconds for the whole batch.

    Returns:
        List of confirmed hits, possibly empty.
    """
    skip_set = set(skip) | _DEFAULT_SKIP
    funcs = [
        f for f in _get_provider_funcs()
        if _provider_name(f) not in skip_set
    ]
    if not funcs:
        return []

    raw = asyncio.run(_probe_email_async(email, funcs, timeout_s))

    hits: "list[HoleheHit]" = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("exists") is True and entry.get("rateLimit") is False:
            name = entry.get("name") or ""
            domain = entry.get("domain") or ""
            if name and domain:
                hits.append(HoleheHit(provider=name, domain=domain))
    return hits
