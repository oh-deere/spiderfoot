# `sfp_holehe` — Account-existence probe via holehe

**Status:** Design (2026-04-26)
**Backlog item:** "Holehe account-existence module" (BACKLOG.md, Low priority, Small)
**Author:** Claude (with Ola)

## Goal

Add a SpiderFoot module that, for each `EMAILADDR` event, asks holehe ("does this email have a registered account at any of these ~120 services?") and emits an `ACCOUNT_EXTERNAL_OWNED` event for each confirmed match. Fills the OSINT gap left by removing `sfp_haveibeenpwned` / `sfp_emailrep` / `sfp_dehashed` in the Tier 2 audit.

## Non-goals

- No password breach detection (different signal — `ACCOUNT_EXTERNAL_OWNED` is "active account exists", not "credential leaked").
- No subprocess CLI invocation (`holehe email@example.com`) — library-only.
- No per-provider configuration (e.g. "only check these 5 services") beyond a blocklist. Curated allow-list is overkill for a probe module.
- No rate-limit / cooldown logic. Each scan is independent; if a provider returns `rateLimit=True` we silently skip and let the user re-run later.

## Architecture

Two units, with strict separation:

### `spiderfoot/holehe_runner.py` — pure adapter

No SpiderFoot imports. Owns everything holehe-specific:

- **Provider discovery.** Walk `holehe.modules` packages once at first call, cache the resolved list of `(provider_name, callable)` tuples. Each holehe provider is a coroutine `async def f(email, client, out): ...` where `out` is a list it appends a result dict to.
- **Asyncio bridge.** Expose one synchronous function `probe_email(email, *, skip, timeout_s) -> list[HoleheHit]`. Internally calls `asyncio.run(_probe_email(...))`.
- **Concurrent gather.** Inside `_probe_email`, create one shared `httpx.AsyncClient`, schedule every provider as a task, gather with `return_exceptions=True`, wrap in `asyncio.wait_for(timeout=timeout_s)`.
- **Per-provider exception isolation.** A provider that raises (upstream holehe API change, unexpected response shape) is debug-logged and skipped; other providers continue.
- **Result filtering.** Only collect entries where `entry.get("exists") is True` *and* `entry.get("rateLimit") is False`. Skip rate-limited responses, `exists is False/None`, exceptions, and missing keys.
- **Built-in skip list.** Module-level `_DEFAULT_SKIP: frozenset[str]` of providers known broken upstream. Updated as holehe evolves.

```python
@dataclass(frozen=True)
class HoleheHit:
    provider: str   # e.g. "github"
    domain: str     # e.g. "github.com"
```

The runner has no module loader / event-bus knowledge. It can be unit-tested with a fake `holehe.modules` namespace.

### `modules/sfp_holehe.py` — SpiderFoot glue

Owns the meta block, watching `EMAILADDR`, calling `probe_email`, the `max_emails` counter, formatting the `ACCOUNT_EXTERNAL_OWNED` data string, emitting events, and `errorState`. ~80 lines. Never imports `asyncio` or `holehe.modules`.

```python
from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.holehe_runner import probe_email

class sfp_holehe(SpiderFootPlugin):
    meta = {
        "name": "Holehe Account Discovery",
        "summary": "Probe ~120 services to see if a registered account "
                   "exists for an email address (via holehe).",
        "flags": ["invasive"],
        "useCases": ["Investigate"],
        "categories": ["Social Media"],
        "dataSource": {
            "website": "https://github.com/megadose/holehe",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://github.com/megadose/holehe"],
            "description": "Open-source library that uses password-reset / "
                           "signup differential responses to detect whether "
                           "an email is registered at a service. No API keys.",
        },
    }

    opts = {
        "max_emails": 25,
        "timeout_s": 60,
        "skip_providers": "",
    }

    optdescs = {
        "max_emails": "Max emails to probe per scan (default 25). Holehe is "
                      "slow and invasive; keep this small.",
        "timeout_s": "Per-email wall-clock timeout in seconds (default 60).",
        "skip_providers": "Comma-separated provider names to skip, in addition "
                          "to the built-in skip list of broken providers.",
    }

    errorState = False
```

## Module options

| Opt | Default | Notes |
|---|---|---|
| `max_emails` | 25 | Per-scan cap. Holehe takes ~5-15s per email; 25 ≈ ~3-6 min. |
| `timeout_s` | 60 | Wall-clock per email. Provider HTTP timeouts are 10-30s; 60s lets the gather finish even with several slow providers. |
| `skip_providers` | `""` | Comma-separated, appended to `_DEFAULT_SKIP`. Whitespace tolerated. |

## Event flow

```
EMAILADDR event arrives
  ↓
self._processed >= max_emails? → drop, debug-log, return
  ↓
self.errorState? → return
  ↓
hits = probe_email(email, skip=combined_skip, timeout_s=opts["timeout_s"])
  ↓
self._processed += 1
  ↓
for hit in hits:
    emit ACCOUNT_EXTERNAL_OWNED with data = f"Holehe: {hit.provider} (Domain: {hit.domain})\n<SFURL>https://{hit.domain}</SFURL>"
```

`probe_email` raises only on a fatal runner failure (e.g. holehe import broken, asyncio loop error). Caught by the module → `errorState = True`, error-logged, future events no-op.

## Error contract

| Failure | Where caught | Behavior |
|---|---|---|
| `import holehe` fails | `setup()` (lazy import on first event use) | log error, `errorState = True`, no-op |
| Per-provider exception | `holehe_runner._probe_email` | debug-log, skip provider, continue |
| `asyncio.wait_for` timeout | `holehe_runner.probe_email` | debug-log "email X timed out", return whatever hits already arrived |
| Runner unrecoverable error | `sfp_holehe.handleEvent` | error-log, `errorState = True`, no-op |

`rateLimit=True` and `exists is None` results are quietly skipped — they don't indicate a hit and don't indicate a problem.

## Distribution

- `requirements.txt`: add `holehe>=1.61`. Hard dep, not optional. holehe pulls `httpx` + `tldextract` + a few small libs (~3 MB total).
- `Dockerfile`: no change — already runs `pip install -r requirements.txt`.
- No new env vars.
- No new event types — `ACCOUNT_EXTERNAL_OWNED` is the existing canonical type, also produced by `sfp_accounts` and `sfp_gravatar`.

## Testing

### `test/unit/spiderfoot/test_holehe_runner.py` (~6 tests)

Mock holehe at the import level (use `sys.modules` injection or `unittest.mock.patch` against the runner's import statement):

1. **Provider discovery yields all non-skipped modules.** Inject 4 fake provider coroutines, skip 1, verify the runner runs the remaining 3.
2. **Per-provider exception isolation.** One coroutine raises; others succeed; `probe_email` returns hits from the successful ones.
3. **Wall-clock timeout returns partial results.** Two providers complete quickly with hits, one hangs; with `timeout_s=0.1` the call returns the two hits and the slow one is cancelled.
4. **`used=False` and `rateLimit=True` results are filtered out.** Mixed result list → only `used=True` entries become `HoleheHit`s.
5. **Empty hit list when no provider returns `used=True`.** Returns `[]`, not error.
6. **Skip set is honored.** Provider name in `skip` is never invoked.

### `test/unit/modules/test_sfp_holehe.py` (~6 tests)

Mock `spiderfoot.holehe_runner.probe_email`:

1. **Watches `EMAILADDR` only.** `watchedEvents()` returns `["EMAILADDR"]`.
2. **Produces `ACCOUNT_EXTERNAL_OWNED`.** `producedEvents()` returns `["ACCOUNT_EXTERNAL_OWNED"]`.
3. **`max_emails` cap stops further probes.** With `max_emails=2`, third event triggers no `probe_email` call.
4. **Hits become events with the expected data format.** One `HoleheHit("github", "github.com")` → emitted event has `eventType == "ACCOUNT_EXTERNAL_OWNED"` and `data == "Holehe: github (Domain: github.com)\n<SFURL>https://github.com</SFURL>"`.
5. **`skip_providers` opt is parsed and forwarded to runner.** `"foo, bar"` → runner receives `{"foo", "bar"} | _DEFAULT_SKIP`.
6. **Runner exception trips errorState.** `probe_email` raises → `self.errorState is True`, subsequent `handleEvent` calls return immediately.

## CLAUDE.md update

After landing:

- Add `sfp_holehe` to the `FREE_NOAUTH_UNLIMITED` list in CLAUDE.md (count goes 96 → 97).
- Bump the audited surviving non-storage module count from 186 → 187.
- Brief note in the OhDeere integration section is unnecessary — holehe is not OhDeere infrastructure. Add a one-paragraph "Local subprocess/library modules" note if it doesn't already exist (it doesn't).

## Out of scope (explicitly deferred)

- Per-scan caching across emails. Holehe doesn't expose this; not worth building.
- Promoting hits into `SOCIAL_MEDIA` / `WEB_ACCOUNT` events. `ACCOUNT_EXTERNAL_OWNED` is the canonical type for "account exists at site"; no need to fan out.
- A separate "username via holehe" mode. Holehe also probes by username, but `sfp_accounts` already covers that surface.
- Updating the built-in `_DEFAULT_SKIP` automatically from holehe upstream. Manual review when holehe versions bump.
