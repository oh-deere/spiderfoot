# Structured (JSON) Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit SpiderFoot's stderr console logs as JSON when `sys.stdout.isatty()` is False (containers/pipes) or when `SPIDERFOOT_LOG_FORMAT=json` is set, so Grafana Loki can JSON-parse `scanId`, `module`, `level`, `timestamp`, `message`. Make the existing rotating file handlers opt-out via `SPIDERFOOT_LOG_FILES=false` so clustered deployments have Loki as the single log destination.

**Architecture:** One new `logging.Formatter` subclass (`SpiderFootJsonFormatter`) and two module-level helpers (`_should_use_json`, `_log_files_enabled`) added to `spiderfoot/logger.py`. `logListenerSetup` picks the formatter from the helper and conditionally appends the file handlers. No call-site changes anywhere. Shipped `Dockerfile` sets both env vars so the image is cluster-ready by default.

**Tech Stack:** Python 3.12+ stdlib only (`logging`, `json`, `datetime`, `os`, `sys`). Tests use `unittest.TestCase` (matches existing style in `test/unit/spiderfoot/`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-19-structured-logging-design.md`.

---

## File Structure

- **Modify** `spiderfoot/logger.py` — add formatter class + two helpers + wire them into `logListenerSetup`. File is ~160 lines; change grows it to ~230 lines. Single responsibility (logging pipeline configuration) — no need to split.
- **Create** `test/unit/spiderfoot/test_logger.py` — unit tests for the formatter and helpers. Follows `unittest.TestCase` pattern used by sibling `test_spiderfootevent.py` / `test_spiderfoottarget.py` / `test_spiderfootdb.py`.
- **Modify** `Dockerfile` — add two `ENV` lines in the runtime stage so the shipped image defaults to JSON + stdout-only.

---

## Context for the implementer

Key facts to internalize before you start (so you don't guess):

- SpiderFoot uses a `QueueListener` log architecture: worker processes enqueue `LogRecord`s via `QueueHandler`; a single listener thread in the main process fans records out to handlers. Our changes are all on the listener side — worker side is untouched.
- `SpiderFootPlugin.debug/info/error` (in `spiderfoot/plugin.py`) calls `self.log.debug(msg, extra={'scanId': self.__scanId__})`. That's the **only** place `scanId` is attached to records. Scan-orchestrator logs (from `sfscan.py`, `sf.py`) don't have `scanId` — the formatter must tolerate its absence.
- The existing `SpiderFootSqliteLogHandler` (lines 11-66 of `spiderfoot/logger.py`) writes scan logs to the SQLite DB for the per-scan "Log" tab in the web UI. **Do not modify or remove it.** It remains in the handler chain regardless of our env vars.
- Existing tests use `unittest.TestCase` (not pure pytest). Follow that convention. `conftest.py` provides a `default_options` autouse fixture but the logger tests don't need it — logger setup takes an `opts` dict argument directly.
- Running flake8 locally: `python3 -m flake8 . --count --show-source --statistics` from the repo root. `./test/run` runs flake8 + pytest together (what CI mirrors).
- Running one test: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v` or narrow to a single function with `::TestClassName::test_fn_name`.

---

## Task 1: Create test file with three formatter tests, verify they fail

**Files:**
- Create: `test/unit/spiderfoot/test_logger.py`

- [ ] **Step 1: Create the test file with three initial tests that drive the formatter**

Create `test/unit/spiderfoot/test_logger.py` with this content:

```python
# test_logger.py
import json
import logging
import unittest

from spiderfoot.logger import SpiderFootJsonFormatter


def _make_record(msg="hello", level=logging.INFO, extras=None, exc_info=None):
    record = logging.LogRecord(
        name="spiderfoot.sflib",
        level=level,
        pathname="/src/spiderfoot/sflib.py",
        lineno=42,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    if extras:
        for k, v in extras.items():
            setattr(record, k, v)
    return record


class TestSpiderFootJsonFormatter(unittest.TestCase):

    def test_json_formatter_contains_standard_fields(self):
        formatter = SpiderFootJsonFormatter()
        record = _make_record(msg="Scan [abc123] completed.",
                              extras={"scanId": "abc123"})
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "spiderfoot.sflib")
        self.assertEqual(parsed["message"], "Scan [abc123] completed.")
        self.assertEqual(parsed["module"], "sflib")
        self.assertEqual(parsed["scanId"], "abc123")
        self.assertIn("timestamp", parsed)
        # RFC3339 with millisecond precision ending in Z
        self.assertTrue(parsed["timestamp"].endswith("Z"))
        self.assertRegex(parsed["timestamp"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    def test_json_formatter_omits_scanid_when_absent(self):
        formatter = SpiderFootJsonFormatter()
        record = _make_record()  # no scanId extra
        parsed = json.loads(formatter.format(record))
        self.assertNotIn("scanId", parsed)

    def test_json_formatter_includes_exception(self):
        formatter = SpiderFootJsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = _make_record(msg="it failed", level=logging.ERROR,
                              exc_info=exc_info)
        parsed = json.loads(formatter.format(record))
        self.assertIn("exception", parsed)
        self.assertIn("ValueError: boom", parsed["exception"])
        self.assertIn("Traceback", parsed["exception"])

    def test_json_formatter_handles_non_serializable_extras(self):
        formatter = SpiderFootJsonFormatter()

        class Opaque:
            def __str__(self):
                return "opaque-value"

        record = _make_record(extras={"scanId": Opaque()})
        # Should not raise — falls back to str() via default=str
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["scanId"], "opaque-value")
```

- [ ] **Step 2: Run the tests to confirm they fail with ImportError**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v`

Expected output includes:
```
ERROR test/unit/spiderfoot/test_logger.py - ImportError: cannot import name 'SpiderFootJsonFormatter' from 'spiderfoot.logger'
```

The failure should be at collection time (import error), not at runtime. If the failure mode differs, stop and investigate before writing the implementation.

- [ ] **Step 3: Commit the failing tests**

```bash
git add test/unit/spiderfoot/test_logger.py
git commit -m "$(cat <<'EOF'
test: add failing tests for SpiderFootJsonFormatter

Drives Task 2: implement the formatter class.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement `SpiderFootJsonFormatter`

**Files:**
- Modify: `spiderfoot/logger.py` (add imports + new class near the top)

- [ ] **Step 1: Add `json` and `datetime` imports**

Find the existing import block at the top of `spiderfoot/logger.py` (lines 1-8):

```python
import atexit
import logging
import sys
import time
from contextlib import suppress
from logging.handlers import QueueHandler, QueueListener

from spiderfoot import SpiderFootDb, SpiderFootHelpers
```

Replace it with:

```python
import atexit
import json
import logging
import os
import sys
import time
from contextlib import suppress
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener

from spiderfoot import SpiderFootDb, SpiderFootHelpers
```

(Adds `json`, `os`, and `from datetime import datetime, timezone`. `os` is needed for the env-var helpers in Task 4; bringing it in now keeps the imports change in one commit.)

- [ ] **Step 2: Add the `SpiderFootJsonFormatter` class**

Immediately after the `SpiderFootHelpers` import and before the `SpiderFootSqliteLogHandler` class, insert:

```python
# Standard LogRecord attributes we don't want re-emitted as "extras".
# Everything else set via logger.*(..., extra={...}) becomes a
# top-level JSON field.
_STANDARD_LOGRECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "asctime", "taskName",
})


class SpiderFootJsonFormatter(logging.Formatter):
    """Emit one compact JSON object per log record.

    Produces RFC3339 UTC timestamps with millisecond precision and
    promotes any ``extra={...}`` keyword from the caller into a
    top-level field. ``scanId`` (set by SpiderFootPlugin helpers) is
    the primary filter operators use via ``| json | scanId="..."``
    in LogQL.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        # Millisecond precision, trailing Z.
        timestamp = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"

        fields = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }

        # Promote any caller-supplied extras (scanId, component, etc.)
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_ATTRS or key.startswith("_"):
                continue
            fields[key] = value

        if record.exc_info:
            fields["exception"] = self.formatException(record.exc_info)

        return json.dumps(fields, default=str)
```

- [ ] **Step 3: Run the tests and confirm all four pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v`

Expected: all four tests in `TestSpiderFootJsonFormatter` pass. If `test_json_formatter_contains_standard_fields` fails on the timestamp regex, the most likely cause is using `record.created` as-is (seconds since epoch float) without millisecond formatting — re-check Step 2's `ts.microsecond // 1000:03d` fragment.

- [ ] **Step 4: Run flake8 to catch style issues before committing**

Run: `python3 -m flake8 spiderfoot/logger.py test/unit/spiderfoot/test_logger.py`

Expected: no output (clean). If warnings appear, fix them inline.

- [ ] **Step 5: Commit**

```bash
git add spiderfoot/logger.py
git commit -m "$(cat <<'EOF'
logger: add SpiderFootJsonFormatter

One compact JSON object per log record with RFC3339 UTC timestamps
at millisecond precision. Promotes caller-supplied extras (scanId,
component) into top-level fields so LogQL pipelines can filter on
them without index-label explosion. Tolerates non-serializable
extras via json.dumps(..., default=str).

Refs docs/superpowers/specs/2026-04-19-structured-logging-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add format-selection and file-toggle helpers (TDD)

**Files:**
- Modify: `test/unit/spiderfoot/test_logger.py` — append a new test class
- Modify: `spiderfoot/logger.py` — add two helpers

- [ ] **Step 1: Add failing tests for `_should_use_json` and `_log_files_enabled`**

Append the following to `test/unit/spiderfoot/test_logger.py`:

```python
from unittest import mock

from spiderfoot.logger import _should_use_json, _log_files_enabled


class TestShouldUseJson(unittest.TestCase):

    def _run(self, env_value, isatty_value):
        env = {} if env_value is None else {"SPIDERFOOT_LOG_FORMAT": env_value}
        with mock.patch.dict("os.environ", env, clear=False):
            if env_value is None:
                # Ensure the var is absent even if the outer env had it.
                os_env_backup = os.environ.pop("SPIDERFOOT_LOG_FORMAT", None)
                try:
                    with mock.patch("sys.stdout.isatty", return_value=isatty_value):
                        return _should_use_json()
                finally:
                    if os_env_backup is not None:
                        os.environ["SPIDERFOOT_LOG_FORMAT"] = os_env_backup
            else:
                with mock.patch("sys.stdout.isatty", return_value=isatty_value):
                    return _should_use_json()

    def test_env_json_forces_json(self):
        self.assertTrue(self._run("json", isatty_value=True))
        self.assertTrue(self._run("json", isatty_value=False))

    def test_env_text_forces_text(self):
        self.assertFalse(self._run("text", isatty_value=True))
        self.assertFalse(self._run("text", isatty_value=False))

    def test_env_unset_follows_tty(self):
        # Interactive terminal → text
        self.assertFalse(self._run(None, isatty_value=True))
        # Pipe/container → json
        self.assertTrue(self._run(None, isatty_value=False))

    def test_env_bogus_value_falls_through_to_tty(self):
        self.assertFalse(self._run("garbage", isatty_value=True))
        self.assertTrue(self._run("garbage", isatty_value=False))


class TestLogFilesEnabled(unittest.TestCase):

    def _run(self, env_value):
        env = {} if env_value is None else {"SPIDERFOOT_LOG_FILES": env_value}
        with mock.patch.dict("os.environ", env, clear=False):
            if env_value is None:
                os.environ.pop("SPIDERFOOT_LOG_FILES", None)
            return _log_files_enabled()

    def test_unset_defaults_to_enabled(self):
        self.assertTrue(self._run(None))

    def test_explicit_true(self):
        self.assertTrue(self._run("true"))
        self.assertTrue(self._run("TRUE"))
        self.assertTrue(self._run("anything-that-is-not-false"))

    def test_explicit_false(self):
        self.assertFalse(self._run("false"))
        self.assertFalse(self._run("False"))
        self.assertFalse(self._run("FALSE"))
```

Also add `import os` at the top of the test file (if not already there from Task 1 — it isn't, so add it):

Change the top of `test/unit/spiderfoot/test_logger.py` from:
```python
import json
import logging
import unittest

from spiderfoot.logger import SpiderFootJsonFormatter
```

to:
```python
import json
import logging
import os
import unittest

from spiderfoot.logger import SpiderFootJsonFormatter
```

- [ ] **Step 2: Run the new tests and confirm they fail with ImportError**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v`

Expected: collection error — `ImportError: cannot import name '_should_use_json'`.

- [ ] **Step 3: Implement both helpers in `spiderfoot/logger.py`**

Insert these two helpers immediately after the `SpiderFootJsonFormatter` class (before `SpiderFootSqliteLogHandler`):

```python
def _should_use_json() -> bool:
    """Decide whether the console handler should emit JSON.

    ``SPIDERFOOT_LOG_FORMAT`` = ``json`` or ``text`` is a deterministic
    override. Anything else (including unset) falls back to
    ``sys.stdout.isatty()`` — interactive terminal gets text,
    non-TTY (pipe, container) gets JSON.
    """
    override = os.environ.get("SPIDERFOOT_LOG_FORMAT", "").lower()
    if override == "json":
        return True
    if override == "text":
        return False
    # Fail-open to auto-detect for any unknown value.
    return not sys.stdout.isatty()


def _log_files_enabled() -> bool:
    """Return False only when ``SPIDERFOOT_LOG_FILES`` is explicitly ``false``.

    Any other value (including unset) preserves the legacy rotating
    file handlers.
    """
    value = os.environ.get("SPIDERFOOT_LOG_FILES", "").lower()
    return value != "false"
```

- [ ] **Step 4: Run the tests and confirm they all pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v`

Expected: every test in `TestSpiderFootJsonFormatter`, `TestShouldUseJson`, and `TestLogFilesEnabled` passes.

- [ ] **Step 5: Flake8 + commit**

```bash
python3 -m flake8 spiderfoot/logger.py test/unit/spiderfoot/test_logger.py
```

Expected: no output.

```bash
git add spiderfoot/logger.py test/unit/spiderfoot/test_logger.py
git commit -m "$(cat <<'EOF'
logger: add format-selection + file-toggle env var helpers

_should_use_json picks JSON when SPIDERFOOT_LOG_FORMAT=json or when
stdout is not a TTY; text otherwise. _log_files_enabled returns
False only on explicit SPIDERFOOT_LOG_FILES=false. Both helpers are
pure (env var + sys.stdout.isatty) so tests just mock those.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire helpers into `logListenerSetup` (TDD)

**Files:**
- Modify: `test/unit/spiderfoot/test_logger.py` — append listener tests
- Modify: `spiderfoot/logger.py:logListenerSetup`

- [ ] **Step 1: Add listener-level tests that exercise the wiring**

Append to `test/unit/spiderfoot/test_logger.py`:

```python
import multiprocessing
from logging.handlers import TimedRotatingFileHandler

from spiderfoot import SpiderFootHelpers
from spiderfoot.logger import logListenerSetup


def _minimal_opts():
    return {
        "_debug": False,
        "__logging": True,
        "__database": f"{SpiderFootHelpers.dataPath()}/spiderfoot.test.db",
    }


class TestLogListenerSetup(unittest.TestCase):

    def _run(self, env):
        q = multiprocessing.Queue()
        with mock.patch.dict("os.environ", env, clear=False):
            listener = logListenerSetup(q, _minimal_opts())
        try:
            return list(listener.handlers)
        finally:
            listener.stop()

    def test_json_formatter_selected_when_env_json(self):
        handlers = self._run({"SPIDERFOOT_LOG_FORMAT": "json",
                              "SPIDERFOOT_LOG_FILES": "true"})
        console = next(h for h in handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, TimedRotatingFileHandler))
        self.assertIsInstance(console.formatter, SpiderFootJsonFormatter)

    def test_text_formatter_selected_when_env_text(self):
        handlers = self._run({"SPIDERFOOT_LOG_FORMAT": "text",
                              "SPIDERFOOT_LOG_FILES": "true"})
        console = next(h for h in handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, TimedRotatingFileHandler))
        self.assertNotIsInstance(console.formatter, SpiderFootJsonFormatter)

    def test_file_handlers_absent_when_log_files_false(self):
        handlers = self._run({"SPIDERFOOT_LOG_FILES": "false",
                              "SPIDERFOOT_LOG_FORMAT": "text"})
        file_handlers = [h for h in handlers
                         if isinstance(h, TimedRotatingFileHandler)]
        self.assertEqual(file_handlers, [])

    def test_file_handlers_present_by_default(self):
        # Default (SPIDERFOOT_LOG_FILES unset) preserves legacy handlers.
        # Ensure the var isn't leaking in from the outer shell environment.
        original = os.environ.pop("SPIDERFOOT_LOG_FILES", None)
        try:
            handlers = self._run({"SPIDERFOOT_LOG_FORMAT": "text"})
            file_handlers = [h for h in handlers
                             if isinstance(h, TimedRotatingFileHandler)]
            self.assertEqual(len(file_handlers), 2)
        finally:
            if original is not None:
                os.environ["SPIDERFOOT_LOG_FILES"] = original
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py::TestLogListenerSetup -v`

Expected: `test_json_formatter_selected_when_env_json` fails because the console handler is currently always formatted with the text `Formatter`. `test_file_handlers_absent_when_log_files_false` fails because file handlers are always appended.

- [ ] **Step 3: Modify `logListenerSetup` to consult the helpers**

In `spiderfoot/logger.py`, locate `logListenerSetup` (currently lines 68-133). Change the block that builds handlers.

Replace the section starting with `# Set log format` and ending with the `spiderFootLogListener = QueueListener(loggingQueue, *handlers)` line — the current lines 113-131 — with:

```python
    # Set log format
    log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(module)s : %(message)s")
    debug_format = logging.Formatter("%(asctime)s [%(levelname)s] %(filename)s:%(lineno)s : %(message)s")
    if _should_use_json():
        console_handler.setFormatter(SpiderFootJsonFormatter())
    else:
        console_handler.setFormatter(log_format)
    debug_handler.setFormatter(debug_format)
    error_handler.setFormatter(debug_format)

    if doLogging:
        handlers = [console_handler]
        if _log_files_enabled():
            handlers.append(debug_handler)
            handlers.append(error_handler)
    else:
        handlers = []

    if doLogging and opts is not None:
        sqlite_handler = SpiderFootSqliteLogHandler(opts)
        sqlite_handler.setLevel(logLevel)
        sqlite_handler.setFormatter(log_format)
        handlers.append(sqlite_handler)
    spiderFootLogListener = QueueListener(loggingQueue, *handlers)
    spiderFootLogListener.start()
    atexit.register(stop_listener, spiderFootLogListener)
    return spiderFootLogListener
```

Notes for the implementer:
- Construct `debug_handler` and `error_handler` **before** this block (they're already constructed in the function above — do not move their construction). Even if they're skipped from the handler list, constructing them is cheap and avoids restructuring the surrounding code.
- The `SpiderFootSqliteLogHandler` **always** stays in the chain when `doLogging` is True — it's product functionality, not controlled by `_log_files_enabled()`.
- The existing line `log_format = logging.Formatter(...)` stays because the SQLite handler uses it for its own `setFormatter` call below.

- [ ] **Step 4: Run the tests and confirm they all pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_logger.py -v`

Expected: every test passes (`TestSpiderFootJsonFormatter`, `TestShouldUseJson`, `TestLogFilesEnabled`, `TestLogListenerSetup`).

- [ ] **Step 5: Run the full suite to catch regressions**

Run: `./test/run`

Expected: flake8 clean + 1584 pytest pass (plus the ~10 new cases from `test_logger.py`) + 35 skipped. If any pre-existing test now fails, stop — it means the listener rewiring changed an observable property of logging the rest of the suite relies on.

- [ ] **Step 6: Commit**

```bash
git add spiderfoot/logger.py test/unit/spiderfoot/test_logger.py
git commit -m "$(cat <<'EOF'
logger: wire JSON formatter + file-handler toggle into listener

logListenerSetup now picks SpiderFootJsonFormatter when
_should_use_json() is True (env var or non-TTY stdout) and only
appends the rotating debug/error file handlers when
_log_files_enabled() is True. The SQLite per-scan log handler is
unaffected — that's product functionality.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Make the shipped Docker image cluster-ready by default

**Files:**
- Modify: `Dockerfile` (the minimal one, not `Dockerfile.full`)

- [ ] **Step 1: Add the two ENV lines**

Locate the second stage of `Dockerfile` (starting with `FROM python:3.12-slim-bookworm` at the bottom — roughly line 47). Find the existing ENV block:

```dockerfile
# Place database and logs outside installation directory
ENV SPIDERFOOT_DATA=/var/lib/spiderfoot
ENV SPIDERFOOT_LOGS=/var/lib/spiderfoot/log
ENV SPIDERFOOT_CACHE=/var/lib/spiderfoot/cache
```

Replace with:

```dockerfile
# Place database and logs outside installation directory
ENV SPIDERFOOT_DATA=/var/lib/spiderfoot
ENV SPIDERFOOT_LOGS=/var/lib/spiderfoot/log
ENV SPIDERFOOT_CACHE=/var/lib/spiderfoot/cache

# Structured logging for Loki. Override with SPIDERFOOT_LOG_FORMAT=text
# for interactive debugging (e.g. docker run -it ... /bin/sh).
ENV SPIDERFOOT_LOG_FORMAT=json
ENV SPIDERFOOT_LOG_FILES=false
```

- [ ] **Step 2: Verify the image still builds**

Run: `docker build -t sf-logging-verify .`

Expected: build succeeds (no change from before except two env vars are now set).

- [ ] **Step 3: Verify the container emits JSON on stdout**

Run:
```bash
docker run --rm -d --name sf-logging-smoke -p 127.0.0.1:5996:5001 sf-logging-verify
sleep 5
docker logs sf-logging-smoke 2>&1 | head -3
docker stop sf-logging-smoke
docker rmi sf-logging-verify
```

Expected: each line of the output should parse as JSON with `level`, `timestamp`, `logger`, `message` fields. Sample:
```json
{"timestamp": "2026-04-19T15:24:42.743Z", "level": "INFO", "logger": "spiderfoot.sf", "message": "Starting web server at 0.0.0.0:5001 ...", "module": "sf"}
```

If you see text-format lines instead, the env var propagation is broken — re-check the Dockerfile edit and that both `ENV` directives landed in the runtime stage, not the build stage.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "$(cat <<'EOF'
Dockerfile: default to JSON logs on stdout for cluster deploys

The shipped production image sets SPIDERFOOT_LOG_FORMAT=json and
SPIDERFOOT_LOG_FILES=false so stdout goes to Loki and no
redundant rotating files are written inside the container. The TTY
auto-detect would catch most of this anyway; explicit env vars
remove ambiguity for interactive debug sessions via docker run -it.

Dockerfile.full is intentionally left alone — that variant is for
local tool-enabled development where the legacy behavior is fine.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update service-level `CLAUDE.md` with the new env vars

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add an env-var section**

Open `CLAUDE.md` in the repo root and find the "Conventions to follow" section at the bottom. Immediately before it, insert a new section:

```markdown
## Environment variables (runtime)

`sf.py` reads `SPIDERFOOT_DATA`, `SPIDERFOOT_LOGS`, `SPIDERFOOT_CACHE` for data/log/cache paths (see Dockerfile). Two additional env vars control the logging pipeline (see `spiderfoot/logger.py`):

- `SPIDERFOOT_LOG_FORMAT={json,text}` — deterministic override for the console formatter. When unset or set to anything else, the format is auto-selected: text when `sys.stdout.isatty()`, JSON otherwise. The shipped `Dockerfile` sets this to `json`.
- `SPIDERFOOT_LOG_FILES={true,false}` — when `false`, the two `TimedRotatingFileHandler` instances under `$SPIDERFOOT_LOGS` are not attached; stdout + the SQLite per-scan log become the only log destinations. The shipped `Dockerfile` sets this to `false` so Loki is the single authoritative log store. Default (unset) preserves the historical behavior for `./sf.py` runs from source.

The per-scan SQLite log (`SpiderFootSqliteLogHandler`) is not controlled by these vars — it's product functionality that feeds the scan UI's "Log" tab.

```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document SPIDERFOOT_LOG_FORMAT and SPIDERFOOT_LOG_FILES

Captures the logging env var contract added in the structured-logging
change so future Claude Code sessions and humans know the toggles
exist.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] **Step 1: Run the CI-equivalent command end-to-end**

Run: `./test/run`

Expected: flake8 clean, all tests pass, no new failures.

- [ ] **Step 2: Smoke-test the web UI locally with both formats**

```bash
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py -l 127.0.0.1:5998 2>/tmp/sf-json.log &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5998/
pkill -f "sf.py -l 127.0.0.1:5998"
head -3 /tmp/sf-json.log
```

Expected: HTTP 200, and the first three lines of `/tmp/sf-json.log` parse as JSON.

Then repeat with `SPIDERFOOT_LOG_FORMAT=text` and verify output is the original human-readable format.

- [ ] **Step 3: Report completion**

Six commits landed. Summary: JSON formatter + two env vars + cluster-ready Dockerfile defaults + CLAUDE.md update. Zero call-site changes anywhere else in the code.
