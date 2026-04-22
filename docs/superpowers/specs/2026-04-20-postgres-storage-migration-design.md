# Postgres Storage Migration — Design

**Date:** 2026-04-20
**Scope:** Replace SpiderFoot's SQLite storage (`spiderfoot/db.py` + `SpiderFootSqliteLogHandler`) with Postgres-only persistence, backed by Alembic versioned migrations. Hard cut — no SQLite paths remain. Targeted at the OhDeere k3s cluster's CloudNativePG instance; local dev uses a `docker-compose` Postgres container.

---

## Goal

Ship SpiderFoot on Postgres as the only supported backend. Match the current SQLite feature set exactly in this milestone — same schema, same query surface, same `SpiderFootDb` API. Concurrency improvements, JSONB, and connection pooling are explicitly deferred to follow-up milestones so this scope stays focused on "correctness-preserving backend swap."

---

## Architecture

### Hard cut

No SQLite paths remain. The `SpiderFootDb` class no longer imports `sqlite3` and has no dual-backend dispatcher. Every call-site that previously passed `opts["__database"] = "/path/to/spiderfoot.db"` now passes a Postgres URL like `postgresql://user:pass@host:5432/dbname`. Most call-sites already source the value from `opts["__database"]` (which itself was previously populated from `SPIDERFOOT_DATA` in `sf.py`) — they keep working with zero change since only the *value* of that opt changes shape.

`SpiderFootDb.__init__` additionally reads `SPIDERFOOT_DATABASE_URL` from the environment if `opts["__database"]` is missing, so tests and dev invocations can rely on the env var directly.

### Query layer

Raw SQL with psycopg2. Port the 34 methods in `spiderfoot/db.py` using three mechanical transforms:

1. **Parameter style**: `?` → `%s`. psycopg2 uses pyformat / numeric paramstyles; `%s` is the safe universal choice.
2. **`INSERT OR REPLACE` → `INSERT ... ON CONFLICT (<pk>) DO UPDATE SET ...`.** Small number of occurrences — inspect each and write the explicit upsert.
3. **`INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`.** Simpler; constant 1-line swap per call-site.

Other SQLite-isms to audit:
- `rowid` references — confirmed absent from SpiderFoot's schema during brainstorming; all 7 tables have explicit PKs.
- Datetime handling — the codebase uses **integer millisecond epochs throughout**, stored as `INTEGER`. Postgres gets `BIGINT` columns; zero datetime-parsing surface change.
- `LIMIT N OFFSET M` — identical syntax in both backends; no change.
- `PRAGMA`s — the only one in use is `PRAGMA foreign_keys = ON` (SQLite off-by-default), which becomes a no-op against Postgres (FKs always enforced).

No SQLAlchemy (neither Core nor ORM). The raw-SQL style keeps the diff tight and merges upstream-mostly-cleanly (upstream will add `sqlite3`-specific changes; we'll conflict-resolve by dropping them from our fork).

### Connection model

One `psycopg2.connect(url)` per `SpiderFootDb` instance. The existing code creates one `SpiderFootDb` per consumer — each scan-process gets its own (via `multiprocessing.Process`), and the CherryPy webui main process creates them on-demand per handler call. Keep that model; no shared pool in this milestone.

If CherryPy's threaded request handling surfaces contention, add `psycopg2.pool.ThreadedConnectionPool` in a follow-up milestone (explicitly out of scope here).

### Schema management — Alembic

**Alembic runs on `sf.py` startup.** Before opening the first connection for actual work, `sf.py` calls `alembic upgrade head` programmatically (via the Alembic API, not a shell out). Fail loudly if the migration fails.

**Repository layout:**
- `alembic.ini` at repo root.
- `alembic/env.py` — standard Alembic scaffolding; configures the URL from `SPIDERFOOT_DATABASE_URL`.
- `alembic/versions/V001__initial_schema.py` — creates the 7 tables + 8 indexes currently built by `db.py:init`. Raw SQL via `op.execute(...)` — no SQLAlchemy model classes.

**Future migrations** go as new files `V002__<name>.py`. Example near-future candidates (all out of scope for this milestone):
- `V002__raw_rir_jsonb.py` — convert `tbl_scan_results.data` from TEXT to JSONB when the module is `RAW_RIR_DATA`.
- `V003__scan_config_index.py` — performance index once scan-config queries need one.

**Schema creation path in `db.py`:**
- `SpiderFootDb.__init__(opts, init=True)` no longer executes CREATE TABLE statements directly. The `init=True` flag becomes a signal to the higher-level startup code that Alembic should be run; the DDL lives in the Alembic migration.
- Tests that currently call `SpiderFootDb({"__database": tmppath}, init=True)` will be refactored to use the testcontainers fixture; the container starts with Alembic already upgraded.

### Logger

`SpiderFootSqliteLogHandler` in `spiderfoot/logger.py` writes per-scan log rows to `tbl_scan_log`. Rewrite as `SpiderFootPostgresLogHandler`:
- Same table, same row shape, same write path.
- `emit()` opens a short-lived psycopg2 connection (one INSERT per log record). No connection pool needed — log volume is modest and per-scan.
- Class name renamed in `spiderfoot/logger.py`; one import in `sf.py` / `sfscan.py` updated accordingly.

### Dev workflow

`docker-compose.yml` at repo root, new file:

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
volumes:
  spiderfoot-pg:
```

Dev loop:
```bash
docker compose up -d postgres
export SPIDERFOOT_DATABASE_URL=postgresql://spiderfoot:dev@localhost:5432/spiderfoot
python3 ./sf.py -l 127.0.0.1:5001
```

CLAUDE.md gains a "Running locally" note covering this.

### Test infrastructure

`testcontainers[postgres]` pinned in `requirements.txt`. New `conftest.py` at repo root:

```python
import os
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://", 1
        )
        os.environ["SPIDERFOOT_DATABASE_URL"] = url
        # Run alembic upgrade head against the container.
        from spiderfoot.migrations import run_alembic_upgrade
        run_alembic_upgrade(url)
        yield url

@pytest.fixture(autouse=True)
def truncate_all_tables(postgres_url):
    """Fast inter-test isolation — TRUNCATE beats DROP/CREATE."""
    import psycopg2
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
    yield
```

The existing tests call `SpiderFootDb({"__database": path})` — refactor those call-sites to read `os.environ["SPIDERFOOT_DATABASE_URL"]`. Some tests construct `SpiderFootDb` without explicit opts; they fall back to the env var. One sweeping refactor needs to land in the same commit as the backend swap or tests break en masse.

**Session-scoped container + per-test TRUNCATE** beats "container per test" on speed (one Postgres startup per pytest run vs one per test). TRUNCATE is fast on empty-ish tables.

### Milestone-1 Playwright fixture

`webui/tests/e2e/fixtures/seed_db.py` currently creates a SQLite file. Rewrite to:
1. Read `SPIDERFOOT_DATABASE_URL` from env (fallback: construct a docker-compose-style URL).
2. Run Alembic migrations programmatically.
3. Execute the existing INSERT statements against Postgres.

Playwright's webServer command in `playwright.config.ts` gains a `docker compose up -d postgres` step before the seed/launch sequence.

### Runtime Docker image

`Dockerfile` changes:
- Build stage: `apt-get install -y libpq-dev gcc` for compiling psycopg2 from source if no wheel is available (psycopg2-binary wheel usually works on Debian slim, but belt-and-braces).
- Runtime stage: `apt-get install -y libpq5` (the shared lib psycopg2 needs at runtime).
- No JVM; no Java; no Flyway — keeps the image slim.

### Kubernetes deployment

- Sealed secret creates `SPIDERFOOT_DATABASE_URL` pointing at `wimo-pg-rw.postgres:5432`.
- Deployment env block references the secret.
- CloudNativePG provisions the `spiderfoot` user + `spiderfoot` database in advance (one-time operator task).
- Alembic's first run on pod startup creates the schema in an empty database.

Detailed k8s manifests are out of scope for this spec — they live in the ops repo. This spec stops at "the container works against any Postgres you point it at."

---

## Dependencies

`requirements.txt` gains three new lines:

- `psycopg2-binary>=2.9,<3`  — runtime DB driver (binary wheel so no build-time libpq headers needed for most Linux distros)
- `alembic>=1.13,<2`         — migration tooling, runs at startup
- `testcontainers[postgres]>=4.0,<5` — dev-time test fixture. Keep in the same file rather than splitting into requirements-dev.txt; the testcontainers import is conftest-guarded so production environments without Docker don't trip it.

Total new runtime deps: psycopg2-binary + alembic. testcontainers is dev-only but listed for clarity.

`sqlite3` dependency is a stdlib module — no requirements.txt change needed on the SQLite side, but every `import sqlite3` across the codebase gets deleted.

---

## Testing

**Target: all 1470 existing pytest cases pass against testcontainers Postgres, unmodified save for fixture-path refactors.**

Specific test categories to audit during implementation:

1. **`test/unit/test_spiderfoot_db.py`** — the biggest block of db-focused tests. All test methods create a fresh DB, insert rows, query, assert. Refactor to use the shared `postgres_url` + `truncate_all_tables` fixtures.
2. **`test/integration/test_sfwebui.py`** — CherryPy handler tests. Already uses a session-scoped Postgres conceptually; just needs the URL env var populated.
3. **`test/unit/modules/test_sfp_*.py`** — most module tests instantiate a `SpiderFootDb` for the scan context; they pick up the env var automatically.

**Net pytest count after the milestone**: no change expected. 1470 passed + 34 skipped. Some SQLite-specific tests (e.g. PRAGMA-related, file-exists checks) may delete outright — documented in the plan.

### New test: Alembic sanity

`test/unit/test_alembic_migrations.py`:
- Assert `alembic upgrade head` on a fresh DB creates all 7 tables + 8 indexes.
- Assert `alembic downgrade base` on a populated DB cleanly drops everything.
- Assert `alembic history` shows V001 as the only revision (after the initial implementation; additions trivially extend).

---

## Rollout

**Single-milestone hard cut. No phased SQLite/Postgres coexistence.** The commit sequence:

1. Backend + dependencies + Alembic scaffolding + docker-compose + conftest — one big commit.
2. `db.py` rewrite (7 tables, 34 methods) — probably needs a second commit for reviewability, but functionally paired with the first.
3. `logger.py` rewrite (SpiderFootPostgresLogHandler) — one commit.
4. Test call-site refactor (pass URLs instead of paths) — one commit.
5. Dockerfile updates + Playwright seed_db.py + CLAUDE.md docs — final commit.

Target: **5-8 commits across 1-2 sessions**. The brainstorm + plan cycles each get their own commit as usual.

After the milestone lands on master, the k3s deployment needs a new sealed secret for `SPIDERFOOT_DATABASE_URL` and a CloudNativePG user + database provisioning — those are ops-side tasks tracked separately.

---

## Risks

- **psycopg2-binary wheel availability.** The wheel covers most Linux distros (amd64 + arm64) + macOS. If a target environment lacks it, the build falls back to source and needs `libpq-dev` + gcc. The Dockerfile already installs those in the build stage.
- **Alembic on startup.** If Alembic upgrade fails (e.g. version mismatch, connection refused), `sf.py` fails loudly and the pod restarts — which is fine; k8s handles it. Don't try to be clever about partial upgrades.
- **Test isolation via TRUNCATE.** `TRUNCATE ... RESTART IDENTITY CASCADE` resets sequences + ripples FK deletes. If any test relies on a specific auto-increment PK value, it'll surprise. Review the `test/unit/test_spiderfoot_db.py` tests during implementation — most use UUIDs for scan IDs, not auto-increment PKs, so impact is likely small.
- **testcontainers startup time.** A Postgres container cold-start takes 3-5 seconds. That's a one-time cost per pytest invocation — acceptable given `./test/run` takes 30+ seconds anyway. If it becomes painful in local dev, pytest-xdist's `--forked` can share the container across workers.
- **Concurrent pytest workers.** `pytest-xdist` with `-n auto` runs multiple workers. Each worker currently hits its own Postgres container via session-scoped fixture — but session scope is per-worker in xdist. Either all workers share one container (single container, per-worker schema) or each gets its own (more containers, simpler isolation). Start with "each worker its own" and measure.
- **`INSERT OR REPLACE` semantics.** `ON CONFLICT (col) DO UPDATE` requires a unique constraint on the conflict column. Audit each conversion — SQLite's `INSERT OR REPLACE` falls back to matching the full PK or any unique index; Postgres needs explicit column(s). Verify against the existing schema during implementation.
- **Alembic + testcontainers boot ordering.** The `postgres_url` fixture needs to run Alembic upgrade *before* yielding the URL. If `run_alembic_upgrade(url)` fails, the fixture raises and all tests skip — good. Make sure the upgrade is idempotent (it is by Alembic design).
- **Removing `sqlite3` imports and SpiderFootSqliteLogHandler class name**. Consumer modules that reach directly into `SpiderFootSqliteLogHandler` (there shouldn't be any outside `sfscan.py` / `sf.py`) need updating. Grep before landing.
- **CherryPy reload / multi-process signal handling.** SpiderFoot uses `multiprocessing.Process` for scans. Each process's psycopg2 connection is its own; no shared sockets. OK.
- **Upstream merge drift.** Our `db.py` will diverge from `smicallef/spiderfoot`'s. Acceptable cost — upstream has been stale for 2+ years per the CLAUDE.md note; no ongoing sync burden.

---

## Non-goals for this milestone

- **JSONB on `RAW_RIR_DATA`.** Follow-up milestone. Would be Alembic `V002`.
- **Connection pooling** (`psycopg2.pool.ThreadedConnectionPool`). If threaded CherryPy contention shows up, add it then.
- **Worker-queue scan model.** SpiderFoot's `multiprocessing.Process` model survives. Postgres unblocks concurrent scans but doesn't require redesign.
- **Migrating existing SQLite scan history.** Users lose their local `spiderfoot.db` scans on cutover. Acceptable: k3s deployments don't have long SQLite history to preserve.
- **Admin UI for the database** (pgAdmin / Adminer). Out of scope; use `psql` or an external tool.
- **Backup/restore tooling.** CloudNativePG provides this at the operator level.
- **Query-plan tuning.** Keep the 8 existing indexes as-is; tune later if scan queries get slow.
- **Read replicas.** Not needed at current scale.
- **Flyway compatibility.** Rejected in favor of Alembic (pure Python).

---

## Open items — none

Four design decisions settled in brainstorming:

1. **Hard cut**, Postgres-only.
2. **testcontainers-python** for CI and local dev test infrastructure.
3. **Alembic** for schema migrations (pure Python; lives in-repo next to code).
4. **Raw SQL** port (no SQLAlchemy).

Everything else flows from those four choices. Ready for the plan phase.
