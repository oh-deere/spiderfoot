#!/usr/bin/env python3
"""Seed a SpiderFoot Postgres DB with deterministic scan rows for Playwright E2E.

Usage:
    SPIDERFOOT_DATABASE_URL=postgresql://... python3 seed_db.py             # 5 deterministic scans
    SPIDERFOOT_DATABASE_URL=postgresql://... python3 seed_db.py --empty     # just build the schema, no rows
    SPIDERFOOT_DATABASE_URL=postgresql://... python3 seed_db.py --clear     # wipe rows from an existing DB
    SPIDERFOOT_DATABASE_URL=postgresql://... python3 seed_db.py --reseed    # clear + insert deterministic scans

Schema is owned by Alembic — ``run_alembic_upgrade`` is always invoked so
a fresh database gets the full schema before we insert. Timestamps are
stored in milliseconds (SpiderFootDb stores ``time.time() * 1000``).

--clear / --reseed use TRUNCATE ... RESTART IDENTITY CASCADE for speed —
the Postgres server does not hold the DB "open" the way SQLite did, so
TRUNCATE is safe to run while sf.py is serving. ``tbl_config`` and
``tbl_event_types`` are preserved; they hold seed metadata owned by the
Alembic migration, not test fixture data.
"""
import os
import sys
import time
import uuid

import psycopg2

# Make the repository root importable so we can reuse SpiderFootDb for
# scan inserts and the Alembic helper for schema creation.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from spiderfoot import SpiderFootDb  # noqa: E402
from spiderfoot.migrations import run_alembic_upgrade  # noqa: E402


SCANS = [
    # (name, seed_target, status, created_offset, started_offset, ended_offset)
    # Offsets are seconds before "now". ended=0 means "not yet ended".
    ("monthly-recon", "example.com", "FINISHED", 3600, 3590, 3000),
    ("ongoing-1", "running.example.com", "RUNNING", 120, 115, 0),
    ("failed-1", "broken.example.com", "ERROR-FAILED", 900, 895, 800),
    ("finished-2", "finished2.example.com", "FINISHED", 7200, 7190, 7000),
    ("finished-3", "finished3.example.com", "FINISHED", 10800, 10790, 10500),
]


def main(argv: list[str]) -> int:
    database_url = os.environ.get("SPIDERFOOT_DATABASE_URL", "")
    if not database_url:
        print(
            "SPIDERFOOT_DATABASE_URL is required (e.g. "
            "postgresql://spiderfoot:dev@localhost:55432/spiderfoot)",
            file=sys.stderr,
        )
        return 2

    flags = argv[1:]

    # Always ensure the schema exists. Alembic is idempotent — upgrading
    # an already-current DB is a no-op.
    run_alembic_upgrade(database_url)

    if "--empty" in flags:
        _clear(database_url)
        print(f"Seeded 0 scans into {database_url}")
        return 0

    if "--clear" in flags:
        _clear(database_url)
        print(f"Cleared {database_url}")
        return 0

    if "--reseed" in flags:
        _clear(database_url)
        _insert_scans(database_url)
        print(f"Reseeded {len(SCANS)} scans into {database_url}")
        return 0

    # default: wipe and re-seed so repeated runs converge on the same
    # fixture state.
    _clear(database_url)
    _insert_scans(database_url)
    print(f"Seeded {len(SCANS)} scans into {database_url}")
    return 0


def _clear(url: str) -> None:
    """TRUNCATE every scan-scoped table.

    ``tbl_config`` and ``tbl_event_types`` are intentionally left alone —
    they hold global metadata populated by the Alembic initial migration
    and the event-type registry, not fixture data.

    Args:
        url: Postgres connection URL.
    """
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE "
                "tbl_scan_correlation_results_events, "
                "tbl_scan_correlation_results, "
                "tbl_scan_results, "
                "tbl_scan_log, "
                "tbl_scan_config, "
                "tbl_scan_instance "
                "RESTART IDENTITY CASCADE"
            )
        conn.commit()


def _insert_scans(url: str) -> None:
    """Insert the deterministic fixture scans using SpiderFootDb.

    SpiderFootDb now connects to Postgres transparently; we reuse it so
    the insert path mirrors what production code writes.

    Args:
        url: Postgres connection URL.
    """
    db = SpiderFootDb({"__database": url})

    now_ms = int(time.time() * 1000)
    qry = (
        "INSERT INTO tbl_scan_instance "
        "(guid, name, seed_target, created, started, ended, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )

    monthly_recon_guid = None
    with db.dbhLock:
        for name, target, status, c_off, s_off, e_off in SCANS:
            guid = str(uuid.uuid4())
            created = now_ms - c_off * 1000
            started = now_ms - s_off * 1000
            ended = 0 if e_off == 0 else now_ms - e_off * 1000
            db.dbh.execute(qry, (guid, name, target, created, started, ended, status))
            if name == "monthly-recon":
                monthly_recon_guid = guid

    # Minimal scan_config for monthly-recon so /clonescan returns a usable
    # prefill (the 08-clone-scan spec exercises the Clone row action).
    if monthly_recon_guid is not None:
        db.scanConfigSet(
            monthly_recon_guid,
            {"_modulesenabled": "sfp_countryname,sfp_dnsresolve"},
        )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
