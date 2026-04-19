# Structured (JSON) logging for Loki

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-19

## Goal

Emit SpiderFoot's stderr console logs as machine-parseable JSON when
running in the cluster, so that Grafana Loki can ingest them with
`scanId` and `module` as first-class labels. Keep the human-readable
text format as the default for interactive local development. Make
the in-container rotating log files opt-out, since Loki becomes the
authoritative log destination once the service is clustered.

## Non-goals

- Do **not** replace the existing SQLite-backed per-scan log handler
  (`SpiderFootSqliteLogHandler`). That feeds the "Log" tab in the
  scan UI and is product functionality, not ops telemetry.
- Do **not** redesign the logging pipeline, change call sites, or
  introduce a context-library like `structlog`.
- Do **not** add CherryPy request-level access logging, Prometheus
  metrics, or log-level dynamic adjustment. Each of those is its own
  separate change.

## Design

### Format selection

`spiderfoot/logger.py:logListenerSetup` chooses one of two formatters
for the existing `console_handler` (which continues to write to
`sys.stderr`):

| Condition | Formatter |
|---|---|
| `SPIDERFOOT_LOG_FORMAT=json` | JSON |
| `SPIDERFOOT_LOG_FORMAT=text` | Text (unchanged legacy format) |
| env var unset or any other value, `sys.stdout.isatty()` True | Text |
| env var unset or any other value, `sys.stdout.isatty()` False | JSON |

Auto-detect uses `sys.stdout.isatty()` (not stderr) because that
reliably distinguishes interactive terminal from container/pipe
contexts. The env var is the deterministic override.

### File handlers

`logListenerSetup` currently attaches two `TimedRotatingFileHandler`
instances (`spiderfoot.debug.log`, `spiderfoot.error.log`) writing
under `$SPIDERFOOT_LOGS`. These become redundant once Loki ingests
stdout.

Behavior driven by `SPIDERFOOT_LOG_FILES`:

| Value | File handlers |
|---|---|
| `false` (case-insensitive) | Not attached |
| anything else, or unset | Attached (current behavior) |

Default preserves the existing behavior for users running from source.

### JSON output shape

One compact JSON object per line, newline-terminated (JSON Lines).
Produced via `json.dumps(fields, default=str)` so any non-serializable
extra stringifies rather than raising.

Always present:

- `timestamp` — ISO-8601 / RFC3339 in UTC with millisecond precision
  (e.g. `"2026-04-19T15:24:42.743Z"`).
- `level` — one of `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- `logger` — the `LogRecord.name` (e.g. `"spiderfoot.sflib"`).
- `message` — already-formatted message (equivalent to
  `record.getMessage()`).
- `module` — `LogRecord.module` (stdlib auto-populates this as the
  basename of the source file without `.py`).

Conditionally present:

- `scanId` — when the record has a `scanId` extra. Set by
  `SpiderFootPlugin.debug/info/error` on all plugin-emitted log
  lines; not set by the scan orchestrator's own logs.
- `exception` — formatted traceback string when `exc_info` is set.
  Produced via `logging.Formatter.formatException`.

Field names are chosen for Grafana Loki's JSON parser default
pipeline: `level`, `timestamp`, `message` are auto-recognized by the
built-in detected-field logic; `scanId` is the label operators will
filter on.

### Dockerfile defaults

The production `Dockerfile` (the minimal one, not `Dockerfile.full`)
sets:

```dockerfile
ENV SPIDERFOOT_LOG_FORMAT=json
ENV SPIDERFOOT_LOG_FILES=false
```

The shipped image is cluster-ready by default. The TTY auto-detect
would catch most of this anyway, but the explicit env vars eliminate
ambiguity when someone runs `docker run -it` to debug inside the
container. `Dockerfile.full` is **not** modified — that variant is
primarily for local-tool-enabled development and leaving current
behavior there reduces surprise.

## Implementation sketch

All changes live in `spiderfoot/logger.py` except two Dockerfile
lines and tests.

1. Add `SpiderFootJsonFormatter(logging.Formatter)` — ~30 lines, uses
   stdlib `json`. Reads `record.scanId` / `record.module` via
   `getattr(record, "scanId", None)`. Emits one compact JSON object
   per record, newline-terminated.
2. Add `_should_use_json() -> bool` helper that reads
   `SPIDERFOOT_LOG_FORMAT` and falls back to `sys.stdout.isatty()`.
3. Add `_log_files_enabled() -> bool` helper that reads
   `SPIDERFOOT_LOG_FILES`.
4. In `logListenerSetup`: pick `SpiderFootJsonFormatter` vs the
   existing `log_format` based on `_should_use_json()`; skip
   appending `debug_handler` and `error_handler` to the handler list
   when `_log_files_enabled()` is False.
5. `Dockerfile`: add the two `ENV` lines.
6. New test file `test/unit/spiderfoot/test_logger.py` covering the
   four cases listed in the Testing section.

## Testing

Unit tests in `test/unit/spiderfoot/test_logger.py`:

- `test_json_formatter_contains_standard_fields` — construct a
  `LogRecord` with `scanId` / `module` extras, format it, assert the
  result parses as JSON with the expected keys and values.
- `test_json_formatter_includes_exception` — format a record with
  `exc_info`, assert the `exception` field is present and contains
  a traceback.
- `test_should_use_json_respects_env_var` — parametrize over
  combinations of `SPIDERFOOT_LOG_FORMAT` and mocked TTY state;
  assert the expected return value.
- `test_log_files_disabled_via_env_var` — monkeypatch
  `SPIDERFOOT_LOG_FILES=false`, run `logListenerSetup`, assert no
  `TimedRotatingFileHandler` is present in the listener's handlers.

No integration test required — the change is formatter-level and is
covered by the above unit tests.

## Risk and rollback

Risk surface is small:

- **Behavior change for existing cluster operators:** anyone running
  SpiderFoot in a container today gets text logs. After this change
  they get JSON (via TTY auto-detect). Mitigation: set
  `SPIDERFOOT_LOG_FORMAT=text` in the Deployment if they want to
  preserve the old behavior.
- **Dependency on stdlib `json` being able to serialize extras:** if
  a caller sets a non-serializable value as an extra (e.g., an
  arbitrary object), formatting the record would raise. Mitigation:
  `json.dumps(..., default=str)` at the bottom of the formatter so
  unknown types stringify instead of erroring.

Rollback is a single-commit revert. No state is persisted in the new
format; Loki will happily ingest either.
