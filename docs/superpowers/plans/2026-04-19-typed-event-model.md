# Typed Event Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SpiderFootEvent`'s stringly-typed interface and `db.py`'s 172-entry `eventDetails` list with a typed single-source-of-truth registry in a new `spiderfoot/event_types.py`, soft-validated at event-creation time. Zero module call-site churn.

**Architecture:** New `spiderfoot/event_types.py` owns a `str`-mixin `EventType` enum, a `frozen=True` `EventTypeDef` dataclass, and the `EVENT_TYPES` registry dict. `spiderfoot/event.py` becomes a `@dataclass(slots=True)` that dual-accepts `str | EventType`, normalises internally, and logs warnings on unknown types or validator failures. `spiderfoot/db.py` drops its `eventDetails` list and iterates `EVENT_TYPES` for DB population.

**Tech Stack:** Python 3.12+ stdlib only (`dataclasses`, `enum`, `logging`, `typing`). Tests use `unittest.TestCase` (matches existing style). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-19-typed-event-model-design.md`.

---

## File Structure

- **Create** `spiderfoot/event_types.py` — ~200 lines. Pure data: enum + dataclass + registry dict.
- **Create** `test/unit/spiderfoot/test_event_types.py` — ~80 lines. Registry invariants + regression fences.
- **Modify** `spiderfoot/event.py` — ~303 lines today → ~140 lines after refactor. `@dataclass(slots=True)` with `__post_init__` validation.
- **Modify** `test/unit/spiderfoot/test_spiderfootevent.py` — **append** new behaviour tests at the end. Do not touch existing tests.
- **Modify** `spiderfoot/db.py` — delete the `eventDetails` list-of-lists at lines 111-284; rewrite the two insertion sites (~lines 378-392 and ~lines 410-419) to iterate `EVENT_TYPES`.

---

## Context for the implementer

Key facts to internalize before starting:

- **The registry has exactly 172 entries.** Category distribution: 79 DESCRIPTOR, 57 ENTITY, 30 DATA, 5 SUBENTITY, 1 INTERNAL. `is_raw` distribution: 155 False, 17 True. These are regression fences — if your final numbers don't match, something dropped or was duplicated.
- **`EventTypeCategory` has five members:** `DATA`, `DESCRIPTOR`, `ENTITY`, `INTERNAL`, `SUBENTITY`. There is **no** `ROOT` category — the `ROOT` event has category `INTERNAL`.
- **`SpiderFootEvent.eventType` today is a `str`.** After the refactor it's an `EventType` enum *that is also a `str`* (due to `str` mixin). `event.eventType == "DNS_NAME"` stays `True`; `isinstance(event.eventType, str)` stays `True`.
- **Validation is soft.** Unknown `eventType` strings and failed `validator(data)` calls emit a `warning` via `logging.getLogger("spiderfoot.event")` and the event is still published. They never raise. The existing `TypeError`/`ValueError` behaviour on non-string inputs is preserved — those still raise.
- **Existing tests in `test_spiderfootevent.py` must pass unchanged.** One test constructs an event with `event_type='example non-root event type'` — this is not in the registry, so it will emit a warning. That's fine; the test only asserts `isinstance(evt, SpiderFootEvent)`.
- **Dataclass vs property/setter trade-off.** Today's setters for `confidence`/`visibility`/`risk` validate ranges on every assignment. `grep` shows zero modules mutate those attributes post-construction; only `moduleDataSource` and `actualSource` are mutated (62 call sites across 14 modules, and their setters do no validation). **However**, `test/unit/spiderfoot/test_spiderfootevent.py` has ~6 tests (around lines 124-200) that exercise `evt.confidence = "bad"` / `evt.confidence = 101` and expect `TypeError` / `ValueError`. These tests are part of the "baseline must pass unchanged" contract — so the dataclass needs a `__setattr__` hook that re-runs range/type validation for those three fields on every assignment. The hook is small (~10 lines) and preserves both the test contract and the class's invariants.
- **Run full suite:** `./test/run` (flake8 + pytest; should pass 1599 + 35 skipped after the prior structured-logging change).
- **Run single test file:** `python3 -m pytest test/unit/spiderfoot/test_event_types.py -v`.
- **Flake8 config in `setup.cfg`.** `spiderfoot/logger.py` has `per-file-ignores = F401,A003`; `spiderfoot/event.py` has `per-file-ignores = A003`. If you need to ignore a rule in a new file, add it to `per-file-ignores`.

---

## Task 1: Create `spiderfoot/event_types.py` and its invariant tests

**Files:**
- Create: `spiderfoot/event_types.py`
- Create: `test/unit/spiderfoot/test_event_types.py`

- [ ] **Step 1: Generate the registry file with a one-shot script**

Run this from the repo root. It reads today's `eventDetails` out of `spiderfoot/db.py` and writes a typed `spiderfoot/event_types.py`:

```bash
python3 <<'PYEOF'
import re
from pathlib import Path

src = Path("spiderfoot/db.py").read_text()
start = src.index("eventDetails = [")
depth = 0
i = start
while i < len(src):
    if src[i] == "[":
        depth += 1
    elif src[i] == "]":
        depth -= 1
        if depth == 0:
            break
    i += 1
block = src[start:i + 1]

# Each row is: ['NAME', 'description', raw_int, 'CATEGORY']
row_re = re.compile(
    r"""\[
        \s* '(?P<name>[A-Z_]+)' \s* ,
        \s* '(?P<desc>(?:[^'\\]|''|\\.)*)' \s* ,
        \s* (?P<raw>\d+) \s* ,
        \s* '(?P<cat>[A-Z_]+)' \s*
    \]""",
    re.VERBOSE,
)
rows = [m.groupdict() for m in row_re.finditer(block)]
assert len(rows) == 172, f"Expected 172 rows, got {len(rows)}"

# Enum member lines
members = "\n".join(f"    {r['name']} = \"{r['name']}\"" for r in rows)
# Registry dict lines
reg_lines = []
for r in rows:
    desc = r["desc"].replace("''", "'")  # SQL double-quote → single
    esc_desc = desc.replace("\\", "\\\\").replace('"', '\\"')
    is_raw = "True" if r["raw"] == "1" else "False"
    reg_lines.append(
        f"    EventType.{r['name']}: EventTypeDef("
        f"\"{r['name']}\", "
        f"\"{esc_desc}\", "
        f"EventTypeCategory.{r['cat']}, "
        f"is_raw={is_raw}"
        f"),"
    )
registry = "\n".join(reg_lines)

out = f'''"""Typed registry of SpiderFoot event types.

This module is the single source of truth for what event types exist,
their human descriptions, their category, and whether they are raw
data. The SQLite ``tbl_event_types`` table is populated from
``EVENT_TYPES`` at database initialization in ``spiderfoot/db.py``.

Adding a new event type: add an ``EventType`` enum member *and* a
matching ``EVENT_TYPES`` entry. The invariant tests in
``test/unit/spiderfoot/test_event_types.py`` will fail if the two
drift apart.
"""
import enum
from collections.abc import Callable
from dataclasses import dataclass


class EventTypeCategory(enum.Enum):
    DATA = "DATA"
    DESCRIPTOR = "DESCRIPTOR"
    ENTITY = "ENTITY"
    INTERNAL = "INTERNAL"
    SUBENTITY = "SUBENTITY"


@dataclass(frozen=True, slots=True)
class EventTypeDef:
    name: str
    description: str
    category: EventTypeCategory
    is_raw: bool
    validator: Callable[[str], bool] | None = None


class EventType(str, enum.Enum):
{members}


EVENT_TYPES: dict[EventType, EventTypeDef] = {{
{registry}
}}
'''

Path("spiderfoot/event_types.py").write_text(out)
print(f"Wrote spiderfoot/event_types.py with {len(rows)} entries")
PYEOF
```

Expected output: `Wrote spiderfoot/event_types.py with 172 entries`.

If the count is anything other than 172, stop — the parser regex failed. Re-read `spiderfoot/db.py:111-284` manually to see what the new shape is.

- [ ] **Step 2: Verify the module imports cleanly**

Run: `python3 -c "from spiderfoot.event_types import EventType, EventTypeDef, EventTypeCategory, EVENT_TYPES; print(len(EVENT_TYPES))"`

Expected output: `172`.

If this fails with a `SyntaxError`, the generated file has a quote-escaping bug — the likely culprit is an event description containing an unescaped quote. Look at the offending line and fix by hand.

- [ ] **Step 3: Write the invariant tests**

Create `test/unit/spiderfoot/test_event_types.py` with the following content:

```python
# test_event_types.py
import unittest

from spiderfoot.event_types import (
    EVENT_TYPES,
    EventType,
    EventTypeCategory,
    EventTypeDef,
)


class TestEventTypes(unittest.TestCase):

    def test_registry_has_expected_count(self):
        self.assertEqual(len(EVENT_TYPES), 172)

    def test_every_enum_member_has_registry_entry(self):
        missing = [e for e in EventType if e not in EVENT_TYPES]
        self.assertEqual(missing, [])

    def test_every_registry_entry_has_matching_enum_member(self):
        orphan_keys = [k for k in EVENT_TYPES if not isinstance(k, EventType)]
        self.assertEqual(orphan_keys, [])

    def test_defs_name_matches_enum_value(self):
        for enum_member, definition in EVENT_TYPES.items():
            self.assertEqual(enum_member.value, definition.name)

    def test_defs_are_frozen_instances(self):
        for definition in EVENT_TYPES.values():
            self.assertIsInstance(definition, EventTypeDef)
            with self.assertRaises(Exception):
                definition.name = "mutated"

    def test_category_distribution_matches_pre_refactor(self):
        counts = {cat: 0 for cat in EventTypeCategory}
        for d in EVENT_TYPES.values():
            counts[d.category] += 1
        self.assertEqual(counts[EventTypeCategory.DESCRIPTOR], 79)
        self.assertEqual(counts[EventTypeCategory.ENTITY], 57)
        self.assertEqual(counts[EventTypeCategory.DATA], 30)
        self.assertEqual(counts[EventTypeCategory.SUBENTITY], 5)
        self.assertEqual(counts[EventTypeCategory.INTERNAL], 1)

    def test_is_raw_distribution_matches_pre_refactor(self):
        raw_true = sum(1 for d in EVENT_TYPES.values() if d.is_raw)
        raw_false = sum(1 for d in EVENT_TYPES.values() if not d.is_raw)
        self.assertEqual(raw_true, 17)
        self.assertEqual(raw_false, 155)

    def test_root_event_is_internal_category(self):
        self.assertEqual(
            EVENT_TYPES[EventType.ROOT].category,
            EventTypeCategory.INTERNAL,
        )

    def test_event_type_is_string_compatible(self):
        # str-mixin contract: `EventType.DNS_NAME == "DNS_NAME"` and
        # `str(EventType.DNS_NAME) == "DNS_NAME"` must both hold.
        # This is the hinge on which all 892 module call sites keep
        # working unchanged.
        self.assertEqual(EventType.DNS_NAME, "DNS_NAME")
        self.assertEqual(str(EventType.DNS_NAME), "DNS_NAME")
        self.assertTrue(isinstance(EventType.DNS_NAME, str))

    def test_category_members_are_exactly_five(self):
        self.assertEqual(
            set(EventTypeCategory),
            {
                EventTypeCategory.DATA,
                EventTypeCategory.DESCRIPTOR,
                EventTypeCategory.ENTITY,
                EventTypeCategory.INTERNAL,
                EventTypeCategory.SUBENTITY,
            },
        )
```

- [ ] **Step 4: Run the invariant tests and confirm all pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_event_types.py -v`

Expected: all 10 tests pass. If any fail, the generator script in Step 1 produced the wrong output — re-check the counts.

- [ ] **Step 5: Flake8 the new files**

Run: `python3 -m flake8 spiderfoot/event_types.py test/unit/spiderfoot/test_event_types.py`

Expected: no output (clean). If `E501` (line too long) triggers on any registry line, that's fine to leave — the file is pre-configured as tabular data; if flake8 complains, add `spiderfoot/event_types.py:E501` to `setup.cfg`'s `per-file-ignores`.

- [ ] **Step 6: Commit**

```bash
git add spiderfoot/event_types.py test/unit/spiderfoot/test_event_types.py
git commit -m "$(cat <<'EOF'
event_types: add typed registry of SpiderFoot event types

Introduces spiderfoot/event_types.py as the single source of truth
for SpiderFoot's 172 event types. EventType is a str-mixin enum so
existing string comparisons in modules keep working unchanged.
EventTypeDef is a frozen slots dataclass with name, description,
category, is_raw, and an optional Callable[[str], bool] validator
hook (None for all types on day 1).

Invariant tests freeze the distribution: 79 DESCRIPTOR, 57 ENTITY,
30 DATA, 5 SUBENTITY, 1 INTERNAL; 155 non-raw + 17 raw. Drift
between the enum and the registry dict fails the suite.

Refs docs/superpowers/specs/2026-04-19-typed-event-model-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Write failing tests for the new `SpiderFootEvent` behaviour (TDD)

**Files:**
- Modify: `test/unit/spiderfoot/test_spiderfootevent.py` — append a new `TestSpiderFootEventTypedRegistry` class at the bottom. Do not touch existing tests.

- [ ] **Step 1: Append the new test class**

Append this to `test/unit/spiderfoot/test_spiderfootevent.py` (do not remove anything that's already there):

```python


import logging

from spiderfoot.event_types import EventType


class TestSpiderFootEventTypedRegistry(unittest.TestCase):

    def _root_source(self):
        return SpiderFootEvent("ROOT", "seed", "", "")

    def test_accepts_enum_event_type(self):
        root = self._root_source()
        evt = SpiderFootEvent(EventType.DNS_NAME, "example.com",
                              "test_mod", root)
        self.assertEqual(evt.eventType, "DNS_NAME")
        self.assertEqual(evt.eventType, EventType.DNS_NAME)
        self.assertIsInstance(evt.eventType, str)

    def test_accepts_str_event_type(self):
        root = self._root_source()
        evt = SpiderFootEvent("DNS_NAME", "example.com", "test_mod", root)
        self.assertEqual(evt.eventType, "DNS_NAME")
        self.assertEqual(evt.eventType, EventType.DNS_NAME)

    def test_str_and_enum_constructor_produce_equal_events(self):
        root = self._root_source()
        evt_str = SpiderFootEvent("DNS_NAME", "example.com", "m", root)
        evt_enum = SpiderFootEvent(EventType.DNS_NAME, "example.com", "m",
                                   root)
        self.assertEqual(evt_str.eventType, evt_enum.eventType)
        self.assertEqual(evt_str.data, evt_enum.data)
        self.assertEqual(evt_str.module, evt_enum.module)

    def test_unknown_event_type_warns_but_creates_event(self):
        root = self._root_source()
        with self.assertLogs("spiderfoot.event", level="WARNING") as cm:
            evt = SpiderFootEvent("NOT_A_REAL_TYPE", "x", "m", root)
        self.assertIsInstance(evt, SpiderFootEvent)
        self.assertEqual(evt.eventType, "NOT_A_REAL_TYPE")
        joined = "\n".join(cm.output).lower()
        self.assertIn("unknown eventtype", joined)

    def test_validator_failure_warns_but_creates_event(self):
        root = self._root_source()
        # Temporarily install a always-false validator on IP_ADDRESS.
        from spiderfoot.event_types import EVENT_TYPES, EventTypeDef
        original = EVENT_TYPES[EventType.IP_ADDRESS]
        EVENT_TYPES[EventType.IP_ADDRESS] = EventTypeDef(
            name=original.name,
            description=original.description,
            category=original.category,
            is_raw=original.is_raw,
            validator=lambda data: False,
        )
        try:
            with self.assertLogs("spiderfoot.event", level="WARNING") as cm:
                evt = SpiderFootEvent("IP_ADDRESS", "1.2.3.4", "m", root)
        finally:
            EVENT_TYPES[EventType.IP_ADDRESS] = original
        self.assertIsInstance(evt, SpiderFootEvent)
        self.assertEqual(evt.data, "1.2.3.4")
        joined = "\n".join(cm.output).lower()
        self.assertIn("validation failed", joined)

    def test_no_validator_means_no_warning(self):
        root = self._root_source()
        # DNS_NAME has validator=None on day 1. assertNoLogs was added
        # in Python 3.10.
        logger = logging.getLogger("spiderfoot.event")
        with self.assertNoLogs("spiderfoot.event", level="WARNING"):
            SpiderFootEvent("DNS_NAME", "example.com", "m", root)
        # Silence "unused" flake8 complaint about the logger handle.
        _ = logger
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `python3 -m pytest test/unit/spiderfoot/test_spiderfootevent.py::TestSpiderFootEventTypedRegistry -v`

Expected: at least `test_unknown_event_type_warns_but_creates_event` and `test_validator_failure_warns_but_creates_event` fail with `AssertionError: no logs of level WARNING or higher triggered on spiderfoot.event`, because the current `SpiderFootEvent` never logs. `test_accepts_enum_event_type` may also fail if the current code rejects the enum — depends on whether the `str` isinstance check passes today (it will, because the enum is a `str`).

Do not proceed to Task 3 until you see expected failures from these two tests specifically.

- [ ] **Step 3: Commit the failing tests**

```bash
git add test/unit/spiderfoot/test_spiderfootevent.py
git commit -m "$(cat <<'EOF'
test: add failing tests for SpiderFootEvent typed-registry behaviour

Drives Task 3: the refactor of SpiderFootEvent to a dataclass that
dual-accepts str or EventType, normalises to EventType, and logs
warnings on unknown types or failed validators without ever raising
or dropping the event.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Refactor `SpiderFootEvent` to a `@dataclass(slots=True)` with soft validation

**Files:**
- Modify: `spiderfoot/event.py` — full rewrite (~303 lines → ~140 lines)

- [ ] **Step 1: Replace the entire contents of `spiderfoot/event.py`**

Overwrite `spiderfoot/event.py` with this content:

```python
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Union

from spiderfoot.event_types import EVENT_TYPES, EventType

_log = logging.getLogger("spiderfoot.event")

_EventTypeArg = Union[str, EventType]

# Fields whose value must remain a 0-100 int across the object's life.
# The dataclass-generated __init__ only runs validation once; test
# suite also exercises evt.confidence = bad_value etc. post-construction,
# so __setattr__ below re-runs validation on every assignment to these.
_VALIDATED_RANGE_FIELDS = frozenset({"confidence", "visibility", "risk"})


@dataclass(slots=True)
class SpiderFootEvent:
    """SpiderFootEvent object representing identified data and associated metadata.

    Attributes:
        eventType: Event type, e.g. URL_FORM, RAW_DATA. Accepted as
            either ``str`` or ``EventType`` at construction; stored
            internally as whichever type the caller passed (``str``
            for unregistered types, ``EventType`` for registered ones).
            ``EventType`` is a ``str`` mixin, so string comparisons
            keep working either way.
        data: Event data, e.g. a URL, port number, webpage content.
        module: Module which produced this event.
        sourceEvent: The event that triggered this one (``None`` only
            for ``ROOT`` events).
        generated: Creation time in Unix seconds.
        confidence: 0-100, default 100.
        visibility: 0-100, default 100.
        risk: 0-100, default 0.
        sourceEventHash: SHA256 hash of ``sourceEvent`` (``"ROOT"`` for
            root events).
        moduleDataSource: Free-form tag describing the upstream data
            source. Mutable post-construction by modules.
        actualSource: Free-form pointer to the parent event's value.
            Mutable post-construction by modules.
        hash: SHA256 identity hash, or ``"ROOT"`` for root events.
    """

    eventType: _EventTypeArg
    data: str
    module: str
    sourceEvent: Optional["SpiderFootEvent"]
    generated: float = field(default_factory=time.time)
    confidence: int = 100
    visibility: int = 100
    risk: int = 0
    sourceEventHash: str = field(init=False, default="")
    moduleDataSource: Optional[str] = None
    actualSource: Optional[str] = None
    _id: str = field(init=False, repr=False, default="")

    def __post_init__(self) -> None:
        # --- eventType normalization + soft validation ---
        if not isinstance(self.eventType, str):
            raise TypeError(
                f"eventType is {type(self.eventType)}; expected str()"
            )
        if not self.eventType:
            raise ValueError("eventType is empty")

        normalized: _EventTypeArg
        try:
            normalized = EventType(str(self.eventType))
        except ValueError:
            _log.warning(
                "unknown eventType=%r emitted by module=%r",
                str(self.eventType), self.module,
            )
            normalized = str(self.eventType)
        self.eventType = normalized

        # --- data validation (existing behaviour, unchanged) ---
        if not isinstance(self.data, str):
            raise TypeError(f"data is {type(self.data)}; expected str()")
        if not self.data:
            raise ValueError(f"data is empty: '{self.data!s}'")

        # --- module validation (existing behaviour, unchanged) ---
        if not isinstance(self.module, str):
            raise TypeError(f"module is {type(self.module)}; expected str()")
        if not self.module and self.eventType != "ROOT":
            raise ValueError("module is empty")

        # Note: confidence/visibility/risk range checks run via
        # __setattr__ below (which fires during the dataclass-generated
        # __init__), so they're already validated by the time we reach
        # this point.

        # --- sourceEvent wiring + hash ---
        if self.eventType == "ROOT":
            self.sourceEvent = None
            self.sourceEventHash = "ROOT"
        else:
            if not isinstance(self.sourceEvent, SpiderFootEvent):
                raise TypeError(
                    f"sourceEvent is {type(self.sourceEvent)}; "
                    "expected SpiderFootEvent()"
                )
            self.sourceEventHash = self.sourceEvent.hash

        # --- identity ---
        self._id = (
            f"{self.eventType}{self.generated}{self.module}"
            f"{random.SystemRandom().randint(0, 99999999)}"
        )

        # --- soft data validation via registry hook ---
        if isinstance(self.eventType, EventType):
            entry = EVENT_TYPES.get(self.eventType)
            if entry is not None and entry.validator is not None:
                try:
                    ok = entry.validator(self.data)
                except Exception as exc:
                    _log.warning(
                        "validation failed for eventType=%s (validator "
                        "raised %s); event published anyway",
                        self.eventType, exc,
                    )
                else:
                    if not ok:
                        _log.warning(
                            "validation failed for eventType=%s data=%r; "
                            "event published anyway",
                            self.eventType, self.data,
                        )

    def __setattr__(self, name: str, value) -> None:
        if name in _VALIDATED_RANGE_FIELDS:
            if not isinstance(value, int):
                raise TypeError(f"{name} is {type(value)}; expected int()")
            if not 0 <= value <= 100:
                raise ValueError(f"{name} value is {value}; expected 0 - 100")
        super().__setattr__(name, value)

    @property
    def hash(self) -> str:
        """Unique SHA256 hash of the event, or ``"ROOT"``.

        Returns:
            str: SHA256 hex digest, or ``"ROOT"`` for root events.
        """
        if self.eventType == "ROOT":
            return "ROOT"
        digest_str = self._id.encode("raw_unicode_escape")
        return hashlib.sha256(digest_str).hexdigest()

    def asDict(self) -> dict:
        """Event object as dictionary.

        Returns:
            dict: event as dictionary
        """
        evt = {
            "generated": int(self.generated),
            "type": str(self.eventType),
            "data": self.data,
            "module": self.module,
            "source": "",
        }
        if self.sourceEvent is not None and self.sourceEvent.data is not None:
            evt["source"] = self.sourceEvent.data
        return evt
```

Key design decisions baked into this code (explained so you can defend edits during review):
- `eventType` field is typed as `Union[str, EventType]`. Enum is preferred; bare `str` is kept only for *unregistered* types (warned, still published).
- Most validation runs once in `__post_init__` (type checks on `eventType`/`data`/`module`/`sourceEvent`). The `confidence`/`visibility`/`risk` range checks run via `__setattr__` so they fire on both construction *and* post-construction mutation — preserving the existing test contract.
- `moduleDataSource` and `actualSource` have no validation (matches today). They stay freely mutable; modules mutate them often.
- The existing `@property hash` stays as a computed property (not a dataclass field) because it depends on runtime state (`_id`).
- `asDict()["type"]` uses `str(self.eventType)` so the dict serialization matches today byte-for-byte regardless of whether `eventType` is stored as `EventType` or `str`.

- [ ] **Step 2: Run the full `event.py` test suite**

Run: `python3 -m pytest test/unit/spiderfoot/test_spiderfootevent.py -v`

Expected: every test passes — both the pre-existing ones and the new `TestSpiderFootEventTypedRegistry` class added in Task 2.

If any pre-existing test fails, the refactor broke public API somewhere. Most likely suspects:
- A setter that used to coerce is now not being called (check `evt.confidence = 50` paths — the test suite has some).
- `asDict()` returns a subtly different shape.
- The new dataclass's `__repr__` differs from the old class's — but no existing test asserts on `repr`.

- [ ] **Step 3: Run the full suite to catch downstream regressions**

Run: `./test/run`

Expected: 1615 passed (1599 baseline + 10 invariant tests from `test_event_types.py` + 6 behaviour tests from `TestSpiderFootEventTypedRegistry`), 35 skipped. Any pre-existing test now failing is a regression — stop and investigate.

If any previously-passing test is now failing, stop. The most likely cause is `sfscan.py`, a module, or the web UI reading an attribute that the dataclass renders differently (e.g. iterating `__dict__` — dataclass with `slots=True` has no `__dict__`; use `dataclasses.asdict()` or `vars()` on a non-slots dataclass). Investigate before proceeding.

- [ ] **Step 4: Flake8**

Run: `python3 -m flake8 spiderfoot/event.py test/unit/spiderfoot/test_spiderfootevent.py`

Expected: no output.

If `DAR` (darglint) warns about missing `Returns:` docstring sections, follow the existing convention in the file — the old docstrings on `__init__` had `Args:` and `Raises:`, matching `docstring_style=google`. If you need to ignore a rule that's project-wide intentional, update `setup.cfg`'s `per-file-ignores`; otherwise fix the docstring.

- [ ] **Step 5: Commit**

```bash
git add spiderfoot/event.py
git commit -m "$(cat <<'EOF'
event: refactor SpiderFootEvent to dataclass with soft validation

Replaces the property-ceremony class with @dataclass(slots=True).
Public API is byte-compatible: eventType, data, module, sourceEvent,
confidence, visibility, risk, generated, sourceEventHash, hash,
asDict, moduleDataSource, actualSource all unchanged to callers.

Construction dual-accepts str | EventType and normalises to
EventType for registered types (logging a warning via
"spiderfoot.event" for unregistered strings). Registered types with
a validator run it; failure logs a warning but still publishes the
event. The existing TypeError / ValueError raises on bad inputs
are preserved.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Drop the duplicated `eventDetails` list from `db.py`

**Files:**
- Modify: `spiderfoot/db.py` — delete `eventDetails = [...]` and rewrite the two insertion sites.

- [ ] **Step 1: Delete the `eventDetails` list-of-lists**

Open `spiderfoot/db.py`. Find the `eventDetails = [` line (near line 111) and delete the entire list including the closing `]` (ends around line 284). In its place, leave **nothing** — there should be no module-level or class-level reference to `eventDetails` after this step. The class body continues with `def __init__` below.

- [ ] **Step 2: Rewrite the first insertion site (`__init__`, near line 377-392)**

Find this block inside `__init__`:

```python
            if init:
                for row in self.eventDetails:
                    event = row[0]
                    event_descr = row[1]
                    event_raw = row[2]
                    event_type = row[3]
                    qry = "INSERT INTO tbl_event_types (event, event_descr, event_raw, event_type) VALUES (?, ?, ?, ?)"

                    try:
                        self.dbh.execute(qry, (
                            event, event_descr, event_raw, event_type
                        ))
                        self.conn.commit()
                    except Exception:
                        continue
                self.conn.commit()
```

Replace with:

```python
            if init:
                self._populateEventTypes()
```

- [ ] **Step 3: Rewrite the second insertion site (`create()`, near line 410-419)**

Find this block inside `create()`:

```python
                for row in self.eventDetails:
                    event = row[0]
                    event_descr = row[1]
                    event_raw = row[2]
                    event_type = row[3]
                    qry = "INSERT INTO tbl_event_types (event, event_descr, event_raw, event_type) VALUES (?, ?, ?, ?)"

                    self.dbh.execute(qry, (
                        event, event_descr, event_raw, event_type
                    ))
                self.conn.commit()
```

Replace with:

```python
                self._populateEventTypes()
                self.conn.commit()
```

- [ ] **Step 4: Add the `_populateEventTypes` helper and the import**

At the top of `spiderfoot/db.py`, find the import block (should include `sqlite3`, `threading`, etc.). Add this import alongside the existing `spiderfoot` imports (the module imports `SpiderFootHelpers` etc. already — add this next to it, or as a new line):

```python
from spiderfoot.event_types import EVENT_TYPES
```

Then add the following helper method inside the `SpiderFootDb` class (anywhere after `__init__` and before `create`, position doesn't matter — place it next to `create` for readability):

```python
    def _populateEventTypes(self) -> None:
        """Populate ``tbl_event_types`` from the typed registry.

        The caller holds ``self.dbhLock`` and drives commit/rollback.
        Individual insert failures are swallowed so that re-init on
        a DB that already has rows doesn't crash (UNIQUE violations
        on the PK are expected).
        """
        qry = (
            "INSERT INTO tbl_event_types "
            "(event, event_descr, event_raw, event_type) "
            "VALUES (?, ?, ?, ?)"
        )
        for enum_member, definition in EVENT_TYPES.items():
            try:
                self.dbh.execute(qry, (
                    enum_member.value,
                    definition.description,
                    1 if definition.is_raw else 0,
                    definition.category.value,
                ))
            except Exception:
                continue
        self.conn.commit()
```

Note the `try/except Exception: continue` — this matches the pre-refactor behaviour exactly. The `__init__` path relied on PK-collision exceptions being silently skipped when re-initialising an already-populated DB; preserve that.

- [ ] **Step 5: Run the full suite**

Run: `./test/run`

Expected: 1599 + new-tests passing, 35 skipped. Same total as Task 3 Step 3.

If a `test_spiderfootdb.py` test fails with something like "row count in tbl_event_types is 0" or "ROOT event type not found", the `_populateEventTypes` helper isn't being called in the right place. Re-check Steps 2 and 3 — both call sites must invoke it.

- [ ] **Step 6: Verify the DB-side population is byte-identical**

Run this ad-hoc check against a fresh DB:

```bash
rm -f /tmp/sf-verify.db
python3 -c "
from spiderfoot.db import SpiderFootDb
db = SpiderFootDb({'__database': '/tmp/sf-verify.db'}, init=True)
rows = db.eventTypes()
print(f'Rows in tbl_event_types: {len(rows)}')
# Rows are [descr, name, raw, type]
cats = {}
raws = [0, 0]
for descr, name, raw, cat in rows:
    cats[cat] = cats.get(cat, 0) + 1
    raws[raw] += 1
print('Categories:', cats)
print('is_raw counts:', raws)
"
rm -f /tmp/sf-verify.db
```

Expected output:
```
Rows in tbl_event_types: 172
Categories: {'INTERNAL': 1, 'ENTITY': 57, 'DESCRIPTOR': 79, 'DATA': 30, 'SUBENTITY': 5}
is_raw counts: [155, 17]
```

Any deviation from 172 rows or these category counts means the registry and DB drifted. Investigate before committing.

- [ ] **Step 7: Flake8**

Run: `python3 -m flake8 spiderfoot/db.py`

Expected: no output. The file already has `per-file-ignores = SFS101` in `setup.cfg`; don't touch that.

- [ ] **Step 8: Commit**

```bash
git add spiderfoot/db.py
git commit -m "$(cat <<'EOF'
db: source tbl_event_types from the typed registry

Deletes the 172-entry eventDetails list-of-lists and replaces the
two insertion sites with _populateEventTypes(), which iterates
EVENT_TYPES from spiderfoot.event_types. The SQL schema is
unchanged — only the origin of inserted rows moves. Result: one
canonical Python-side registry, one DB mirror, no drift.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run the CI-equivalent command end-to-end**

Run: `./test/run`

Expected: flake8 clean, 1615 passed (1599 baseline + 10 `test_event_types.py` + 6 `TestSpiderFootEventTypedRegistry`), 35 skipped. No failures.

- [ ] **Step 2: Real-scan smoke test**

Run a short scan against `spiderfoot.net` with a couple of benign modules. Capture JSON logs and grep for warnings:

```bash
rm -f /tmp/sf-smoke.log
SPIDERFOOT_LOG_FORMAT=json timeout 45 python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_whois -q \
    2>/tmp/sf-smoke.log || true
echo "--- unknown eventType / validation failed warnings ---"
grep -iE '"unknown eventtype|validation failed' /tmp/sf-smoke.log || echo "(none)"
echo "--- event count ---"
grep -c '"logger": "spiderfoot' /tmp/sf-smoke.log
rm -f /tmp/sf-smoke.log
```

Expected: `(none)` for warnings and a positive event count (scan produced events). Any warnings mean either:
1. A registry typo — compare against `eventDetails` in the pre-refactor `git show HEAD~4:spiderfoot/db.py`.
2. A module is emitting an unregistered event type — capture the name, check if it was ever in the original `eventDetails`. If it was, fix `event_types.py`. If it wasn't, we've surfaced a pre-existing module bug; flag it for Phase 1 item 3 (dead module audit) and move on.

- [ ] **Step 3: Verify git state**

Run: `git log --oneline master..HEAD` (or just `git log --oneline -5`).

Expected: four fresh commits on this branch beyond the spec commit — Task 1 (registry), Task 2 (failing tests), Task 3 (dataclass refactor), Task 4 (db.py cleanup). Task 5 has no commits; it's verification only.

- [ ] **Step 4: Report completion**

Summary to report: "Typed event model landed. Four commits: typed registry in `spiderfoot/event_types.py`, dataclass-based `SpiderFootEvent` with soft validation, `db.py` now sources `tbl_event_types` from the registry. Zero module call-site changes. `./test/run` clean. Real-scan smoke test produced no validation warnings."
