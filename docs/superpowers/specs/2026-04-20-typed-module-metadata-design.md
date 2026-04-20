# Typed module metadata registry (Phase 1 item 2)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Replace SpiderFoot modules' free-form `meta = {...}` dict with an import-time validator backed by typed enums and a frozen dataclass. Catches typos in `flags` / `useCases` / `categories`, enforces required fields (`name`, `summary`, `dataSource.website`, etc.), and refuses any module declaring the removed `COMMERCIAL_ONLY` / `PRIVATE_ONLY` models. Complements the typed event registry (Phase 1 item 1) and locks in the policy added by the dead-module audit (Phase 1 item 3).

## Non-goals

- **Not** rewriting the 122 existing modules to use typed constructors (`meta = ModuleMeta(...)`). Zero module-source edits.
- **Not** mandating meta on local-analysis modules (regex extractors, `sfp_tool_*`, DNS helpers). Modules with no `meta` attribute continue to load silently.
- **Not** building a dual-accept constructor. Scope is strictly "validate existing dicts at load time."
- **Not** changing the UI rendering path. `module.meta` stays a dict for anything that reads it today; typed form attached as `_typed_meta` for future consumers.
- **Not** touching the typed event registry, modules, scanner, or web UI templates.

## Design

### New module — `spiderfoot/module_meta.py`

One pure-data-plus-validator module. Imports: `enum`, `logging`, `dataclasses`. No SpiderFoot imports (avoids circular dependency — `helpers.py` will import from here, not vice versa).

```python
class ModuleFlag(str, enum.Enum):
    APIKEY = "apikey"
    SLOW = "slow"
    TOOL = "tool"
    ERRORPRONE = "errorprone"
    TOR = "tor"
    INVASIVE = "invasive"


class ModuleUseCase(str, enum.Enum):
    FOOTPRINT = "Footprint"
    INVESTIGATE = "Investigate"
    PASSIVE = "Passive"


class ModuleCategory(str, enum.Enum):
    CONTENT_ANALYSIS = "Content Analysis"
    CRAWLING_AND_SCANNING = "Crawling and Scanning"
    DNS = "DNS"
    LEAKS_DUMPS_AND_BREACHES = "Leaks, Dumps and Breaches"
    PASSIVE_DNS = "Passive DNS"
    PUBLIC_REGISTRIES = "Public Registries"
    REAL_WORLD = "Real World"
    REPUTATION_SYSTEMS = "Reputation Systems"
    SEARCH_ENGINES = "Search Engines"
    SECONDARY_NETWORKS = "Secondary Networks"
    SOCIAL_MEDIA = "Social Media"


class DataSourceModel(str, enum.Enum):
    FREE_NOAUTH_UNLIMITED = "FREE_NOAUTH_UNLIMITED"
    FREE_NOAUTH_LIMITED = "FREE_NOAUTH_LIMITED"
    FREE_AUTH_UNLIMITED = "FREE_AUTH_UNLIMITED"
    FREE_AUTH_LIMITED = "FREE_AUTH_LIMITED"


@dataclass(frozen=True, slots=True)
class DataSourceMeta:
    website: str
    model: DataSourceModel
    description: str
    references: tuple[str, ...] = ()
    api_key_instructions: tuple[str, ...] = ()
    fav_icon: str | None = None
    logo: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleMeta:
    name: str
    summary: str
    flags: frozenset[ModuleFlag]
    use_cases: frozenset[ModuleUseCase]
    categories: tuple[ModuleCategory, ...]
    data_source: DataSourceMeta


class ModuleMetaError(ValueError):
    """Raised when a module's meta dict is structurally broken."""


def validate_module_meta(raw: dict | None, module_name: str) -> ModuleMeta | None:
    """Parse and validate a module's `meta` dict. Return a ModuleMeta, or None if raw is None.
    Raise ModuleMetaError on structural failures. Warn on enum drift."""
```

**DataSourceModel deliberately omits `COMMERCIAL_ONLY` and `PRIVATE_ONLY`.** The audit removed those; if a new module declares them, the validator refuses it. This is the anti-regression fence promised in `CLAUDE.md`'s Module Inventory section.

### Validation rules

**Structural errors — raise `ModuleMetaError`, module fails to load:**

1. `meta` is not a dict.
2. Missing any of: `name`, `summary`, `flags`, `useCases`, `categories`, `dataSource`.
3. `name` / `summary` not a non-empty string.
4. `flags` / `useCases` / `categories` not list/tuple/set.
5. `dataSource` not a dict.
6. `dataSource` missing any of: `website`, `model`, `description`.
7. `dataSource.website` / `dataSource.description` not non-empty strings.
8. `dataSource.model` not in `DataSourceModel` — unconditional.
9. `ModuleFlag.APIKEY` in `flags` but `dataSource.apiKeyInstructions` is empty/missing.

**Enum drift — warn via `logging.getLogger("spiderfoot.module_meta")`, continue with best-effort parse:**

1. Unknown string in `flags` (e.g. `"apiKey"` typo) → drop that entry.
2. Unknown string in `useCases` → drop.
3. Unknown string in `categories` → drop.
4. Duplicate entries in any enum list → dedup via `frozenset`, warn once.
5. Non-canonical `useCases` ordering → silently canonicalize (not worth a warning).

**Warning format** (structured for Loki):
```
module_meta.drift module=sfp_foo field=flags unknown=apiKey
```
Uses `extra={"module_name": ..., "field": ..., "unknown": ...}` so JSON log lines carry each dimension as its own field.

### Integration point — `spiderfoot/helpers.py::SpiderFootHelpers.loadModulesAsDict`

Existing method already wraps per-module import in try/except to survive malformed modules. Add ~8 lines inside that try block:

```python
# after: klass = importlib.import_module(...)
raw_meta = getattr(klass, "meta", None)
if raw_meta is not None:
    try:
        klass._typed_meta = validate_module_meta(raw_meta, mod_name)
    except ModuleMetaError as exc:
        _log.error("module_meta.invalid module=%s error=%s", mod_name, exc)
        continue  # skip this module
```

`klass._typed_meta` is opt-in for future consumers. Nothing reads it yet; the UI continues to read `klass.meta` (the dict). The typed form is available when downstream code wants compile-time safety.

### Modules with no `meta` attribute

`validate_module_meta(None, ...)` returns `None` and logs nothing. About 60 local-analysis modules (`sfp_tool_*`, DNS resolvers, regex extractors) load unchanged.

## Testing

### Unit tests — `test/unit/spiderfoot/test_module_meta.py`

Each `ModuleMetaError` path + each warning path + happy paths:

1. Happy-path parse of a canonical meta dict returns a well-formed `ModuleMeta`.
2. Missing `name` → `ModuleMetaError` with "name" in message.
3. Missing `dataSource` → `ModuleMetaError`.
4. Missing `dataSource.website` → `ModuleMetaError`.
5. `flags=["apikey"]` without `apiKeyInstructions` → `ModuleMetaError`.
6. `dataSource.model = "COMMERCIAL_ONLY"` → `ModuleMetaError` (anti-regression fence).
7. Unknown flag (`"apiKey"` typo) → warning logged, returned `flags` contains only valid entries.
8. Unknown category → warning logged, dropped.
9. `useCases` in non-canonical order returns a stable canonical tuple.
10. Duplicate flags deduped, warning logged once.
11. `flags` provided as a `set` rather than a `list` accepted.
12. `validate_module_meta(None, ...)` returns `None` with no error or warning.

### Fleet-integration test

One test iterates the 122 production modules (via `SpiderFootHelpers.loadModulesAsDict` or direct file scan) and asserts `validate_module_meta(mod.meta, name)` returns a `ModuleMeta` instance for each. If any module fails validation, the correct resolution is **to fix the module's meta to match the validator** — not to relax the validator.

### Full-suite verification

`./test/run` must still pass. Module count unchanged at 186. Test count rises by ~13 (the unit tests + fleet integration). Any module whose meta is found to be structurally broken during the fleet run gets a corrected `meta` dict in the same commit.

## Rollout

Single commit after all-module-fleet compliance is verified:
1. Add `spiderfoot/module_meta.py`.
2. Add `test/unit/spiderfoot/test_module_meta.py`.
3. Wire the validator into `spiderfoot/helpers.py::loadModulesAsDict`.
4. Fix any module meta dicts that fail the fleet-integration test.
5. Commit all together.

## Follow-ups enabled

- UI refactor can read `module._typed_meta` for type-safe filtering / faceting (currently UI does string comparison on raw dicts).
- Module author workflow: when adding a new module, typos in flags/categories surface instantly at import instead of at UI render time.
- The `DataSourceModel` enum's omission of `COMMERCIAL_ONLY` / `PRIVATE_ONLY` turns the audit's no-paid-services policy from a doc convention into a code-enforced invariant.
- Future: add the `_typed_meta` attribute to `SpiderFootPlugin`'s type hints so `mypy` / `pyright` can infer the shape on any module class.
