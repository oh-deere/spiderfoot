# Dead-module audit (Phase 1 item 3)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Reduce the 233-module surface area of the SpiderFoot fork by removing modules that:

1. Require a paid-only third-party subscription (`meta.dataSource.model = COMMERCIAL_ONLY` or `PRIVATE_ONLY`).
2. Target a service that has been shut down, acquired and paywalled, or reduced to a punitive free tier since the module was written.

Each deletion is pure maintenance-debt reduction: fewer `sfp_*` files to keep flake8-clean, fewer modules to audit for Python-3.12 compatibility, fewer third-party dependencies to track, fewer tests to run. Zero impact on the 163+ surviving modules.

## Non-goals

- **Not** building a runtime smoke-test harness that probes every module against a live target. That's a separate, larger project (Phase 1 option C).
- **Not** pruning orphaned event types from `spiderfoot/event_types.py` — they're 1-line entries with zero runtime cost, and removing them would invalidate correlation rules that reference them. Defer to a later "registry sweep" pass.
- **Not** rewriting surviving modules. If a module works but uses a slightly-rate-limited API, it stays.
- **Not** validating that surviving modules' free tiers still function end-to-end. Research is public pricing / docs pages only; no API key testing.
- **Not** removing module references in upstream documentation or the SpiderFoot web UI help pages. Those are decoupled — filename-glob module discovery (`SpiderFootHelpers.loadModulesAsDict`) automatically drops the module from UI lists.

## Design

### Tier structure

Three tiers, each with its own commit:

**Tier 1 — metadata-flagged removes (10 modules).**
Trust the existing `meta.dataSource.model` classification. No research needed.

- `COMMERCIAL_ONLY` (8): `sfp_c99`, `sfp_dehashed`, `sfp_haveibeenpwned`, `sfp_seon`, `sfp_sociallinks`, `sfp_spur`, `sfp_whoisology`, `sfp_whoxy`
- `PRIVATE_ONLY` (2): `sfp_fsecure_riddler`, `sfp_projectdiscovery`

Template file `sfp_template.py` is preserved — it's the reference for adding new modules, not a production module.

**Tier 2 — researched removes (target ~15-25 from ~68 candidates).**

Every module whose metadata says `FREE_AUTH_LIMITED` (52), `FREE_AUTH_UNLIMITED` (9), or `FREE_NOAUTH_LIMITED` (7) gets a web-research pass. `FREE_NOAUTH_UNLIMITED` modules are out of scope — no credential requirement, unlimited use — so we trust them unless a later smoke test catches a dead endpoint. Each is classified into exactly one of five buckets:

| Bucket | Meaning | Verdict |
|---|---|---|
| `DEAD` | DNS gone, 404 on homepage, or public "service shut down" notice | remove |
| `ACQUIRED` | Absorbed into a paid product (classic: Clearbit → HubSpot) | remove |
| `PAYWALLED` | Free tier removed since the module was written | remove |
| `PUNITIVE-FREE` | Free tier exists but <100 queries/month (useless for actual scans) | remove |
| `USABLE-FREE` | Genuinely usable free tier (≥1000 queries/month or similar) | keep |

Research is bounded to public pages: service homepage, pricing page, developer sign-up page. No API-key testing. No attempts at creating accounts. The goal is evidence strong enough to justify removing a module, not to audit individual modules' correctness.

Output: a decision table in `docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md` formatted as:

```markdown
| Module | Service | Status | Evidence URL | Verdict |
|---|---|---|---|---|
| sfp_clearbit | Clearbit | ACQUIRED | https://clearbit.com/... | remove |
```

User reviews the table, marks overrides inline, then Tier 2 executes the accumulated `remove` verdicts in one commit.

**Tier 3 — documented keeps.** Final surviving module list is appended to `CLAUDE.md` in a new "Module inventory" section, noting the audit date (2026-04-20) and the classification standard, so future contributors don't reintroduce paid-only modules without thought.

### Removal mechanics (per module)

For each `sfp_<name>` being removed, the cleanup is:

Always delete (all three may or may not exist; `git rm --ignore-unmatch` tolerates missing):
- `modules/sfp_<name>.py`
- `test/unit/modules/test_sfp_<name>.py`
- `test/integration/modules/test_sfp_<name>.py`

Remove if present:
- Any `setup.cfg` `per-file-ignores` entry referencing the module (e.g. `modules/sfp_alienvault.py:C901`, `modules/sfp_binaryedge.py:C901`).

Leave alone (per design Section 2):
- `spiderfoot/event_types.py` — orphaned event types stay for now.
- `correlations/*.yaml` — rules reference event types, not modules; silent inert matches are harmless.
- `spiderfoot/db.py`, `sfscan.py`, web UI — filename-glob discovery auto-updates; no hardcoded lists.

### Research parallelism (Tier 2 only)

The ~68-module sweep is dispatched as parallel subagents — one subagent per ~15 modules, 4 parallel workers, each producing a partial decision table. The controller merges partial tables into the single decisions file. Each subagent's job is pure web research + classification; no code changes inside subagents.

Wall-clock target: ≤15 min for the full Tier 2 research pass, vs ~1 hour serial.

### Verification (after each tier commit)

1. `./test/run` passes. Test count drops by (tests-per-removed-module); new baseline becomes the post-cull figure.
2. Smoke scan:
   ```bash
   SPIDERFOOT_LOG_FORMAT=json timeout 30 python3 ./sf.py \
       -s spiderfoot.net -m sfp_dnsresolve,sfp_whois 2>&1 | head -5
   ```
   Must produce valid JSON log lines. No `ModuleNotFoundError` on startup (which would indicate that something other than a module file hard-referenced a removed module name).

## Rollout

Three commits on `master`, in order:

1. **`modules: remove commercial / private-only modules (tier 1)`** — deletes 10 `.py` files + their tests + any `setup.cfg` entries.
2. **`modules: remove dead / paywalled modules (tier 2)`** — deletes the approved subset of the researched modules, plus the `tier2-decisions.md` spec artifact gets committed into the repo for audit history.
3. **`docs: document surviving module inventory (tier 3)`** — appends Module Inventory section to `CLAUDE.md`.

Tier 2 has an approval checkpoint — the decisions table commits first (without any module deletions) so the user can review; once the user approves, a follow-up commit performs the actual deletions.

## Follow-ups enabled by this change

- Every surviving module gets a smaller review surface if we later run a real runtime smoke-test harness.
- The Module Inventory in `CLAUDE.md` becomes an anti-regression fence: any future module PR that doesn't match the classification table is flagged during review.
- Post-cull, a "registry sweep" follow-up spec can prune orphaned event types from `spiderfoot/event_types.py` and update correlation rules. Deferred per design Section 2.
- Phase 1 item 2 (typed module metadata registry) gets a cleaner starting point.
