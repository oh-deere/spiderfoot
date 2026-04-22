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


def _should_use_json() -> bool:
    """Decide whether the console handler should emit JSON.

    ``SPIDERFOOT_LOG_FORMAT`` = ``json`` or ``text`` is a deterministic
    override. Anything else (including unset) falls back to
    ``sys.stdout.isatty()`` — interactive terminal gets text,
    non-TTY (pipe, container) gets JSON.

    Returns:
        bool: True if the JSON formatter should be used.
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

    Returns:
        bool: True if the rotating file handlers should be attached.
    """
    value = os.environ.get("SPIDERFOOT_LOG_FILES", "").lower()
    return value != "false"


class SpiderFootPostgresLogHandler(logging.Handler):
    """Handler for logging scan events to the Postgres scan_log table.

    Feeds the per-scan "Log" tab in the SpiderFoot scan UI. The handler
    lazily opens a ``SpiderFootDb`` connection on the first
    ``emit()``, batches a small number of rows and flushes to the DB.
    """

    def __init__(self, opts: dict) -> None:
        """Initialize the handler.

        Args:
            opts (dict): SpiderFoot config (forwarded to
                ``SpiderFootDb`` when the DB handle is lazily created).
        """
        self.opts = opts
        self.dbh = None
        self.batch = []
        if self.opts.get('_debug', False):
            self.batch_size = 100
        else:
            self.batch_size = 5
        self.shutdown_hook = False
        super().__init__()

    def emit(self, record: 'logging.LogRecord') -> None:
        """Append a log record to the pending batch.

        Args:
            record (logging.LogRecord): Log event record
        """
        if not self.shutdown_hook:
            atexit.register(self.logBatch)
            self.shutdown_hook = True
        scanId = getattr(record, "scanId", None)
        component = getattr(record, "module", None)
        if scanId:
            level = ("STATUS" if record.levelname == "INFO" else record.levelname)
            self.batch.append((scanId, level, record.getMessage(), component, time.time()))
            if len(self.batch) >= self.batch_size:
                self.logBatch()

    def logBatch(self):
        """Flush the pending batch of log rows to Postgres."""
        batch = self.batch
        self.batch = []
        if not batch:
            # Nothing to flush (common at atexit on scans that never
            # emitted a log row) — don't open a DB connection just to
            # insert zero rows.
            return
        try:
            if self.dbh is None:
                # Create a new database handle when the first log batch is processed
                self.makeDbh()
            logResult = self.dbh.scanLogEvents(batch)
            if logResult is False:
                # Try to recreate database handle if insert failed
                self.makeDbh()
                self.dbh.scanLogEvents(batch)
        except Exception:
            # Swallow flush errors — this runs from atexit during
            # interpreter shutdown, and test fixtures may have already
            # torn the DB down. Raising here would pollute the output
            # without helping anyone.
            pass

    def makeDbh(self) -> None:
        """Open (or re-open) the backing ``SpiderFootDb`` handle."""
        self.dbh = SpiderFootDb(self.opts)


# Backwards-compatible alias — retained for any external callers that
# still reference the legacy SQLite class name.
SpiderFootSqliteLogHandler = SpiderFootPostgresLogHandler


def logListenerSetup(loggingQueue, opts: dict = None) -> 'logging.handlers.QueueListener':
    """Create and start a SpiderFoot log listener in its own thread.

    This function should be called as soon as possible in the main
    process, or whichever process is attached to stdin/stdout.

    Args:
        loggingQueue (Queue): Queue (accepts both normal and multiprocessing queue types)
                              Must be instantiated in the main process.
        opts (dict): SpiderFoot config

    Returns:
        spiderFootLogListener (logging.handlers.QueueListener): Log listener
    """
    if opts is None:
        opts = dict()
    doLogging = opts.get("__logging", True)
    debug = opts.get("_debug", False)
    logLevel = (logging.DEBUG if debug else logging.INFO)

    # Log to terminal
    console_handler = logging.StreamHandler(sys.stderr)

    # Log debug messages to file
    log_dir = SpiderFootHelpers.logPath()
    debug_handler = logging.handlers.TimedRotatingFileHandler(
        f"{log_dir}/spiderfoot.debug.log",
        when="d",
        interval=1,
        backupCount=30
    )

    # Log error messages to file
    error_handler = logging.handlers.TimedRotatingFileHandler(
        f"{log_dir}/spiderfoot.error.log",
        when="d",
        interval=1,
        backupCount=30
    )

    # Filter by log level
    console_handler.addFilter(lambda x: x.levelno >= logLevel)
    debug_handler.addFilter(lambda x: x.levelno >= logging.DEBUG)
    error_handler.addFilter(lambda x: x.levelno >= logging.WARN)

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
        postgres_handler = SpiderFootPostgresLogHandler(opts)
        postgres_handler.setLevel(logLevel)
        postgres_handler.setFormatter(log_format)
        handlers.append(postgres_handler)
    spiderFootLogListener = QueueListener(loggingQueue, *handlers)
    spiderFootLogListener.start()
    atexit.register(stop_listener, spiderFootLogListener)
    return spiderFootLogListener


def logWorkerSetup(loggingQueue) -> 'logging.Logger':
    """Root SpiderFoot logger.

    Args:
        loggingQueue (Queue): TBD

    Returns:
        logging.Logger: Logger
    """
    log = logging.getLogger("spiderfoot")
    # Don't do this more than once
    if len(log.handlers) == 0:
        log.setLevel(logging.DEBUG)
        queue_handler = QueueHandler(loggingQueue)
        log.addHandler(queue_handler)
    return log


def stop_listener(listener: 'logging.handlers.QueueListener') -> None:
    """TBD.

    Args:
        listener: (logging.handlers.QueueListener): TBD
    """
    with suppress(Exception):
        listener.stop()
