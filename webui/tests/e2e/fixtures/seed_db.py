#!/usr/bin/env python3
"""Seed a SpiderFoot SQLite DB with deterministic scan rows for Playwright E2E.

Usage:
    python3 seed_db.py <db-path>           # 5 deterministic scans (fresh DB)
    python3 seed_db.py <db-path> --empty   # just build the schema, no rows
    python3 seed_db.py <db-path> --clear   # wipe rows from an existing DB
    python3 seed_db.py <db-path> --reseed  # clear + insert deterministic scans
                                           # without removing the DB file

The schema is created via SpiderFootDb(init=True). The scan timestamps are
stored in milliseconds (SpiderFootDb stores ``time.time() * 1000``); the
``ROUND(i.started)/1000`` divisions in ``scanInstanceList`` confirm that.

--reseed exists because the E2E sf.py process keeps the SQLite file open for
the whole run; removing the file and re-init'ing (the default mode) races
with that connection. --reseed instead deletes rows via the existing handle
and re-inserts the same fixtures.
"""
import os
import sys
import time
import uuid

# Make the repository root importable so we can reuse SpiderFootDb for
# schema creation (matches the path sf.py itself uses for its DB file).
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from spiderfoot import SpiderFootDb  # noqa: E402


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
    if len(argv) < 2:
        print(f"usage: {argv[0]} <db-path> [--empty|--clear]", file=sys.stderr)
        return 2

    db_path = argv[1]
    flags = argv[2:]

    if "--clear" in flags:
        # Wipe rows from an existing, possibly-open DB without rebuilding
        # the schema. Used by the E2E empty-state spec between tests:
        # the running sf.py holds the SQLite file, so removing and
        # re-initialising would race with its connection.
        db = SpiderFootDb({"__database": db_path})
        with db.dbhLock:
            db.dbh.execute("DELETE FROM tbl_scan_instance")
            db.conn.commit()
        print(f"Cleared {db_path}")
        return 0

    if "--reseed" in flags:
        # Clear + re-insert the deterministic scans without touching the
        # DB file itself — sf.py keeps it open for the whole E2E run.
        db = SpiderFootDb({"__database": db_path})
        _insert_scans(db, clear_first=True)
        print(f"Reseeded {len(SCANS)} scans into {db_path}")
        return 0

    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # init=True creates the full schema on a fresh file.
    db = SpiderFootDb({"__database": db_path}, init=True)

    if "--empty" in flags:
        print(f"Seeded 0 scans into {db_path}")
        return 0

    _insert_scans(db, clear_first=False)
    print(f"Seeded {len(SCANS)} scans into {db_path}")
    return 0


def _insert_scans(db: "SpiderFootDb", clear_first: bool) -> None:
    now_ms = time.time() * 1000
    qry = (
        "INSERT INTO tbl_scan_instance "
        "(guid, name, seed_target, created, started, ended, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    with db.dbhLock:
        if clear_first:
            db.dbh.execute("DELETE FROM tbl_scan_instance")
        for name, target, status, c_off, s_off, e_off in SCANS:
            guid = str(uuid.uuid4())
            created = now_ms - c_off * 1000
            started = now_ms - s_off * 1000
            ended = 0 if e_off == 0 else now_ms - e_off * 1000
            db.dbh.execute(qry, (guid, name, target, created, started, ended, status))
        db.conn.commit()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
