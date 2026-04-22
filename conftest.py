"""Repo-root pytest configuration — Postgres-backed test database.

Strategy:

* If ``SPIDERFOOT_TEST_DATABASE_URL`` is set in the environment, use
  that URL directly (fast path for local dev with the
  ``docker-compose`` Postgres on port 55432, and for CI where the
  workflow starts its own Postgres service).
* Otherwise, boot a session-scoped Postgres via testcontainers.

Under pytest-xdist, each worker gets its own database namespace. We
pick a per-worker database name (``spiderfoot_test_<workerid>``) and
run Alembic migrations into it on first use. Per-test isolation is
done with ``TRUNCATE ... RESTART IDENTITY`` inside each worker's DB.

Event-type rows are seeded once after migrations; the autouse
truncate fixture preserves them across tests.
"""
import os

import psycopg2
import pytest
from psycopg2 import sql


_DEFAULT_DEV_URL = "postgresql://spiderfoot:dev@localhost:55432/spiderfoot"


def _parse_admin_url(url: str) -> tuple[str, str]:
    """Split a libpq URL into (admin URL pointing at 'postgres', dbname-less URL).

    Args:
        url: full ``postgresql://user:pass@host:port/dbname`` URL.

    Returns:
        tuple: ``(admin_url, url_without_dbname)``. ``admin_url``
            connects to the ``postgres`` maintenance database (so we
            can ``CREATE DATABASE``); the second value is ``url`` with
            its path stripped — callers append a per-worker dbname.
    """
    from urllib.parse import urlparse, urlunparse

    p = urlparse(url)
    admin = urlunparse(p._replace(path="/postgres"))
    without_db = urlunparse(p._replace(path=""))
    return admin, without_db


@pytest.fixture(scope="session")
def postgres_url(worker_id):
    """Session-scoped Postgres URL (one database per pytest-xdist worker).

    Falls back to a session-scoped testcontainers Postgres when neither
    ``SPIDERFOOT_TEST_DATABASE_URL`` nor the dev ``docker-compose``
    instance is available.

    Args:
        worker_id: xdist worker id (``"master"`` when not parallelised).

    Yields:
        str: libpq-style URL for the per-worker database.
    """
    base_url = os.environ.get("SPIDERFOOT_TEST_DATABASE_URL")

    container = None
    if not base_url:
        # Try the dev docker-compose Postgres first — free and fast.
        try:
            conn = psycopg2.connect(_DEFAULT_DEV_URL, connect_timeout=2)
            conn.close()
            base_url = _DEFAULT_DEV_URL
        except Exception:
            base_url = None

    if not base_url:
        # Last resort — spin up a container (slow, but stand-alone).
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine")
        container.start()
        base_url = container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://", 1,
        )

    try:
        # Per-worker database. xdist sets ``worker_id`` to e.g. ``gw0``,
        # ``gw1``; non-xdist runs get ``master``.
        dbname = f"spiderfoot_test_{worker_id}"
        admin_url, url_no_db = _parse_admin_url(base_url)

        # (Re-)create the per-worker database from scratch.
        admin = psycopg2.connect(admin_url)
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname))
                )
        finally:
            admin.close()

        worker_url = f"{url_no_db}/{dbname}"
        os.environ["SPIDERFOOT_DATABASE_URL"] = worker_url

        from spiderfoot.migrations import run_alembic_upgrade
        run_alembic_upgrade(worker_url)

        from spiderfoot import SpiderFootDb
        _db = SpiderFootDb({"__database": worker_url})
        try:
            _db._populateEventTypes()
        finally:
            _db.close()

        yield worker_url

        # Best-effort teardown — drop the worker's database. Any
        # failure here just leaves a stale DB behind for the next
        # session's DROP IF EXISTS to clean up; do not block on it.
        try:
            admin = psycopg2.connect(admin_url, connect_timeout=5)
            admin.autocommit = True
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        [dbname],
                    )
                    cur.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(dbname)
                        )
                    )
            finally:
                admin.close()
        except Exception:
            pass
    finally:
        if container is not None:
            container.stop()


@pytest.fixture(autouse=True)
def _truncate_all_tables(postgres_url):
    """Per-test isolation — TRUNCATE every data table after each test.

    ``RESTART IDENTITY`` resets the ``tbl_scan_log.id`` sequence so
    tests don't accidentally depend on sequence values from prior
    runs. ``tbl_event_types`` is preserved — those rows are the seed
    from ``_populateEventTypes`` and are read-only for test purposes.

    Args:
        postgres_url: session-scoped Postgres URL from the sibling
            fixture. Declaring the dependency here is what pulls the
            per-worker database into existence before any test runs.

    Yields:
        None: tests run in the yield window; TRUNCATE runs afterwards.
    """
    yield  # run the test first
    conn = psycopg2.connect(postgres_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE tbl_scan_correlation_results_events, "
                "tbl_scan_correlation_results, tbl_scan_results, "
                "tbl_scan_log, tbl_scan_config, tbl_scan_instance "
                "RESTART IDENTITY"
            )
            cur.execute("DELETE FROM tbl_config")
        conn.commit()
    finally:
        conn.close()
