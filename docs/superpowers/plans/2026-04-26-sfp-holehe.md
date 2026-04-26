# `sfp_holehe` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SpiderFoot module that probes `~120` services via the holehe library to find existing accounts for each `EMAILADDR` event, emitting `ACCOUNT_EXTERNAL_OWNED`.

**Architecture:** Two-unit split. `spiderfoot/holehe_runner.py` is a synchronous adapter that bridges asyncio, discovers holehe provider coroutines, gathers them concurrently per email under a wall-clock cap, and isolates per-provider exceptions. `modules/sfp_holehe.py` is the SpiderFoot glue: meta block, options, event watcher, `max_emails` counter, `errorState`, event emission. The module never imports `asyncio` or `holehe.modules`.

**Tech Stack:** Python 3.7+, holehe 1.61, httpx (vendored by holehe), asyncio. SpiderFoot's normal `SpiderFootPlugin` event-bus model. pytest + unittest.mock for tests.

**Spec:** `docs/superpowers/specs/2026-04-26-sfp-holehe-design.md`

---

## File map

| File | Purpose |
|---|---|
| `requirements.txt` | Add `holehe>=1.61`. |
| `spiderfoot/holehe_runner.py` (new) | Pure adapter: provider discovery, asyncio bridge, concurrent gather, per-provider exception isolation, `_DEFAULT_SKIP` constant. Exports `HoleheHit` dataclass + `probe_email()` function. No SpiderFoot imports. |
| `modules/sfp_holehe.py` (new) | SpiderFoot module class. Meta/opts/optdescs, `watchedEvents`, `producedEvents`, `setup`, `handleEvent`. Calls `probe_email`. ~80 lines. |
| `test/unit/spiderfoot/test_holehe_runner.py` (new) | 6 tests for the runner with fake provider coroutines. |
| `test/unit/modules/test_sfp_holehe.py` (new) | 6 tests for the module with `probe_email` mocked. |
| `CLAUDE.md` | Add `sfp_holehe` to `FREE_NOAUTH_UNLIMITED` list, bump module count. |
| `docs/superpowers/BACKLOG.md` | Mark Holehe item as shipped. |

---

## Task 1: Add `holehe` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Inspect current requirements.txt**

Run: `head -20 requirements.txt`
Expected: list of pinned deps. Confirm `holehe` is not already present.

- [ ] **Step 2: Add holehe**

Append to `requirements.txt`:

```
holehe>=1.61
```

(Add after the last existing line. Don't sort — `requirements.txt` in this repo is grouped by purpose, not alphabetized.)

- [ ] **Step 3: Install in current env**

Run: `pip3 install -r requirements.txt`
Expected: holehe + httpx + tldextract + termcolor + trio install successfully.

- [ ] **Step 4: Sanity-check holehe imports**

Run: `python3 -c "from holehe.core import import_submodules, get_functions; mods = import_submodules('holehe.modules'); funcs = get_functions(mods); print(len(funcs), 'providers')"`
Expected: `121 providers` (or close — holehe upstream may have added/removed since 1.61).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "deps: add holehe>=1.61 for sfp_holehe"
```

---

## Task 2: Runner — failing tests for `probe_email`

We use TDD. This task only writes the failing tests; the runner module doesn't exist yet, so collection itself fails — that's the red state.

**Files:**
- Create: `test/unit/spiderfoot/test_holehe_runner.py`

- [ ] **Step 1: Write the failing test file**

Create `test/unit/spiderfoot/test_holehe_runner.py`:

```python
# test_holehe_runner.py
import asyncio
import unittest
from unittest import mock

from spiderfoot.holehe_runner import HoleheHit, probe_email


def _make_provider(name, domain, exists, rate_limit=False, raises=False, slow=False):
    """Build a fake holehe-shaped async provider: f(email, client, out)."""
    async def f(email, client, out):
        if slow:
            await asyncio.sleep(10)
        if raises:
            raise RuntimeError(f"{name} blew up")
        out.append({
            "name": name,
            "domain": domain,
            "exists": exists,
            "rateLimit": rate_limit,
        })
    f.__module__ = f"holehe.modules.fake.{name}"
    return f


class TestProbeEmail(unittest.TestCase):

    def _patch_funcs(self, funcs):
        """Patch the runner's provider-list builder to return ``funcs``."""
        return mock.patch(
            "spiderfoot.holehe_runner._get_provider_funcs",
            return_value=funcs,
        )

    def test_collects_only_exists_true_and_not_rate_limited(self):
        funcs = [
            _make_provider("a", "a.com", exists=True),
            _make_provider("b", "b.com", exists=False),
            _make_provider("c", "c.com", exists=True, rate_limit=True),
            _make_provider("d", "d.com", exists=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        names = sorted(h.provider for h in hits)
        self.assertEqual(names, ["a", "d"])
        self.assertTrue(all(isinstance(h, HoleheHit) for h in hits))

    def test_per_provider_exception_isolated(self):
        funcs = [
            _make_provider("ok", "ok.com", exists=True),
            _make_provider("bad", "bad.com", exists=True, raises=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual([h.provider for h in hits], ["ok"])

    def test_skip_set_excludes_providers(self):
        called = []

        def make_recording(name):
            async def f(email, client, out):
                called.append(name)
                out.append({"name": name, "domain": f"{name}.com",
                            "exists": True, "rateLimit": False})
            f.__module__ = f"holehe.modules.fake.{name}"
            return f

        funcs = [make_recording("keep"), make_recording("drop")]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip={"drop"}, timeout_s=5)
        self.assertEqual(called, ["keep"])
        self.assertEqual([h.provider for h in hits], ["keep"])

    def test_timeout_returns_partial_results(self):
        funcs = [
            _make_provider("fast1", "f1.com", exists=True),
            _make_provider("fast2", "f2.com", exists=True),
            _make_provider("slow", "slow.com", exists=True, slow=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=0.5)
        names = sorted(h.provider for h in hits)
        self.assertEqual(names, ["fast1", "fast2"])

    def test_empty_when_no_provider_returns_exists_true(self):
        funcs = [
            _make_provider("a", "a.com", exists=False),
            _make_provider("b", "b.com", exists=False),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual(hits, [])

    def test_hit_carries_provider_and_domain(self):
        funcs = [_make_provider("github", "github.com", exists=True)]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].provider, "github")
        self.assertEqual(hits[0].domain, "github.com")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails (collection error)**

Run: `python3 -m pytest test/unit/spiderfoot/test_holehe_runner.py -v`
Expected: ImportError / ModuleNotFoundError on `spiderfoot.holehe_runner` — collection fails. That's the red state.

- [ ] **Step 3: Commit the failing tests**

```bash
git add test/unit/spiderfoot/test_holehe_runner.py
git commit -m "test: add failing tests for spiderfoot.holehe_runner"
```

---

## Task 3: Runner — implement `holehe_runner.py`

**Files:**
- Create: `spiderfoot/holehe_runner.py`

- [ ] **Step 1: Write the runner**

Create `spiderfoot/holehe_runner.py`:

```python
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
    # holehe README "broken" list — keep aligned with upstream.
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
    """
    global _provider_funcs_cache
    if _provider_funcs_cache is None:
        from holehe.core import import_submodules, get_functions
        mods = import_submodules("holehe.modules")
        _provider_funcs_cache = get_functions(mods)
    return _provider_funcs_cache


def _provider_name(func) -> str:
    """Return the short provider name (e.g. ``github``) from a holehe func."""
    return func.__module__.rsplit(".", 1)[-1]


async def _probe_email_async(email: str, funcs, timeout_s: float) -> list:
    """Run all ``funcs`` concurrently against ``email``; return raw out list."""
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

    Returns a list of confirmed hits. Providers that raise, time out,
    return ``rateLimit=True``, or report ``exists != True`` are silently
    omitted (debug-logged). The whole batch is bounded by ``timeout_s``.

    Raises:
        ImportError: holehe is not installed.
        RuntimeError: An unrecoverable adapter failure (e.g. an event-loop
            issue). Per-provider failures do *not* propagate.
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_holehe_runner.py -v`
Expected: 6 passed.

- [ ] **Step 3: Lint**

Run: `python3 -m flake8 spiderfoot/holehe_runner.py`
Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
git add spiderfoot/holehe_runner.py
git commit -m "holehe_runner: asyncio adapter for holehe providers"
```

---

## Task 4: Module — failing tests for `sfp_holehe`

**Files:**
- Create: `test/unit/modules/test_sfp_holehe.py`

- [ ] **Step 1: Inspect a sibling module test for setup pattern**

Run: `head -40 test/unit/modules/test_sfp_searxng.py`
Expected: shows the `default_options` fixture and how SpiderFoot tests instantiate a plugin. Use the same pattern.

- [ ] **Step 2: Write the failing test file**

Create `test/unit/modules/test_sfp_holehe.py`:

```python
# test_sfp_holehe.py
import unittest
from unittest import mock

import pytest

from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.holehe_runner import HoleheHit


@pytest.fixture
def module(default_options):
    """Instantiate a fresh sfp_holehe with default options + dummy target."""
    from modules.sfp_holehe import sfp_holehe
    sf_mock = mock.MagicMock()
    mod = sfp_holehe()
    mod.setup(sf_mock, dict(default_options))
    mod.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
    mod._listenerModules = []
    return mod


class TestWatchedAndProduced:

    def test_watches_emailaddr_only(self, module):
        assert module.watchedEvents() == ["EMAILADDR"]

    def test_produces_account_external_owned(self, module):
        assert module.producedEvents() == ["ACCOUNT_EXTERNAL_OWNED"]


class TestHandleEvent:

    def _make_event(self, data="user@example.com"):
        root = SpiderFootEvent("ROOT", "example.com", "", None)
        return SpiderFootEvent("EMAILADDR", data, "test_module", root)

    def test_max_emails_caps_probing(self, module):
        module.opts["max_emails"] = 2
        with mock.patch("modules.sfp_holehe.probe_email",
                        return_value=[]) as p:
            for _ in range(5):
                module.handleEvent(self._make_event())
        assert p.call_count == 2

    def test_hit_emits_account_external_owned_with_expected_format(self, module):
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            return_value=[HoleheHit(provider="github", domain="github.com")],
        ):
            module.handleEvent(self._make_event())
        assert len(emitted) == 1
        evt = emitted[0]
        assert evt.eventType == "ACCOUNT_EXTERNAL_OWNED"
        assert evt.data == (
            "Holehe: github (Domain: github.com)\n"
            "<SFURL>https://github.com</SFURL>"
        )

    def test_skip_providers_opt_forwarded_to_runner(self, module):
        module.opts["skip_providers"] = "foo, bar"
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            return_value=[],
        ) as p:
            module.handleEvent(self._make_event())
        kwargs = p.call_args.kwargs
        assert kwargs["skip"] == {"foo", "bar"}

    def test_runner_exception_trips_errorstate(self, module):
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            side_effect=RuntimeError("boom"),
        ) as p:
            module.handleEvent(self._make_event())
            module.handleEvent(self._make_event())
        assert module.errorState is True
        # Second event must short-circuit (no second call to probe_email).
        assert p.call_count == 1
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m pytest test/unit/modules/test_sfp_holehe.py -v`
Expected: ImportError on `modules.sfp_holehe`. Collection fails. Red state.

- [ ] **Step 4: Commit the failing tests**

```bash
git add test/unit/modules/test_sfp_holehe.py
git commit -m "test: add failing tests for sfp_holehe"
```

---

## Task 5: Module — implement `sfp_holehe.py`

**Files:**
- Create: `modules/sfp_holehe.py`

- [ ] **Step 1: Inspect `sfp_template.py` to confirm the boilerplate**

Run: `head -60 modules/sfp_template.py`
Expected: confirms the meta block format and class skeleton. Use the same shape.

- [ ] **Step 2: Write the module**

Create `modules/sfp_holehe.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_holehe
# Purpose:      Probe ~120 services for account existence using the holehe
#               library. For each EMAILADDR event, emit one
#               ACCOUNT_EXTERNAL_OWNED per confirmed registration.
# Introduced:   2026-04-26
# Licence:      MIT
# -------------------------------------------------------------------------------

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
            "description": "Open-source library that uses password-reset "
                           "and signup differential responses to detect "
                           "whether an email is registered at a service. "
                           "No API keys required.",
        },
    }

    opts = {
        "max_emails": 25,
        "timeout_s": 60,
        "skip_providers": "",
    }

    optdescs = {
        "max_emails": "Max emails to probe per scan (default 25). Holehe "
                      "is slow and invasive; keep this small.",
        "timeout_s": "Per-email wall-clock timeout in seconds (default 60).",
        "skip_providers": "Comma-separated provider names to skip, in "
                          "addition to the built-in skip list.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._processed = 0
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["EMAILADDR"]

    def producedEvents(self):
        return ["ACCOUNT_EXTERNAL_OWNED"]

    def handleEvent(self, event):
        if self.errorState:
            return

        max_emails = int(self.opts["max_emails"])
        if self._processed >= max_emails:
            self.debug(f"hit max_emails={max_emails}; skipping {event.data}")
            return

        skip = {
            s.strip() for s in self.opts["skip_providers"].split(",")
            if s.strip()
        }

        try:
            hits = probe_email(
                event.data,
                skip=skip,
                timeout_s=int(self.opts["timeout_s"]),
            )
        except Exception as exc:
            self.error(f"holehe runner failed: {exc}")
            self.errorState = True
            return

        self._processed += 1

        for hit in hits:
            data = (
                f"Holehe: {hit.provider} (Domain: {hit.domain})\n"
                f"<SFURL>https://{hit.domain}</SFURL>"
            )
            evt = SpiderFootEvent(
                "ACCOUNT_EXTERNAL_OWNED", data, self.__name__, event,
            )
            self.notifyListeners(evt)


# End of sfp_holehe class
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python3 -m pytest test/unit/modules/test_sfp_holehe.py -v`
Expected: 6 passed.

- [ ] **Step 4: Lint**

Run: `python3 -m flake8 modules/sfp_holehe.py`
Expected: no output (clean).

- [ ] **Step 5: Commit**

```bash
git add modules/sfp_holehe.py
git commit -m "sfp_holehe: account-existence module via holehe"
```

---

## Task 6: Smoke-check the module loads through SpiderFoot

The module loader (`SpiderFootHelpers.loadModulesAsDict`) is what actually validates the meta block in production. A test that runs the loader against the new module catches malformed `meta` blocks (wrong category name, missing `dataSource` key, etc.) that unit tests miss.

**Files:**
- Touch: nothing — just run a smoke command.

- [ ] **Step 1: Load the module via the SpiderFoot loader**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
m = mods['sfp_holehe']
print('loaded:', m['name'])
print('flags:', m['flags'])
print('cats:', m['cats'])
print('produces:', m['provides'])
print('consumes:', m['consumes'])
"
```

Expected output (exact wording):

```
loaded: Holehe Account Discovery
flags: ['invasive']
cats: ['Social Media']
produces: ['ACCOUNT_EXTERNAL_OWNED']
consumes: ['EMAILADDR']
```

- [ ] **Step 2: Confirm `-M` lists it on the CLI**

Run: `python3 ./sf.py -M 2>&1 | grep holehe`
Expected: `sfp_holehe                | Holehe Account Discovery` (column widths may differ slightly).

- [ ] **Step 3: No commit** — this is a verification-only step.

---

## Task 7: Run the full unit suite + lint

**Files:** none — verification only.

- [ ] **Step 1: Run flake8 across the changes**

Run: `python3 -m flake8 spiderfoot/holehe_runner.py modules/sfp_holehe.py test/unit/spiderfoot/test_holehe_runner.py test/unit/modules/test_sfp_holehe.py`
Expected: no output.

- [ ] **Step 2: Run all new tests + a sibling module test to confirm we didn't break shared fixtures**

Run: `python3 -m pytest test/unit/spiderfoot/test_holehe_runner.py test/unit/modules/test_sfp_holehe.py test/unit/modules/test_sfp_searxng.py -v`
Expected: 12 holehe tests pass + the searxng tests still pass.

- [ ] **Step 3: No commit** — verification only.

---

## Task 8: Docs — CLAUDE.md + BACKLOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Update CLAUDE.md FREE_NOAUTH_UNLIMITED list**

Find the `### FREE_NOAUTH_UNLIMITED (96)` heading in `CLAUDE.md` and bump the count to `97`. Insert `- sfp_holehe` in alphabetical order (between `sfp_h1nobbdde` and `sfp_hackertarget`).

- [ ] **Step 2: Update CLAUDE.md surviving-module count**

Find the sentence in CLAUDE.md that reads "The **186** surviving non-storage modules are listed below" and change `186` to `187`.

- [ ] **Step 3: Mark Holehe shipped in BACKLOG.md**

Edit the `### Holehe account-existence module (`sfp_holehe`)` section in `docs/superpowers/BACKLOG.md`: prepend `**Status:** Shipped 2026-04-26 (commits XXXXXXXX … YYYYYYYY).` as the first line, and replace the bottom-of-file `| Low | sfp_holehe |` row with `| ~~Low~~ Done | ~~sfp_holehe~~ — shipped 2026-04-26 |` (mirror the format used for the Postgres-migration row already present).

- [ ] **Step 4: Verify docs render cleanly**

Run: `grep -c "sfp_holehe" CLAUDE.md`
Expected: `1` (the new entry only).

Run: `grep -A 1 "sfp_holehe" docs/superpowers/BACKLOG.md | head -5`
Expected: shows the shipped status line.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "docs: CLAUDE.md + BACKLOG.md — sfp_holehe shipped"
```

---

## Task 9: Final verify

**Files:** none — verification only.

- [ ] **Step 1: Show the commit chain**

Run: `git log --oneline master..HEAD` — or `git log --oneline -8` if working straight on master.
Expected: ~6 new commits (deps, runner tests, runner impl, module tests, module impl, docs).

- [ ] **Step 2: Run the project's standard test suite**

Run: `./test/run` (this runs flake8 + the unit/integration suite — same as CI).
Expected: all green. If it surfaces flakes unrelated to the holehe work, note them but do not fix in this branch.

- [ ] **Step 3: Done.** Hand back to the user with the commit list and any notes from `./test/run`.

---

## Self-review

**Spec coverage:** Walked the spec section-by-section.

- "Architecture / two units" → Tasks 2-5 build runner first, module second; runner has zero SpiderFoot imports (verified by Task 6's loader smoke).
- "Module options" (`max_emails`, `timeout_s`, `skip_providers`) → all in Task 5's `opts`/`optdescs` blocks; tested in Task 4.
- "Event flow" — `max_emails` cap + `skip_providers` parsing + event-format string — Task 4 covers all three.
- "Error contract" — runner exception → errorState (Task 4 test #5); per-provider exceptions isolated (Task 2 test #2); timeout returns partial (Task 2 test #4); `rateLimit`/`exists is False` filtered (Task 2 test #1). Holehe import-failure path is *not* a dedicated test — handled by Task 5's blanket `except Exception` around `probe_email` (which itself imports lazily). Acceptable: the existing `test_runner_exception_trips_errorstate` covers the propagation; explicit ImportError test would be redundant.
- "Distribution" — Task 1 adds `requirements.txt` line; Dockerfile change confirmed unnecessary (already runs `pip install -r requirements.txt`).
- "Testing" sections — six runner tests in Task 2 match spec list; six module tests in Task 4 match (watched/produced collapsed into one class with two methods, total still six methods).
- "CLAUDE.md update" — Task 8 covers list insertion + count bump.

**Placeholder scan:** No "TBD"/"TODO"/"add error handling"/etc. Every step has either concrete code, a concrete shell command, or a concrete file edit instruction.

**Type consistency:**
- `HoleheHit(provider, domain)` defined in Task 3, used identically in Tasks 4 and 5.
- `probe_email(email, *, skip, timeout_s)` signature defined in Task 3, called identically in Task 5; tested with `kwargs["skip"]` in Task 4.
- `_DEFAULT_SKIP: frozenset` referenced in spec → defined in Task 3 → tested-around (test injects its own `skip` set, doesn't rely on the constant being non-empty).
- `_get_provider_funcs` is the patched seam used by tests (Task 2) and defined in the runner (Task 3) — names match.
