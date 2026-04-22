# Postgres Storage Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SQLite with Postgres-only persistence. `spiderfoot/db.py` + `spiderfoot/logger.py` rewritten. Alembic scaffolding with a `V001__initial_schema` migration runs on `sf.py` startup. `testcontainers-python` drives the test suite. Hard cut — no SQLite left.

**Architecture:** 6 tasks. The biggest (Task 3) is atomic: port `db.py` + `logger.py` + add `conftest.py` + refactor every test call-site in one commit. Tasks 1 & 2 stage dependencies + migrations without breaking anything. Task 4 wires Alembic into `sf.py` startup. Tasks 5 & 6 cover the Playwright fixture + Dockerfile + docs.

**Tech Stack:** Python 3.12 + `psycopg2-binary` + `alembic` + `testcontainers[postgres]`; Postgres 16 (via Docker + CloudNativePG).

**Spec:** `docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md`.

---

## File Structure

### Backend
- **Modify** `requirements.txt` — add `psycopg2-binary`, `alembic`, `testcontainers[postgres]`.
- **Create** `docker-compose.yml` at repo root — dev Postgres 16 service.
- **Create** `alembic.ini` at repo root.
- **Create** `alembic/env.py` — standard Alembic scaffolding.
- **Create** `alembic/versions/V001__initial_schema.py` — raw-SQL migration creating 7 tables + 8 indexes.
- **Create** `spiderfoot/migrations.py` — `run_alembic_upgrade(url)` helper.
- **Rewrite** `spiderfoot/db.py` — psycopg2 + `%s` placeholders + `ON CONFLICT` upserts; drop all `sqlite3` imports; drop the inline DDL path (Alembic owns DDL).
- **Rewrite** `spiderfoot/logger.py` — `SpiderFootSqliteLogHandler` → `SpiderFootPostgresLogHandler`.
- **Modify** `sf.py` — call `run_alembic_upgrade(url)` on startup; require `SPIDERFOOT_DATABASE_URL` env; drop SQLite file-path logic.
- **Modify** `sfscan.py` — update logger import if it references `SpiderFootSqliteLogHandler`.

### Tests
- **Create** `conftest.py` at repo root — session-scoped `postgres_url` + autouse `truncate_all_tables` fixtures.
- **Modify** existing test files — every `SpiderFootDb({"__database": path})` call-site refactored to pick up the URL from env. Big mechanical sweep across `test/unit/` + `test/integration/`.
- **Create** `test/unit/test_alembic_migrations.py` — 3 tests (upgrade, downgrade, history).

### Playwright
- **Modify** `webui/tests/e2e/fixtures/seed_db.py` — write to Postgres via psycopg2 instead of SQLite.
- **Modify** `webui/playwright.config.ts` — webServer starts docker-compose postgres before seed + sf.py.

### Docker
- **Modify** `Dockerfile` — build stage adds `libpq-dev gcc`; runtime stage adds `libpq5`.

### Docs
- **Modify** `CLAUDE.md` — "Running locally" section documenting docker-compose + URL env var.
- **Modify** `docs/superpowers/BACKLOG.md` — mark Postgres migration shipped.

---

## Context for the implementer

- **Branch:** master, direct commits. HEAD is `0d922ddc` (this milestone's spec commit).
- **Baseline:** 71 Vitest + 16 Playwright + flake8 clean + **1470 pytest** + 34 skipped.
- **Read the spec first:** `docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md`. Key decisions: hard cut, testcontainers for tests, Alembic for migrations, raw SQL port (no SQLAlchemy).
- **`spiderfoot/db.py`** is 1630 lines / 34 methods / 91 `?` placeholders / 7 tables + 8 indexes. Key SQLite-isms to translate:
  - `?` → `%s`
  - `INSERT OR REPLACE INTO ... VALUES (...)` → `INSERT INTO ... VALUES (...) ON CONFLICT (<pk_col>) DO UPDATE SET col1=EXCLUDED.col1, col2=EXCLUDED.col2, ...`
  - `INSERT OR IGNORE INTO ...` → `INSERT INTO ... ON CONFLICT DO NOTHING`
  - `PRAGMA foreign_keys = ON` — delete (Postgres always enforces FKs)
  - `rowid` — none in this schema
  - Datetime: integer-millisecond epochs stay `BIGINT` in Postgres
- **Connection model:** one `psycopg2.connect(url)` per `SpiderFootDb` instance. No shared pool. Each scan-process already creates its own SpiderFootDb; each CherryPy handler instantiates on-demand.
- **Environment variables:**
  - `SPIDERFOOT_DATABASE_URL` — required at startup. Format: `postgresql://user:pass@host:5432/dbname`.
  - `SPIDERFOOT_LOGS` / `SPIDERFOOT_CACHE` / `SPIDERFOOT_LOG_FORMAT` / `SPIDERFOOT_LOG_FILES` — unchanged.
  - `SPIDERFOOT_DATA` — deprecated; no longer controls database path. Keep in CLAUDE.md only for the file-cache path if still used elsewhere.
- **pybreaker** commit (`05157f81`) landed last milestone; no interaction with this work.
- **Playwright fixture** currently creates a SQLite file via `SpiderFootDb({"__database": tmppath}, init=True)`. Task 5 rewrites that; before that, the Playwright suite will fail until the rewrite lands.

---

## Task 1: Dependencies + docker-compose

**Files:**
- Modify: `requirements.txt`.
- Create: `docker-compose.yml` at repo root.

### Step 1: Add dependencies to `requirements.txt`

Open `/Users/olahjort/Projects/OhDeere/spiderfoot/requirements.txt`. Append (matching the file's existing pin-range style):

```
psycopg2-binary>=2.9,<3
alembic>=1.13,<2
testcontainers[postgres]>=4.0,<5
```

### Step 2: Install locally

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
pip3 install -r requirements.txt
```

Verify all three imports:

```bash
python3 -c "import psycopg2; import alembic; from testcontainers.postgres import PostgresContainer"
```

No import errors = pass.

### Step 3: Create `docker-compose.yml` at repo root

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: spiderfoot
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: spiderfoot
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - spiderfoot-pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U spiderfoot -d spiderfoot"]
      interval: 2s
      timeout: 2s
      retries: 30

volumes:
  spiderfoot-pg:
```

### Step 4: Spin up the dev postgres + verify

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U spiderfoot -d spiderfoot
```

Expected: `accepting connections`.

Leave the container running for subsequent tasks.

### Step 5: Run pytest — confirm baseline

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1470 passed, 34 skipped** — no code changes yet.

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add requirements.txt docker-compose.yml
git commit -m "$(cat <<'EOF'
postgres-migration: add deps + docker-compose

Prep step for the Postgres storage lift. Adds runtime deps
(psycopg2-binary, alembic) and test-time deps
(testcontainers[postgres]) with pinned ranges matching the
file's existing style.

docker-compose.yml at repo root provides a dev Postgres 16
service with a healthcheck. `docker compose up -d postgres`
plus `SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@
localhost:5432/spiderfoot` is the dev-loop setup until
subsequent tasks wire everything together.

No code changes yet — baseline pytest (1470/34) unchanged.

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Alembic scaffold + V001 initial schema + migrations helper

**Files:**
- Create: `alembic.ini` at repo root.
- Create: `alembic/env.py`.
- Create: `alembic/script.py.mako` (Alembic template for future revisions).
- Create: `alembic/versions/V001__initial_schema.py`.
- Create: `spiderfoot/migrations.py`.

### Step 1: Generate the Alembic scaffold (one-time)

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
alembic init alembic
```

This creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and an empty `alembic/versions/`.

### Step 2: Configure `alembic.ini`

Open `alembic.ini`. Find the `sqlalchemy.url` line (near line 60-ish). Replace with a placeholder that `env.py` overrides:

```ini
# Set at runtime via env.py from SPIDERFOOT_DATABASE_URL.
sqlalchemy.url = 
```

Find the `file_template` line (near line 10) and set it to match our `V<n>__<name>` convention:

```ini
file_template = V%%(rev)s__%%(slug)s
```

Leave other defaults. The `[alembic]` section's `script_location` should be `alembic` (default).

### Step 3: Configure `alembic/env.py`

Replace the generated `alembic/env.py` with a minimal version that reads the URL from the environment:

```python
"""Alembic env — reads Postgres URL from SPIDERFOOT_DATABASE_URL."""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
fileConfig_fn = getattr(context, 'fileConfig', None)
if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

DATABASE_URL = os.environ.get("SPIDERFOOT_DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "SPIDERFOOT_DATABASE_URL is not set — Alembic requires it"
    )
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = None  # raw-SQL migrations; no SQLAlchemy model autogenerate


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Step 4: Create `alembic/versions/V001__initial_schema.py`

```python
"""Initial SpiderFoot schema (7 tables + 8 indexes).

Revision ID: V001
Revises:
Create Date: 2026-04-20
"""
from alembic import op

revision = "V001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tbl_event_types (
            event       VARCHAR NOT NULL PRIMARY KEY,
            event_descr VARCHAR NOT NULL,
            event_raw   INTEGER NOT NULL DEFAULT 0,
            event_type  VARCHAR NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE tbl_config (
            scope VARCHAR NOT NULL,
            opt   VARCHAR NOT NULL,
            val   VARCHAR NOT NULL,
            PRIMARY KEY (scope, opt)
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_instance (
            guid           VARCHAR NOT NULL PRIMARY KEY,
            name           VARCHAR NOT NULL,
            seed_target    VARCHAR NOT NULL,
            created        BIGINT DEFAULT 0,
            started        BIGINT DEFAULT 0,
            ended          BIGINT DEFAULT 0,
            status         VARCHAR NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_log (
            scan_instance_id VARCHAR NOT NULL REFERENCES tbl_scan_instance(guid),
            generated        BIGINT NOT NULL,
            component        VARCHAR,
            type             VARCHAR NOT NULL,
            message          VARCHAR
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_config (
            scan_instance_id VARCHAR NOT NULL REFERENCES tbl_scan_instance(guid),
            component        VARCHAR NOT NULL,
            opt              VARCHAR NOT NULL,
            val              VARCHAR NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_results (
            scan_instance_id   VARCHAR NOT NULL REFERENCES tbl_scan_instance(guid),
            hash               VARCHAR NOT NULL,
            type               VARCHAR NOT NULL REFERENCES tbl_event_types(event),
            generated          BIGINT NOT NULL,
            confidence         INTEGER NOT NULL DEFAULT 100,
            visibility         INTEGER NOT NULL DEFAULT 100,
            risk               INTEGER NOT NULL DEFAULT 0,
            module             VARCHAR NOT NULL,
            data               VARCHAR,
            false_positive     INTEGER NOT NULL DEFAULT 0,
            source_event_hash  VARCHAR DEFAULT 'ROOT'
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_correlation_results (
            id               VARCHAR NOT NULL PRIMARY KEY,
            scan_instance_id VARCHAR NOT NULL REFERENCES tbl_scan_instance(guid),
            title            VARCHAR NOT NULL,
            rule_risk        VARCHAR NOT NULL,
            rule_id          VARCHAR NOT NULL,
            rule_name        VARCHAR NOT NULL,
            rule_descr       VARCHAR NOT NULL,
            rule_logic       VARCHAR NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE tbl_scan_correlation_results_events (
            correlation_id VARCHAR NOT NULL REFERENCES tbl_scan_correlation_results(id),
            event_hash     VARCHAR NOT NULL
        )
    """)

    # Indexes
    op.execute("CREATE INDEX idx_scan_results_id ON tbl_scan_results (scan_instance_id)")
    op.execute("CREATE INDEX idx_scan_results_type ON tbl_scan_results (scan_instance_id, type)")
    op.execute("CREATE INDEX idx_scan_results_hash ON tbl_scan_results (scan_instance_id, hash)")
    op.execute("CREATE INDEX idx_scan_results_module ON tbl_scan_results (scan_instance_id, module)")
    op.execute("CREATE INDEX idx_scan_results_srchash ON tbl_scan_results (scan_instance_id, source_event_hash)")
    op.execute("CREATE INDEX idx_scan_logs ON tbl_scan_log (scan_instance_id)")
    op.execute("CREATE INDEX idx_scan_correlation ON tbl_scan_correlation_results (scan_instance_id, id)")
    op.execute("CREATE INDEX idx_scan_correlation_events ON tbl_scan_correlation_results_events (correlation_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tbl_scan_correlation_results_events")
    op.execute("DROP TABLE IF EXISTS tbl_scan_correlation_results")
    op.execute("DROP TABLE IF EXISTS tbl_scan_results")
    op.execute("DROP TABLE IF EXISTS tbl_scan_config")
    op.execute("DROP TABLE IF EXISTS tbl_scan_log")
    op.execute("DROP TABLE IF EXISTS tbl_scan_instance")
    op.execute("DROP TABLE IF EXISTS tbl_config")
    op.execute("DROP TABLE IF EXISTS tbl_event_types")
```

**Before finalizing:** open `/Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/db.py` and compare the existing `CREATE TABLE` statements against the migration above. Faithfully port every column name, type, nullability, default, and FK. If any deviation surfaces (e.g. a column I missed, a different default), update the migration to match the current schema exactly — the goal is byte-for-byte compatibility.

### Step 5: Create `spiderfoot/migrations.py`

```python
"""Thin helper for running Alembic migrations from Python."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def _config(database_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    # env.py reads SPIDERFOOT_DATABASE_URL; propagate for consistency.
    os.environ["SPIDERFOOT_DATABASE_URL"] = database_url
    return cfg


def run_alembic_upgrade(database_url: str, revision: str = "head") -> None:
    """Run alembic upgrade <revision> against the given URL."""
    command.upgrade(_config(database_url), revision)


def run_alembic_downgrade(database_url: str, revision: str = "base") -> None:
    """Run alembic downgrade <revision> (default: tear everything down)."""
    command.downgrade(_config(database_url), revision)
```

### Step 6: Verify Alembic works against the dev Postgres

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
export SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot
python3 -c "
from spiderfoot.migrations import run_alembic_upgrade, run_alembic_downgrade
run_alembic_upgrade('$SPIDERFOOT_DATABASE_URL')
print('upgrade ok')
"
```

Expected: `upgrade ok`.

Verify tables via psql:

```bash
docker compose exec -T postgres psql -U spiderfoot -d spiderfoot -c '\dt'
```

Expected: 7 `tbl_*` tables plus `alembic_version`.

Clean up:

```bash
python3 -c "
from spiderfoot.migrations import run_alembic_downgrade
run_alembic_downgrade('$SPIDERFOOT_DATABASE_URL')
print('downgrade ok')
"
```

Expected: `downgrade ok`. Verify tables are gone (`\dt` shows only `alembic_version` or nothing).

### Step 7: Run pytest — confirm baseline unchanged

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1470 passed, 34 skipped** — the DB code is still SQLite; Alembic is not invoked by any test yet.

### Step 8: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add alembic.ini alembic/ spiderfoot/migrations.py
git commit -m "$(cat <<'EOF'
postgres-migration: Alembic scaffold + V001 initial schema

Adds Alembic configuration (alembic.ini, alembic/env.py,
alembic/script.py.mako) and the V001__initial_schema migration
that creates the 7 tables + 8 indexes currently built inline by
SpiderFootDb. File_template = V%%(rev)s__%%(slug)s matches the
convention in our specs.

env.py reads SPIDERFOOT_DATABASE_URL at module-import time and
fails loudly if unset — callers (sf.py, tests) populate the env
before invoking Alembic.

spiderfoot/migrations.py wraps alembic.command.upgrade/downgrade
for programmatic use — sf.py startup and test conftest both
call run_alembic_upgrade(url) to ensure the schema exists before
any SpiderFootDb work happens.

Verified against the dev docker-compose postgres: upgrade creates
all 7 tables + 8 indexes; downgrade cleanly drops them.

No code paths touching sqlite yet changed — pytest still 1470/34.

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Port `db.py` + `logger.py` + conftest.py + refactor test call-sites (atomic swap)

> **This is the biggest task in the milestone.** Expect a multi-file diff, careful SQL audit, and a full pytest run to confirm green at the end. Land in one commit so master never has mixed SQLite/Postgres state.

**Files:**
- Rewrite: `spiderfoot/db.py`.
- Rewrite: `spiderfoot/logger.py`.
- Create: `conftest.py` at repo root.
- Modify: `sfscan.py` — update logger import if needed.
- Modify: test files under `test/unit/` and `test/integration/` — refactor `SpiderFootDb({"__database": path})` calls to use env var.

### Step 1: Read the current `spiderfoot/db.py`

```bash
wc -l /Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/db.py
grep -n "^    def " /Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/db.py
```

Expected: 1630 lines, 34 method definitions. Read each method's SQL — build a mental map of every `?`, every `INSERT OR REPLACE`, every `INSERT OR IGNORE`. There are no `rowid` references or other SQLite-exclusive idioms, but verify during reading.

### Step 2: Rewrite `spiderfoot/db.py`

At the top:

```python
"""SpiderFoot database layer (Postgres via psycopg2)."""
import contextlib
import hashlib
import os
import random
import threading
import time
import typing
from typing import Optional, Union

import psycopg2
import psycopg2.extras

from spiderfoot import SpiderFootEvent
```

The main `SpiderFootDb` class:

```python
class SpiderFootDb:

    def __init__(self, opts: dict, init: bool = False) -> None:
        self.dbhLock = threading.RLock()
        self.opts = opts
        url = opts.get("__database") or os.environ.get("SPIDERFOOT_DATABASE_URL", "")
        if not url:
            raise ValueError(
                "SpiderFootDb requires __database (a Postgres URL) or "
                "SPIDERFOOT_DATABASE_URL set in the environment"
            )
        # psycopg2 connect_timeout is in seconds.
        self.conn = psycopg2.connect(url, connect_timeout=10)
        self.conn.autocommit = False
        self.dbh = self.conn.cursor()
        # Schema creation is Alembic's job; ``init`` is now a no-op here.
        if init:
            # Kept as a no-op so legacy callers that pass init=True don't
            # need code changes. Alembic is run from sf.py / conftest.
            pass
```

Then each method's SQL gets transformed:

- `?` → `%s`
- `INSERT OR REPLACE INTO tbl_config VALUES (?, ?, ?)` →
  ```python
  self.dbh.execute(
      "INSERT INTO tbl_config (scope, opt, val) VALUES (%s, %s, %s) "
      "ON CONFLICT (scope, opt) DO UPDATE SET val=EXCLUDED.val",
      (scope, opt, val),
  )
  ```
- `INSERT OR IGNORE INTO tbl_event_types VALUES (?, ?, ?, ?)` →
  ```python
  self.dbh.execute(
      "INSERT INTO tbl_event_types (event, event_descr, event_raw, event_type) "
      "VALUES (%s, %s, %s, %s) ON CONFLICT (event) DO NOTHING",
      (event, event_descr, event_raw, event_type),
  )
  ```

Commit handling: every write-method wraps in try/except and commits/rollbacks per-call (matches existing SQLite behavior where the code commits after each statement). psycopg2 requires explicit `.commit()` — the existing code's pattern is to call `self.conn.commit()` after write statements; preserve that exactly.

Fetch methods: replace `self.dbh.fetchall()` → continues working identically with psycopg2. Row tuples come back as `list[tuple[Any, ...]]` — same shape as sqlite3.

Close method:

```python
def close(self) -> None:
    with self.dbhLock:
        self.dbh.close()
        self.conn.close()
```

Every call-site that constructed a `SpiderFootDb({"__database": path})` continues to work because `__database` now carries a URL. Consumer modules unchanged.

### Step 3: Rewrite `spiderfoot/logger.py`

Locate the `SpiderFootSqliteLogHandler` class. Rename to `SpiderFootPostgresLogHandler`. The structural change:

- Import `psycopg2` instead of `sqlite3`.
- Connection: open on first emit (lazy) against `SPIDERFOOT_DATABASE_URL`.
- `emit(record)` method writes one row to `tbl_scan_log` via an INSERT with `%s` placeholders.
- Close connection in the handler's `close()` method.

Before the rename lands, grep for other references to the old name:

```bash
grep -rn "SpiderFootSqliteLogHandler" /Users/olahjort/Projects/OhDeere/spiderfoot --include="*.py"
```

Update every caller. Likely 1-2 references in `sfscan.py` and/or `sf.py`.

### Step 4: Create `conftest.py` at repo root

```python
"""Pytest configuration — testcontainers-powered Postgres."""
import os

import psycopg2
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url():
    """Spin up a session-scoped Postgres 16 container + run Alembic upgrade."""
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://", 1,
        )
        os.environ["SPIDERFOOT_DATABASE_URL"] = url
        from spiderfoot.migrations import run_alembic_upgrade
        run_alembic_upgrade(url)
        yield url


@pytest.fixture(autouse=True)
def truncate_all_tables(postgres_url):
    """Fast inter-test isolation — TRUNCATE beats DROP/CREATE."""
    yield
    conn = psycopg2.connect(postgres_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE
                    tbl_scan_correlation_results_events,
                    tbl_scan_correlation_results,
                    tbl_scan_results,
                    tbl_scan_log,
                    tbl_scan_config,
                    tbl_scan_instance,
                    tbl_config,
                    tbl_event_types
                RESTART IDENTITY CASCADE
            """)
        conn.commit()
    finally:
        conn.close()
```

(Note the `yield` is before the TRUNCATE — we want tables clean *after* each test, not before, so the first test starts with a freshly-created empty schema.)

### Step 5: Refactor test call-sites

```bash
grep -rn '"__database":' /Users/olahjort/Projects/OhDeere/spiderfoot/test/ --include="*.py" | head -20
```

Every match needs an audit. Two patterns:

1. **Tests constructing their own DB**: `SpiderFootDb({"__database": tmppath}, init=True)`. Since `__database` is now a URL, these need to read from the fixture. Simplest refactor: change `tmppath` to `os.environ["SPIDERFOOT_DATABASE_URL"]`.
   
2. **Tests reading `spiderfoot.test.db`** for isolation: the fixture pattern via `test/conftest.py` (pre-existing). Update those fixtures to inject the `postgres_url` fixture.

Do this systematically. Probably ~50-100 test functions touch the DB. A shell oneliner sed:

```bash
# List the files first, then do a manual sed per file reviewing results.
grep -rln '"__database":' /Users/olahjort/Projects/OhDeere/spiderfoot/test/ --include="*.py"
```

Read each file, update idiomatically. Don't blind-sed: some tests may assert SQLite-specific behavior (e.g. file exists, specific error messages) — those need deleting or rewriting.

### Step 6: Update `test/conftest.py` (if it exists)

There's likely a `test/conftest.py` with `default_options` / `web_default_options` fixtures that set `__database` to a tmppath. Update those to use the env var set by the session-scoped fixture.

### Step 7: Run pytest — expect green

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1470 passed, 34 skipped**.

If failures:
- FK violations → a test inserts a scan_result before its scan_instance exists. Check TRUNCATE ordering.
- "type json" errors → a column that was TEXT in SQLite is now something else in Postgres. Verify the V001 migration matches.
- `INSERT OR REPLACE` conversions — verify every converted statement names the correct conflict column(s).

Iterate until all 1470 tests pass.

### Step 8: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add spiderfoot/db.py spiderfoot/logger.py sfscan.py sf.py conftest.py test/
git commit -m "$(cat <<'EOF'
postgres-migration: atomic db.py + logger.py + conftest swap

Biggest commit of the Postgres lift:

- spiderfoot/db.py rewritten for psycopg2. 34 methods ported;
  91 ? placeholders → %s; every INSERT OR REPLACE converted to
  INSERT ... ON CONFLICT (<pk>) DO UPDATE; every INSERT OR IGNORE
  converted to INSERT ... ON CONFLICT DO NOTHING. No sqlite3
  imports. Schema DDL deleted (Alembic owns it now); init=True
  is a no-op kept for caller compat.
- spiderfoot/logger.py — SpiderFootSqliteLogHandler renamed to
  SpiderFootPostgresLogHandler; same tbl_scan_log row shape,
  same emit() flow.
- conftest.py (new, repo root) — session-scoped postgres_url
  fixture via testcontainers; autouse truncate_all_tables
  fixture for per-test isolation.
- test/* — ~N test call-sites refactored to read
  SPIDERFOOT_DATABASE_URL from env (populated by the fixture).
  A handful of SQLite-specific tests removed.

pytest: 1470/34 maintained across the swap. All existing tests
pass against testcontainers Postgres unchanged save for the
path→URL refactor.

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

(Replace `~N` in the commit message with the actual count of edited test files.)

---

## Task 4: `sf.py` Alembic-on-startup + env-var handling

**Files:**
- Modify: `sf.py` — require SPIDERFOOT_DATABASE_URL; call run_alembic_upgrade before CherryPy start.

### Step 1: Locate the DB-path setup in sf.py

```bash
grep -n "SPIDERFOOT_DATA\|__database\|dataPath" /Users/olahjort/Projects/OhDeere/spiderfoot/sf.py | head -10
```

The existing code builds a SQLite file path from `SPIDERFOOT_DATA`. Replace that with the env-var URL.

### Step 2: Update startup logic

Near the top of `start_web_server` (or wherever the DB is first touched), add:

```python
database_url = os.environ.get("SPIDERFOOT_DATABASE_URL")
if not database_url:
    log.critical(
        "SPIDERFOOT_DATABASE_URL is required. Start the dev Postgres with "
        "`docker compose up -d postgres` then set "
        "SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot"
    )
    sys.exit(1)

# Run Alembic migrations before any DB work happens.
log.info("Running Alembic migrations ...")
from spiderfoot.migrations import run_alembic_upgrade
try:
    run_alembic_upgrade(database_url)
except Exception as e:
    log.critical(f"Alembic upgrade failed: {e}")
    sys.exit(1)
log.info("Alembic migrations up-to-date.")

# Propagate the URL to any caller that still reads opts["__database"].
sfConfig["__database"] = database_url
```

Remove the old SQLite path logic. Keep the rest of the startup sequence.

### Step 3: Remove SPIDERFOOT_DATA references that pointed at the SQLite file

`SPIDERFOOT_DATA` may still be used elsewhere (e.g. cache directory). Audit:

```bash
grep -n "SPIDERFOOT_DATA" /Users/olahjort/Projects/OhDeere/spiderfoot/sf.py
```

Keep references that relate to *other* data (cache, etc.). Delete only the DB-file construction.

### Step 4: Manual smoke test

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
docker compose up -d postgres
export SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot
python3 ./sf.py -l 127.0.0.1:5001 &
sleep 5
curl -s http://127.0.0.1:5001/ | head -1
curl -s http://127.0.0.1:5001/scanlist | head -1
kill %1
```

Expected: The `/` endpoint returns the SPA shell, `/scanlist` returns `[]`. Verify via psql that the tables exist:

```bash
docker compose exec -T postgres psql -U spiderfoot -d spiderfoot -c '\dt'
```

### Step 5: Run pytest

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1470 passed, 34 skipped**.

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sf.py
git commit -m "$(cat <<'EOF'
postgres-migration: sf.py runs Alembic on startup; requires URL

sf.py startup sequence now:

1. Reads SPIDERFOOT_DATABASE_URL from env; exits with a
   readable critical log if unset (dev reminder to docker-compose
   + export).
2. Runs Alembic migrations to HEAD before any DB work happens.
   Hard-fails if upgrade fails — k8s restart policy handles
   recovery; better than a partial schema.
3. Propagates the URL into sfConfig["__database"] so downstream
   SpiderFootDb instantiations pick it up via the existing
   opts["__database"] path.

SQLite file-path construction removed. SPIDERFOOT_DATA still
exists for the cache-path usage (unchanged).

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Playwright fixture + Dockerfile

**Files:**
- Modify: `webui/tests/e2e/fixtures/seed_db.py` — write to Postgres.
- Modify: `webui/playwright.config.ts` — webServer starts docker-compose first.
- Modify: `Dockerfile` — add libpq build + runtime deps.

### Step 1: Rewrite `seed_db.py`

Current version creates a SQLite file. Rewrite to write to Postgres. Read the current structure first:

```bash
cat /Users/olahjort/Projects/OhDeere/spiderfoot/webui/tests/e2e/fixtures/seed_db.py
```

The script currently takes a path arg; rewrite it to take a URL (or read `SPIDERFOOT_DATABASE_URL`). Modes (`--empty`, `--clear`, `--reseed`) stay — `--clear` and `--reseed` use TRUNCATE; `--empty` / `default` run the same SpiderFootDb insert pattern but via psycopg2.

Skeleton:

```python
#!/usr/bin/env python3
"""Seed the Playwright e2e Postgres with deterministic scan data.

Modes:
  default    — upsert a fixed set of scans (e.g. monthly-recon).
  --empty    — ensure the schema exists; no rows.
  --clear    — TRUNCATE all tables; no rows.
  --reseed   — --clear + default seed.
"""
import os
import sys
from spiderfoot.migrations import run_alembic_upgrade
from spiderfoot.db import SpiderFootDb
# ... construct scans and INSERT via psycopg2 or SpiderFootDb
```

Use `os.environ["SPIDERFOOT_DATABASE_URL"]` as the connection URL.

### Step 2: Update `webui/playwright.config.ts`

The webServer command currently:

```
rm -rf ${SPIDERFOOT_DATA} && mkdir -p ${SPIDERFOOT_DATA} && python3 ${SEED_SCRIPT} ${SPIDERFOOT_DATA}/spiderfoot.db && SPIDERFOOT_DATA=${SPIDERFOOT_DATA} python3 ${REPO_ROOT}/sf.py -l 127.0.0.1:5990
```

Rewrite to:

```
docker compose up -d postgres \
  && (for i in 1 2 3 4 5 6 7 8 9 10; do docker compose exec -T postgres pg_isready -U spiderfoot -d spiderfoot && break || sleep 1; done) \
  && SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot python3 ${SEED_SCRIPT} --reseed \
  && SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot python3 ${REPO_ROOT}/sf.py -l 127.0.0.1:5990
```

Running `docker compose up -d postgres` is idempotent (starts if not running; no-op if already up).

### Step 3: Update `Dockerfile`

Find the `build` stage. Add to `apt-get install`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc git curl swig \
    libssl-dev libffi-dev libxslt1-dev libxml2-dev \
    libjpeg-dev zlib1g-dev libopenjp2-7-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

Find the runtime stage. Add to its `apt-get install`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxslt1.1 libxml2 libjpeg62-turbo zlib1g libopenjp2-7 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd spiderfoot \
    ...
```

### Step 4: Docker build smoke test

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
docker build -t sf-pg-verify . 2>&1 | tail -10
```

Expected: build succeeds. Inspect the image for psycopg2:

```bash
docker run --rm sf-pg-verify python3 -c "import psycopg2; print(psycopg2.__version__)"
```

Cleanup:

```bash
docker rmi sf-pg-verify
```

### Step 5: Run `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -20
```

Expected: webui build + 71 Vitest + 16 Playwright + flake8 clean + **1470 pytest** / 34 skipped. Playwright now drives against the dev Postgres via docker-compose.

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/tests/e2e/fixtures/seed_db.py webui/playwright.config.ts Dockerfile
git commit -m "$(cat <<'EOF'
postgres-migration: Playwright fixture + Dockerfile libpq

Playwright e2e now runs against the dev docker-compose postgres.
seed_db.py rewritten to use psycopg2 + SPIDERFOOT_DATABASE_URL;
modes unchanged (default / --empty / --clear / --reseed).

playwright.config.ts webServer command:
1. docker compose up -d postgres (idempotent)
2. poll pg_isready for up to 10s
3. run seed_db.py --reseed against the container
4. start sf.py

Dockerfile build stage adds libpq-dev (psycopg2 build); runtime
stage adds libpq5 (runtime shared lib). No JVM.

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs + final verify

**Files:**
- Modify: `CLAUDE.md`.
- Modify: `docs/superpowers/BACKLOG.md`.

### Step 1: Update `CLAUDE.md`

Find the "Common commands" section's first paragraph. Update the "Run the web UI" description:

Before:
```
Run the web UI (default dev target):

```
python3 ./sf.py -l 127.0.0.1:5001
```
```

After:
```
Run the web UI (default dev target). Requires Postgres:

```
docker compose up -d postgres
export SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot
python3 ./sf.py -l 127.0.0.1:5001
```
```

Add a new top-level section "Database" after "Common commands", briefly:

```
## Database

SpiderFoot stores all scan state in Postgres. The SQLite backend was retired in the Postgres migration milestone. Local dev uses `docker-compose.yml` at the repo root (Postgres 16 on port 5432). Cluster deployments point at CloudNativePG via a sealed secret (`SPIDERFOOT_DATABASE_URL`).

Schema is managed by Alembic (`alembic/versions/`). `sf.py` runs `alembic upgrade head` on startup. New migrations land as `alembic/versions/V<n>__<name>.py` files — pure-Python, raw-SQL via `op.execute(...)`. No SQLAlchemy models. `spiderfoot/migrations.py` wraps the Alembic commands for programmatic use.
```

### Step 2: Update `docs/superpowers/BACKLOG.md`

Find the Postgres migration item. Move to shipped. Representative phrasing:

```
- **Postgres storage migration (2026-04-20)** — SQLite retired; Postgres-only via `psycopg2-binary` + Alembic. Hard cut. testcontainers-python session-scoped fixture drives the pytest suite; docker-compose Postgres 16 for local dev; CloudNativePG in cluster via `SPIDERFOOT_DATABASE_URL`. 1470 pytest unchanged. Spec: `docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md`. Follow-ups: JSONB on RAW_RIR_DATA (V002), shared psycopg2 pool for webui, scan-concurrency refactor.
```

### Step 3: Final `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 71 Vitest + 16 Playwright + flake8 clean + **1470 pytest** / 34 skipped.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — Postgres storage migration shipped

CLAUDE.md adds a Database section pointing at docker-compose for
local dev + CloudNativePG for cluster deployment; dev-loop
instructions updated to include the new env var + compose step.

BACKLOG.md marks the Postgres migration shipped with a reference
to the spec + the three near-term follow-ups (JSONB, pool,
scan-concurrency).

Refs docs/superpowers/specs/2026-04-20-postgres-storage-migration-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone summary

Report:
- 6 commits (plus 2 docs commits for spec + plan).
- Postgres migration shipped end-to-end.
- Final test counts.
- Known follow-ups: JSONB on RAW_RIR_DATA, shared pool for webui, scan-concurrency refactor.
- Cluster deploy requires a new sealed secret for SPIDERFOOT_DATABASE_URL — tracked ops-side.

## Report Format

- **Status:** DONE | BLOCKED
- Final `./test/run` one-line summary
- Commit SHA
- Milestone summary
