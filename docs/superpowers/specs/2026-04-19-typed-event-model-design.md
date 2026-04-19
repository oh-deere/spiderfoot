# Typed event model

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-19

## Goal

Replace the ad-hoc, stringly-typed `SpiderFootEvent` / `eventDetails`
pair with a typed, single-source-of-truth registry so future work
(module cull, correlation engine changes, API/worker split) can lean
on compile-time and import-time checks instead of runtime string
matching. This is Phase 1, item 1 of the broader modernization
roadmap for the SpiderFoot fork.

## Non-goals

- **Not** introducing per-event-type subclasses (`DnsNameEvent`,
  `IpAddressEvent`, …). The 892 existing `SpiderFootEvent(...)` call
  sites across 231 modules stay untouched.
- **Not** culling dead modules. Dead-module audit is Phase 1, item 3
  and gets its own spec.
- **Not** introducing a typed module metadata registry (`flags`,
  `useCases`, `categories`). Phase 1, item 2, separate spec.
- **Not** changing `tbl_scan_results.data` storage — `data` stays
  `VARCHAR`. Validators operate on strings.
- **Not** adding structural typing of event payloads (`DNS_NAME.data`
  stays `str`, not a parsed hostname object).
- **Not** breaking the `SpiderFootEvent` public API. Every existing
  module, `sfscan.py`, `sfwebui.py`, and correlation rule must keep
  working with zero edits.

## Design

### New module — `spiderfoot/event_types.py`

One pure-data module. No DB, filesystem, or logging imports. Owns:

```python
class EventTypeCategory(enum.Enum):
    ROOT = "ROOT"
    ENTITY = "ENTITY"
    DESCRIPTOR = "DESCRIPTOR"
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
    ROOT = "ROOT"
    DNS_NAME = "DNS_NAME"
    # ... one member per type, 172 total


EVENT_TYPES: dict[EventType, EventTypeDef] = {
    EventType.ROOT: EventTypeDef("ROOT", "Internal SpiderFoot Root event",
                                 EventTypeCategory.INTERNAL, is_raw=True),
    EventType.DNS_NAME: EventTypeDef("DNS_NAME", "Domain Name",
                                     EventTypeCategory.ENTITY, is_raw=False),
    # ... one entry per member
}
```

**Why `str`-mixin enum for `EventType`**: `EventType.DNS_NAME == "DNS_NAME"`
evaluates to `True`, `str(EventType.DNS_NAME) == "DNS_NAME"`. Existing
code that does `if event.eventType == "DNS_NAME":` keeps working
byte-for-byte after the refactor.

**Why `frozen=True, slots=True` dataclass for `EventTypeDef`**: the
registry is immutable data; `slots=True` saves memory across 172
instances.

### `spiderfoot/event.py` — modernized `SpiderFootEvent`

- Keep the class name and constructor call signature exactly:
  `SpiderFootEvent(eventType, data, module, sourceEvent)`.
- Accept either `str` or `EventType` for the `eventType` arg
  ("dual-accept"); normalize to `EventType` internally.
- Replace the ~300-line property/setter ceremony with a
  `@dataclass(slots=True)`. Runtime validation (type checks, value
  ranges) lives in `__post_init__` instead of setters.
- Preserve every public attribute: `generated`, `eventType`,
  `confidence`, `visibility`, `risk`, `module`, `data`, `sourceEvent`,
  `sourceEventHash`, `actualSource`, `moduleDataSource`, `hash`,
  `asDict()`.
- **Mutation after construction:** `moduleDataSource` and
  `actualSource` are mutated post-construction by 14 modules (62
  total call sites). Today's setters for those two attributes do no
  validation, so plain `@dataclass` assignment is byte-compatible.
  `confidence`/`visibility`/`risk` setters *do* validate ranges
  today, but grep shows zero mutation sites for them — they're only
  set at construction. Conclusion: `__post_init__`-only validation
  matches actual usage. If a module is later found that mutates
  `confidence`/`visibility`/`risk` post-construction with an invalid
  value, a follow-up change can add a validating `__setattr__` hook,
  but we don't pay that cost up front.
- `eventType` returns the enum member (which *is* a string), so any
  existing `str(event.eventType)`, `event.eventType == "DNS_NAME"`,
  or `event.asDict()["type"]` call keeps returning what it did.

### Validation behaviour at event creation

`SpiderFootEvent.__post_init__` does, in order:

1. Normalize `eventType` input. If `str`, resolve via
   `EventType(value)`. On `ValueError` (unknown type), log a
   **warning** via `logging.getLogger("spiderfoot.event")` and coerce
   back to the raw string — event is still published. This preserves
   the current permissive behaviour while making typos visible in
   the JSON log stream.
2. Run the existing type/value checks (unchanged from today).
3. Registry lookup: `EVENT_TYPES.get(normalized_event_type)`. Missing
   entries — only possible if `eventType` was an unregistered string
   — were already logged in step 1.
4. If the registry entry has a `validator` and `validator(data)`
   returns `False`, log a **warning** and publish the event anyway.

**Soft validation is deliberate.** Hard validation would raise and
drop the event — that risks breaking scans on registry bugs and
regressing confidence in the change itself. Warnings land in the
structured JSON log stream shipped in the prior change, so they're
grep-able via Loki (`{app="spiderfoot"} | json | message=~"unknown
eventType|validation failed"`).

Day 1 registry has no validators — every `EventTypeDef.validator`
is `None`. Validators get added incrementally in follow-up commits
for high-value types (e.g. `IP_ADDRESS` → `ipaddress.ip_address`;
`EMAILADDR` → simple regex). That work is explicitly out of scope
for this spec.

### `spiderfoot/db.py` — drop the duplicated registry

The current 172-entry `eventDetails` list-of-lists (lines 111-~300 of
`db.py`) is removed. DB schema init code that inserts into
`tbl_event_types` (two call sites around lines 383 and 415) now
iterates `EVENT_TYPES` from `event_types.py` instead. The SQL schema
for `tbl_event_types` is unchanged; only the source of inserted rows
moves.

Result: one canonical Python-side registry, one DB mirror. No risk
of drift between the two lists.

## Data flow summary

```
module code
  └─ SpiderFootEvent("DNS_NAME", "example.com", name, parent)
       └─ __post_init__
            ├─ normalize "DNS_NAME" → EventType.DNS_NAME
            ├─ type/value checks (existing behaviour)
            ├─ lookup EVENT_TYPES[EventType.DNS_NAME] → EventTypeDef
            ├─ if validator: run on data, log.warning on fail
            └─ event is created and published unchanged
```

Nothing downstream of `__post_init__` changes. The correlation
engine, SQLite storage, scanner queue, and web UI see the same
fields as today.

## Testing strategy

**Baseline protection:** `test/unit/spiderfoot/test_spiderfootevent.py`
must pass unchanged. Any break there is a regression, not a
design choice.

**New `test/unit/spiderfoot/test_event_types.py`:**

- Every `EventType` member has a corresponding `EVENT_TYPES` entry.
- `EVENT_TYPES` has exactly 172 entries (matches today's `eventDetails`).
- Every `EventTypeDef.name` equals its enum key's value (no drift).
- Category distribution matches pre-refactor counts (regression fence
  against accidental re-categorization).
- `EventTypeCategory` has exactly the five values `ROOT`, `ENTITY`,
  `DESCRIPTOR`, `INTERNAL`, `SUBENTITY`.

**New behaviour tests on `SpiderFootEvent` (appended to
`test_spiderfootevent.py`):**

- Constructor with `eventType="DNS_NAME"` (str) and
  `eventType=EventType.DNS_NAME` (enum) produce equal events.
- Unknown string `eventType="FAKEFAKE"`: event is created, a warning
  matching `/unknown eventType/i` is emitted via `caplog` /
  `assertLogs`.
- Registered type with `validator` returning False → warning emitted
  matching `/validation failed/i`, event still created.
- Registered type with no validator → no warning.

**Integration:** `./test/run` must report 1599 passing + 35 skipped,
same as the post-structured-logging baseline. Any delta indicates a
behaviour regression in one of the 231 module call sites.

**Real-scan smoke test:** run a short scan against `spiderfoot.net`
locally, `grep -iE 'unknown eventType|validation failed'` across the
JSON log output. Zero matches = clean migration. Any matches are
either registry typos (fix `event_types.py`) or genuine pre-existing
bugs in a module (fix or flag for Phase 1 item 3).

## Rollout

Single commit. No feature flag, no env-var toggle, no deprecation
warnings. The change is behaviourally equivalent for every
legitimate caller; all new behaviour is observable only via logs.

Ordered steps for the implementation plan:
1. Create `spiderfoot/event_types.py` with the full 172-entry
   registry, populated from today's `eventDetails`.
2. Replace `SpiderFootEvent` with the dataclass version; keep public
   API byte-compatible; add soft validation in `__post_init__`.
3. Replace `eventDetails` consumers in `db.py` with iteration over
   `EVENT_TYPES`.
4. Delete `eventDetails`.
5. Verify `./test/run` is green and real-scan smoke test shows no
   warnings.

## Follow-ups enabled by this change

- Validator population per event type (incremental).
- Module metadata registry (Phase 1 item 2) can reuse the same
  `dataclass(frozen=True)` pattern.
- Eventual flip of `SpiderFootEvent.__init__` signature from
  `str | EventType` to `EventType` required (pure type annotation
  change once all callers have migrated, tracked as a later spec).
- `mypy` / `pyright` pass on `spiderfoot/` package — the typed
  registry is the foundation that makes this useful.
