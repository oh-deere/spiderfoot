# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfdb
# Purpose:      Common functions for working with the Postgres database back-end.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     15/05/2012
# Copyright:   (c) Steve Micallef 2012
# Licence:     MIT
# -------------------------------------------------------------------------------

import contextlib
import hashlib
import os
import random
import threading
import time
import urllib.parse

import psycopg2

from spiderfoot.event_types import EVENT_TYPES


def _redact_url(url: str) -> str:
    """Return ``url`` with any embedded password replaced by ``***``.

    Used so that connection-failure messages we log or raise don't leak
    the credential to logs/scan output. Falls back to a generic
    placeholder if the URL can't be parsed.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.password:
            return url
        netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@", 1)
        return urllib.parse.urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        return "<postgres url redacted>"


class SpiderFootDb:
    """SpiderFoot database (Postgres via psycopg2).

    Schema is owned by Alembic (see ``spiderfoot/migrations.py`` and
    ``alembic/versions/V001__initial_schema.py``). The ``init`` flag on
    the constructor is kept as a no-op for legacy call-site
    compatibility — passing ``init=True`` used to create the schema on
    a fresh SQLite file; under Postgres that is the migration tool's
    job, not ours.

    Attributes:
        conn: psycopg2 connection
        dbh: psycopg2 cursor
        dbhLock (threading.RLock): serialises access to the cursor
    """

    dbh = None
    conn = None

    # Serialise access to the cursor. Postgres itself handles concurrency
    # across connections, but this class shares a single cursor between
    # threads (scanner workers + logger), which is not itself thread-safe.
    dbhLock = threading.RLock()

    def __init__(self, opts: dict, init: bool = False) -> None:
        """Connect to Postgres.

        Args:
            opts (dict): must specify the Postgres URL under the
                ``__database`` key, or ``SPIDERFOOT_DATABASE_URL`` must
                be set in the environment.
            init (bool): ignored — kept for backwards compatibility.
                Schema is owned by Alembic.

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database connection failed
        """
        if not isinstance(opts, dict):
            raise TypeError(f"opts is {type(opts)}; expected dict()") from None
        if not opts:
            raise ValueError("opts is empty") from None

        url = opts.get('__database') or os.environ.get(
            "SPIDERFOOT_DATABASE_URL", ""
        )
        if not url:
            raise ValueError(
                "opts['__database'] is empty and SPIDERFOOT_DATABASE_URL "
                "is unset — SpiderFootDb needs a Postgres URL"
            ) from None

        self.opts = opts
        self._closed = False

        try:
            self.conn = psycopg2.connect(url, connect_timeout=10)
        except Exception as e:
            raise IOError(
                f"Error connecting to Postgres at {_redact_url(url)}"
            ) from e

        # autocommit=True — we never span multiple statements across a
        # single semantic "operation" (the only multi-statement method
        # is scanInstanceDelete, which the code happens to run as an
        # idempotent sequence of DELETEs). Keeping each SELECT in its
        # own auto-committed statement avoids "idle in transaction"
        # connections holding relation locks that block TRUNCATE in
        # concurrent writers.
        self.conn.autocommit = True
        self.dbh = self.conn.cursor()

    def __enter__(self) -> 'SpiderFootDb':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        # Safety net — if a caller forgets to close() (or use `with`),
        # ensure the connection is closed when the instance is
        # garbage-collected. Without this, a leaked SpiderFootDb keeps
        # its slot on the server until the process dies.
        # Use a bare try/except (not contextlib.suppress) because at
        # interpreter shutdown the contextlib module may already be
        # partially torn down.
        try:
            self.close()
        except BaseException:
            pass

    #
    # Back-end database operations
    #

    def create(self) -> None:
        """Legacy no-op.

        Schema creation is owned by Alembic
        (``spiderfoot.migrations.run_alembic_upgrade``). Kept so that
        any lingering caller does not crash.
        """
        with self.dbhLock:
            self._populateEventTypes()

    def _populateEventTypes(self) -> None:
        """Populate ``tbl_event_types`` from the typed registry.

        Idempotent — re-inserts are swallowed via
        ``ON CONFLICT (event) DO NOTHING``.
        """
        qry = (
            "INSERT INTO tbl_event_types "
            "(event, event_descr, event_raw, event_type) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (event) DO NOTHING"
        )
        for enum_member, definition in EVENT_TYPES.items():
            self.dbh.execute(qry, (
                enum_member.value,
                definition.description,
                1 if definition.is_raw else 0,
                definition.category.value,
            ))
        self.conn.commit()

    def close(self) -> None:
        """Close the cursor + connection. Idempotent."""
        with self.dbhLock:
            if self._closed:
                return
            self._closed = True
            with contextlib.suppress(Exception):
                self.dbh.close()
            with contextlib.suppress(Exception):
                self.conn.close()

    def vacuumDB(self) -> bool:
        """VACUUM the database. Must run in autocommit mode under Postgres.

        Returns:
            bool: True on success

        Raises:
            IOError: database I/O failed
        """
        with self.dbhLock:
            try:
                old_autocommit = self.conn.autocommit
                self.conn.autocommit = True
                try:
                    self.dbh.execute("VACUUM")
                finally:
                    self.conn.autocommit = old_autocommit
                return True
            except psycopg2.Error as e:
                raise IOError("SQL error encountered when vacuuming the database") from e

    def search(self, criteria: dict, filterFp: bool = False) -> list:
        """Search database.

        Args:
            criteria (dict): search criteria such as:
                - scan_id (search within a scan, if omitted search all)
                - type (search a specific type, if omitted search all)
                - value (search values for a specific string, if omitted search all)
                - regex (search values for a regular expression)
                ** at least two criteria must be set **
            filterFp (bool): filter out false positives

        Returns:
            list: search results

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(criteria, dict):
            raise TypeError(f"criteria is {type(criteria)}; expected dict()") from None

        valid_criteria = ['scan_id', 'type', 'value', 'regex']

        for key in list(criteria.keys()):
            if key not in valid_criteria:
                criteria.pop(key, None)
                continue

            if not isinstance(criteria.get(key), str):
                raise TypeError(f"criteria[{key}] is {type(criteria.get(key))}; expected str()") from None

            if not criteria[key]:
                criteria.pop(key, None)
                continue

        if len(criteria) == 0:
            raise ValueError(f"No valid search criteria provided; expected: {', '.join(valid_criteria)}") from None

        if len(criteria) == 1:
            raise ValueError("Only one search criteria provided; expected at least two")

        qvars = list()
        qry = "SELECT ROUND(c.generated)::float AS generated, c.data, \
            s.data as source_data, \
            c.module, c.type, c.confidence, c.visibility, c.risk, c.hash, \
            c.source_event_hash, t.event_descr, t.event_type, c.scan_instance_id, \
            c.false_positive as fp, s.false_positive as parent_fp \
            FROM tbl_scan_results c, tbl_scan_results s, tbl_event_types t \
            WHERE s.scan_instance_id = c.scan_instance_id AND \
            t.event = c.type AND c.source_event_hash = s.hash "

        if filterFp:
            qry += " AND c.false_positive <> 1 "

        if criteria.get('scan_id') is not None:
            qry += "AND c.scan_instance_id = %s "
            qvars.append(criteria['scan_id'])

        if criteria.get('type') is not None:
            qry += " AND c.type = %s "
            qvars.append(criteria['type'])

        if criteria.get('value') is not None:
            qry += " AND (c.data LIKE %s OR s.data LIKE %s) "
            qvars.append(criteria['value'])
            qvars.append(criteria['value'])

        if criteria.get('regex') is not None:
            qry += " AND (c.data ~* %s OR s.data ~* %s) "
            qvars.append(criteria['regex'])
            qvars.append(criteria['regex'])

        qry += " ORDER BY c.data"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching search results") from e

    def eventTypes(self) -> list:
        """Get event types.

        Returns:
            list: event types

        Raises:
            IOError: database I/O failed
        """
        qry = "SELECT event_descr, event, event_raw, event_type FROM tbl_event_types"
        with self.dbhLock:
            try:
                self.dbh.execute(qry)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when retrieving event types") from e

    def scanLogEvents(self, batch: list) -> bool:
        """Log a batch of events to the database.

        Args:
            batch (list): tuples containing: instanceId, classification, message, component, logTime

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Returns:
            bool: Whether the logging operation succeeded
        """
        inserts = []

        for instanceId, classification, message, component, logTime in batch:
            if not isinstance(instanceId, str):
                raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

            if not isinstance(classification, str):
                raise TypeError(f"classification is {type(classification)}; expected str()") from None

            if not isinstance(message, str):
                raise TypeError(f"message is {type(message)}; expected str()") from None

            if not component:
                component = "SpiderFoot"

            inserts.append((instanceId, int(logTime * 1000), component, classification, message))

        if inserts:
            qry = "INSERT INTO tbl_scan_log \
                (scan_instance_id, generated, component, type, message) \
                VALUES (%s, %s, %s, %s, %s)"

            with self.dbhLock:
                try:
                    self.dbh.executemany(qry, inserts)
                    self.conn.commit()
                except psycopg2.Error as e:
                    self.conn.rollback()
                    msg = str(e) if e.args else ""
                    if "locked" not in msg and "thread" not in msg:
                        raise IOError("Unable to log scan event in database") from e
                    return False
        return True

    def scanLogEvent(self, instanceId: str, classification: str, message: str, component: str = None) -> None:
        """Log an event to the database.

        Args:
            instanceId (str): scan instance ID
            classification (str): log-level classification ("INFO", "ERROR", ...)
            message (str): log message body
            component (str): module/component name that produced the log

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Todo:
            Do something smarter to handle database locks
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(classification, str):
            raise TypeError(f"classification is {type(classification)}; expected str()") from None

        if not isinstance(message, str):
            raise TypeError(f"message is {type(message)}; expected str()") from None

        if not component:
            component = "SpiderFoot"

        qry = "INSERT INTO tbl_scan_log \
            (scan_instance_id, generated, component, type, message) \
            VALUES (%s, %s, %s, %s, %s)"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, (
                    instanceId, int(time.time() * 1000), component, classification, message
                ))
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                msg = str(e) if e.args else ""
                if "locked" not in msg and "thread" not in msg:
                    raise IOError("Unable to log scan event in database") from e

    def scanInstanceCreate(self, instanceId: str, scanName: str, scanTarget: str) -> None:
        """Store a scan instance in the database.

        Args:
            instanceId (str): scan instance ID
            scanName (str): scan name
            scanTarget (str): scan target

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(scanName, str):
            raise TypeError(f"scanName is {type(scanName)}; expected str()") from None

        if not isinstance(scanTarget, str):
            raise TypeError(f"scanTarget is {type(scanTarget)}; expected str()") from None

        qry = "INSERT INTO tbl_scan_instance \
            (guid, name, seed_target, created, status) \
            VALUES (%s, %s, %s, %s, %s)"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, (
                    instanceId, scanName, scanTarget, int(time.time() * 1000), 'CREATED'
                ))
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("Unable to create scan instance in database") from e

    def scanInstanceSet(self, instanceId: str, started: str = None, ended: str = None, status: str = None) -> None:
        """Update the start time, end time or status (or all 3) of a scan instance.

        Args:
            instanceId (str): scan instance ID
            started: scan start time (epoch ms)
            ended: scan end time (epoch ms)
            status (str): scan status

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qvars = list()
        qry = "UPDATE tbl_scan_instance SET "

        if started is not None:
            qry += " started = %s,"
            qvars.append(int(float(started)))

        if ended is not None:
            qry += " ended = %s,"
            qvars.append(int(float(ended)))

        if status is not None:
            qry += " status = %s,"
            qvars.append(status)

        # guid = guid is a little hack to avoid messing with , placement above
        qry += " guid = guid WHERE guid = %s"
        qvars.append(instanceId)

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                self.conn.commit()
            except psycopg2.Error:
                self.conn.rollback()
                raise IOError("Unable to set information for the scan instance.") from None

    def scanInstanceGet(self, instanceId: str) -> list:
        """Return info about a scan instance (name, target, created, started, ended, status).

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan instance info

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = "SELECT name, seed_target, (created/1000)::float AS created, \
            (started/1000)::float AS started, (ended/1000)::float AS ended, status \
            FROM tbl_scan_instance WHERE guid = %s"
        qvars = [instanceId]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return self.dbh.fetchone()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when retrieving scan instance") from e

    def scanResultSummary(self, instanceId: str, by: str = "type") -> list:
        """Obtain a summary of the results, filtered by event type, module or entity.

        Args:
            instanceId (str): scan instance ID
            by (str): filter by "type", "module" or "entity"

        Returns:
            list: scan result summary

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(by, str):
            raise TypeError(f"by is {type(by)}; expected str()") from None

        if by not in ["type", "module", "entity"]:
            raise ValueError(f"Invalid filter by value: {by}") from None

        if by == "type":
            qry = "SELECT r.type, e.event_descr, MAX(ROUND(generated)::float) AS last_in, \
                count(*) AS total, count(DISTINCT r.data) as utotal FROM \
                tbl_scan_results r, tbl_event_types e WHERE e.event = r.type \
                AND r.scan_instance_id = %s GROUP BY r.type, e.event_descr ORDER BY e.event_descr"

        if by == "module":
            qry = "SELECT r.module, '', MAX(ROUND(generated)::float) AS last_in, \
                count(*) AS total, count(DISTINCT r.data) as utotal FROM \
                tbl_scan_results r, tbl_event_types e WHERE e.event = r.type \
                AND r.scan_instance_id = %s GROUP BY r.module ORDER BY r.module DESC"

        if by == "entity":
            qry = "SELECT r.data, e.event_descr, MAX(ROUND(generated)::float) AS last_in, \
                count(*) AS total, count(DISTINCT r.data) as utotal FROM \
                tbl_scan_results r, tbl_event_types e WHERE e.event = r.type \
                AND r.scan_instance_id = %s \
                AND e.event_type in ('ENTITY') \
                GROUP BY r.data, e.event_descr ORDER BY total DESC limit 50"

        qvars = [instanceId]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching result summary") from e

    def scanCorrelationSummary(self, instanceId: str, by: str = "rule") -> list:
        """Obtain a summary of the correlations, filtered by rule or risk.

        Args:
            instanceId (str): scan instance ID
            by (str): filter by "rule" or "risk"

        Returns:
            list: scan correlation summary

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(by, str):
            raise TypeError(f"by is {type(by)}; expected str()") from None

        if by not in ["rule", "risk"]:
            raise ValueError(f"Invalid filter by value: {by}") from None

        if by == "risk":
            qry = "SELECT rule_risk, count(*) AS total FROM \
                tbl_scan_correlation_results \
                WHERE scan_instance_id = %s GROUP BY rule_risk ORDER BY rule_risk"

        if by == "rule":
            qry = "SELECT rule_id, rule_name, rule_risk, rule_descr, \
                count(*) AS total FROM \
                tbl_scan_correlation_results \
                WHERE scan_instance_id = %s GROUP BY rule_id, rule_name, rule_risk, rule_descr ORDER BY rule_id"

        qvars = [instanceId]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching correlation summary") from e

    def scanCorrelationList(self, instanceId: str) -> list:
        """Obtain a list of the correlations from a scan.

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan correlation list

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = "SELECT c.id, c.title, c.rule_id, c.rule_risk, c.rule_name, \
            c.rule_descr, c.rule_logic, count(e.event_hash) AS event_count FROM \
            tbl_scan_correlation_results c, tbl_scan_correlation_results_events e \
            WHERE scan_instance_id = %s AND c.id = e.correlation_id \
            GROUP BY c.id, c.title, c.rule_id, c.rule_risk, c.rule_name, c.rule_descr, c.rule_logic \
            ORDER BY c.title, c.rule_risk"

        qvars = [instanceId]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching correlation list") from e

    def scanResultEvent(
        self,
        instanceId: str,
        eventType: str = 'ALL',
        srcModule: str = None,
        data: list = None,
        sourceId: list = None,
        correlationId: str = None,
        filterFp: bool = False
    ) -> list:
        """Obtain the data for a scan and event type.

        Args:
            instanceId (str): scan instance ID
            eventType (str): filter by event type
            srcModule (str): filter by the generating module
            data (list): filter by the data
            sourceId (list): filter by the ID of the source event
            correlationId (str): filter by the ID of a correlation result
            filterFp (bool): filter false positives

        Returns:
            list: scan results

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(eventType, str) and not isinstance(eventType, list):
            raise TypeError(f"eventType is {type(eventType)}; expected str() or list()") from None

        qry = "SELECT ROUND(c.generated)::float AS generated, c.data, \
            s.data as source_data, \
            c.module, c.type, c.confidence, c.visibility, c.risk, c.hash, \
            c.source_event_hash, t.event_descr, t.event_type, s.scan_instance_id, \
            c.false_positive as fp, s.false_positive as parent_fp \
            FROM tbl_scan_results c, tbl_scan_results s, tbl_event_types t "

        if correlationId:
            qry += ", tbl_scan_correlation_results_events ce "

        qry += "WHERE c.scan_instance_id = %s AND c.source_event_hash = s.hash AND \
            s.scan_instance_id = c.scan_instance_id AND t.event = c.type"

        qvars = [instanceId]

        if correlationId:
            qry += " AND ce.event_hash = c.hash AND ce.correlation_id = %s"
            qvars.append(correlationId)

        if eventType != "ALL":
            if isinstance(eventType, list):
                qry += " AND c.type in (" + ','.join(['%s'] * len(eventType)) + ")"
                qvars.extend(eventType)
            else:
                qry += " AND c.type = %s"
                qvars.append(eventType)

        if filterFp:
            qry += " AND c.false_positive <> 1"

        if srcModule:
            if isinstance(srcModule, list):
                qry += " AND c.module in (" + ','.join(['%s'] * len(srcModule)) + ")"
                qvars.extend(srcModule)
            else:
                qry += " AND c.module = %s"
                qvars.append(srcModule)

        if data:
            if isinstance(data, list):
                qry += " AND c.data in (" + ','.join(['%s'] * len(data)) + ")"
                qvars.extend(data)
            else:
                qry += " AND c.data = %s"
                qvars.append(data)

        if sourceId:
            if isinstance(sourceId, list):
                qry += " AND c.source_event_hash in (" + ','.join(['%s'] * len(sourceId)) + ")"
                qvars.extend(sourceId)
            else:
                qry += " AND c.source_event_hash = %s"
                qvars.append(sourceId)

        qry += " ORDER BY c.data"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching result events") from e

    def scanResultEventUnique(self, instanceId: str, eventType: str = 'ALL', filterFp: bool = False) -> list:
        """Obtain a unique list of elements.

        Args:
            instanceId (str): scan instance ID
            eventType (str): filter by event type
            filterFp (bool): filter false positives

        Returns:
            list: unique scan results

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(eventType, str):
            raise TypeError(f"eventType is {type(eventType)}; expected str()") from None

        qry = "SELECT DISTINCT data, type, COUNT(*) FROM tbl_scan_results \
            WHERE scan_instance_id = %s"
        qvars = [instanceId]

        if eventType != "ALL":
            qry += " AND type = %s"
            qvars.append(eventType)

        if filterFp:
            qry += " AND false_positive <> 1"

        qry += " GROUP BY type, data ORDER BY COUNT(*)"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching unique result events") from e

    def scanLogs(self, instanceId: str, limit: int = None, fromRowId: int = 0, reverse: bool = False) -> list:
        """Get scan logs.

        Args:
            instanceId (str): scan instance ID
            limit (int): limit number of results
            fromRowId (int): retrieve logs starting from row ID
            reverse (bool): search result order

        Returns:
            list: scan logs

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = "SELECT generated AS generated, component, \
            type, message, id FROM tbl_scan_log WHERE scan_instance_id = %s"
        if fromRowId:
            qry += " and id > %s"

        qry += " ORDER BY generated "
        if reverse:
            qry += "ASC"
        else:
            qry += "DESC"
        qvars = [instanceId]

        if fromRowId:
            qvars.append(int(fromRowId))

        if limit is not None:
            qry += " LIMIT %s"
            qvars.append(int(limit))

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching scan logs") from e

    def scanErrors(self, instanceId: str, limit: int = 0) -> list:
        """Get scan errors.

        Args:
            instanceId (str): scan instance ID
            limit (int): limit number of results

        Returns:
            list: scan errors

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(limit, int):
            raise TypeError(f"limit is {type(limit)}; expected int()") from None

        qry = "SELECT generated AS generated, component, \
            message FROM tbl_scan_log WHERE scan_instance_id = %s \
            AND type = 'ERROR' ORDER BY generated DESC"
        qvars = [instanceId]

        if limit:
            qry += " LIMIT %s"
            qvars.append(int(limit))

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching scan errors") from e

    def scanInstanceDelete(self, instanceId: str) -> bool:
        """Delete a scan instance.

        Args:
            instanceId (str): scan instance ID

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry1 = "DELETE FROM tbl_scan_instance WHERE guid = %s"
        qry2 = "DELETE FROM tbl_scan_config WHERE scan_instance_id = %s"
        qry3 = "DELETE FROM tbl_scan_results WHERE scan_instance_id = %s"
        qry4 = "DELETE FROM tbl_scan_log WHERE scan_instance_id = %s"
        qvars = [instanceId]

        with self.dbhLock:
            try:
                # Order matters under Postgres — FK constraints force us
                # to delete children before parents.
                self.dbh.execute(qry2, qvars)
                self.dbh.execute(qry3, qvars)
                self.dbh.execute(qry4, qvars)
                self.dbh.execute(qry1, qvars)
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when deleting scan") from e

        return True

    def scanResultsUpdateFP(self, instanceId: str, resultHashes: list, fpFlag: int) -> bool:
        """Set the false positive flag for a result.

        Args:
            instanceId (str): scan instance ID
            resultHashes (list): list of event hashes
            fpFlag (int): false positive flag

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(resultHashes, list):
            raise TypeError(f"resultHashes is {type(resultHashes)}; expected list()") from None

        with self.dbhLock:
            for resultHash in resultHashes:
                qry = "UPDATE tbl_scan_results SET false_positive = %s WHERE \
                    scan_instance_id = %s AND hash = %s"
                qvars = [fpFlag, instanceId, resultHash]
                try:
                    self.dbh.execute(qry, qvars)
                except psycopg2.Error as e:
                    self.conn.rollback()
                    raise IOError("SQL error encountered when updating false-positive") from e

            try:
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when updating false-positive") from e

        return True

    def configSet(self, optMap: dict = {}) -> bool:
        """Store the default configuration in the database.

        Args:
            optMap (dict): config options

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(optMap, dict):
            raise TypeError(f"optMap is {type(optMap)}; expected dict()") from None
        if not optMap:
            raise ValueError("optMap is empty") from None

        qry = ("INSERT INTO tbl_config (scope, opt, val) VALUES (%s, %s, %s) "
               "ON CONFLICT (scope, opt) DO UPDATE SET val = EXCLUDED.val")

        with self.dbhLock:
            for opt in list(optMap.keys()):
                # Module option
                if ":" in opt:
                    parts = opt.split(':')
                    qvals = [parts[0], parts[1], optMap[opt]]
                else:
                    # Global option
                    qvals = ["GLOBAL", opt, optMap[opt]]

                try:
                    self.dbh.execute(qry, qvals)
                except psycopg2.Error as e:
                    self.conn.rollback()
                    raise IOError("SQL error encountered when storing config, aborting") from e

            try:
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when storing config, aborting") from e

        return True

    def configGet(self) -> dict:
        """Retrieve the config from the database.

        Returns:
            dict: config

        Raises:
            IOError: database I/O failed
        """
        qry = "SELECT scope, opt, val FROM tbl_config"

        retval = dict()

        with self.dbhLock:
            try:
                self.dbh.execute(qry)
                for scope, opt, val in self.dbh.fetchall():
                    if scope == "GLOBAL":
                        retval[opt] = val
                    else:
                        retval[f"{scope}:{opt}"] = val

                return retval
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching configuration") from e

    def configClear(self) -> None:
        """Reset the config to default.

        Clears the config from the database and lets the hard-coded
        settings in the code take effect.

        Raises:
            IOError: database I/O failed
        """
        qry = "DELETE from tbl_config"
        with self.dbhLock:
            try:
                self.dbh.execute(qry)
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("Unable to clear configuration from the database") from e

    def scanConfigSet(self, scan_id, optMap=dict()) -> None:
        """Store a configuration value for a scan.

        Args:
            scan_id (str): scan instance ID
            optMap (dict): config options

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(optMap, dict):
            raise TypeError(f"optMap is {type(optMap)}; expected dict()") from None
        if not optMap:
            raise ValueError("optMap is empty") from None

        # tbl_scan_config has no UNIQUE/PK constraint — a plain INSERT
        # matches the SQLite REPLACE semantics on that table (which had
        # nothing to REPLACE against either, so every call just
        # appended rows).
        qry = "INSERT INTO tbl_scan_config \
                (scan_instance_id, component, opt, val) VALUES (%s, %s, %s, %s)"

        with self.dbhLock:
            for opt in list(optMap.keys()):
                # Module option
                if ":" in opt:
                    parts = opt.split(':')
                    qvals = [scan_id, parts[0], parts[1], optMap[opt]]
                else:
                    # Global option
                    qvals = [scan_id, "GLOBAL", opt, optMap[opt]]

                try:
                    self.dbh.execute(qry, qvals)
                except psycopg2.Error as e:
                    self.conn.rollback()
                    raise IOError("SQL error encountered when storing config, aborting") from e

            try:
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when storing config, aborting") from e

    def scanConfigGet(self, instanceId: str) -> dict:
        """Retrieve configuration data for a scan component.

        Args:
            instanceId (str): scan instance ID

        Returns:
            dict: configuration data

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = "SELECT component, opt, val FROM tbl_scan_config \
                WHERE scan_instance_id = %s ORDER BY component, opt"
        qvars = [instanceId]

        retval = dict()

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                for component, opt, val in self.dbh.fetchall():
                    if component == "GLOBAL":
                        retval[opt] = val
                    else:
                        retval[f"{component}:{opt}"] = val
                return retval
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching configuration") from e

    def scanEventStore(self, instanceId: str, sfEvent, truncateSize: int = 0) -> None:
        """Store an event in the database.

        Args:
            instanceId (str): scan instance ID
            sfEvent (SpiderFootEvent): event to be stored in the database
            truncateSize (int): truncate size for event data

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        from spiderfoot import SpiderFootEvent

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not instanceId:
            raise ValueError("instanceId is empty") from None

        if not isinstance(sfEvent, SpiderFootEvent):
            raise TypeError(f"sfEvent is {type(sfEvent)}; expected SpiderFootEvent()") from None

        if not isinstance(sfEvent.generated, float):
            raise TypeError(f"sfEvent.generated is {type(sfEvent.generated)}; expected float()") from None

        if not sfEvent.generated:
            raise ValueError("sfEvent.generated is empty") from None

        if not isinstance(sfEvent.eventType, str):
            raise TypeError(f"sfEvent.eventType is {type(sfEvent.eventType,)}; expected str()") from None

        if not sfEvent.eventType:
            raise ValueError("sfEvent.eventType is empty") from None

        if not isinstance(sfEvent.data, str):
            raise TypeError(f"sfEvent.data is {type(sfEvent.data)}; expected str()") from None

        if not sfEvent.data:
            raise ValueError("sfEvent.data is empty") from None

        if not isinstance(sfEvent.module, str):
            raise TypeError(f"sfEvent.module is {type(sfEvent.module)}; expected str()") from None

        if not sfEvent.module and sfEvent.eventType != "ROOT":
            raise ValueError("sfEvent.module is empty") from None

        if not isinstance(sfEvent.confidence, int):
            raise TypeError(f"sfEvent.confidence is {type(sfEvent.confidence)}; expected int()") from None

        if not 0 <= sfEvent.confidence <= 100:
            raise ValueError(f"sfEvent.confidence value is {type(sfEvent.confidence)}; expected 0 - 100") from None

        if not isinstance(sfEvent.visibility, int):
            raise TypeError(f"sfEvent.visibility is {type(sfEvent.visibility)}; expected int()") from None

        if not 0 <= sfEvent.visibility <= 100:
            raise ValueError(f"sfEvent.visibility value is {type(sfEvent.visibility)}; expected 0 - 100") from None

        if not isinstance(sfEvent.risk, int):
            raise TypeError(f"sfEvent.risk is {type(sfEvent.risk)}; expected int()") from None

        if not 0 <= sfEvent.risk <= 100:
            raise ValueError(f"sfEvent.risk value is {type(sfEvent.risk)}; expected 0 - 100") from None

        if not isinstance(sfEvent.sourceEvent, SpiderFootEvent) and sfEvent.eventType != "ROOT":
            raise TypeError(f"sfEvent.sourceEvent is {type(sfEvent.sourceEvent)}; expected str()") from None

        if not isinstance(sfEvent.sourceEventHash, str):
            raise TypeError(f"sfEvent.sourceEventHash is {type(sfEvent.sourceEventHash)}; expected str()") from None

        if not sfEvent.sourceEventHash:
            raise ValueError("sfEvent.sourceEventHash is empty") from None

        storeData = sfEvent.data

        # truncate if required
        if isinstance(truncateSize, int) and truncateSize > 0:
            storeData = storeData[0:truncateSize]

        qry = "INSERT INTO tbl_scan_results \
            (scan_instance_id, hash, type, generated, confidence, \
            visibility, risk, module, data, source_event_hash) \
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

        qvals = [instanceId, sfEvent.hash, sfEvent.eventType, int(sfEvent.generated),
                 sfEvent.confidence, sfEvent.visibility, sfEvent.risk,
                 sfEvent.module, storeData, sfEvent.sourceEventHash]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvals)
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError(f"SQL error encountered when storing event data ({self.dbh})") from e

    def scanInstanceList(self) -> list:
        """List all previously run scans.

        Returns:
            list: previously run scans

        Raises:
            IOError: database I/O failed
        """
        # Postgres supports LEFT JOIN directly (SQLite used a UNION ALL
        # workaround because it didn't support OUTER JOINs).
        qry = "SELECT i.guid, i.name, i.seed_target, \
            (i.created/1000)::float, \
            (i.started/1000)::float AS started, \
            (i.ended/1000)::float, \
            i.status, \
            COALESCE(SUM(CASE WHEN r.type <> 'ROOT' THEN 1 ELSE 0 END), 0) AS total \
            FROM tbl_scan_instance i \
            LEFT JOIN tbl_scan_results r ON i.guid = r.scan_instance_id \
            GROUP BY i.guid \
            ORDER BY started DESC"

        with self.dbhLock:
            try:
                self.dbh.execute(qry)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when fetching scan list") from e

    def scanResultHistory(self, instanceId: str) -> list:
        """History of data from the scan.

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan data history

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        # SQLite's STRFTIME('%H:%M %w', generated, 'unixepoch') formatted
        # an epoch-seconds int as "HH:MM D" where D is 0-6 (Sunday=0).
        # to_char(to_timestamp(...), 'HH24:MI D') reproduces the format
        # but Postgres's D is 1-7 (Sunday=1). Subtract 1 so outputs line
        # up if any downstream consumer cares — none in the repo does
        # (it's a grouping key, not a value).
        qry = "SELECT to_char(to_timestamp(generated), 'HH24:MI ') \
                || ((EXTRACT(DOW FROM to_timestamp(generated))::int)::text) AS hourmin, \
                type, COUNT(*) FROM tbl_scan_results \
                WHERE scan_instance_id = %s GROUP BY hourmin, type"
        qvars = [instanceId]

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError(f"SQL error encountered when fetching history for scan {instanceId}") from e

    def scanElementSourcesDirect(self, instanceId: str, elementIdList: list) -> list:
        """Get the source IDs, types and data for a set of IDs.

        Args:
            instanceId (str): scan instance ID
            elementIdList (list): event hashes to resolve sources for

        Returns:
            list: source events

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(elementIdList, list):
            raise TypeError(f"elementIdList is {type(elementIdList)}; expected list()") from None

        hashIds = []
        for hashId in elementIdList:
            if not hashId:
                continue
            if not hashId.isalnum():
                continue
            hashIds.append(hashId)

        if not hashIds:
            return []

        # the output of this needs to be aligned with scanResultEvent,
        # as other functions call both expecting the same output.
        placeholders = ','.join(['%s'] * len(hashIds))
        qry = ("SELECT ROUND(c.generated)::float AS generated, c.data, "
               "s.data as source_data, "
               "c.module, c.type, c.confidence, c.visibility, c.risk, c.hash, "
               "c.source_event_hash, t.event_descr, t.event_type, s.scan_instance_id, "
               "c.false_positive as fp, s.false_positive as parent_fp, "
               "s.type, s.module, st.event_type as source_entity_type "
               "FROM tbl_scan_results c, tbl_scan_results s, tbl_event_types t, "
               "tbl_event_types st "
               "WHERE c.scan_instance_id = %s AND c.source_event_hash = s.hash AND "
               "s.scan_instance_id = c.scan_instance_id AND st.event = s.type AND "
               f"t.event = c.type AND c.hash in ({placeholders})")
        qvars = [instanceId] + hashIds

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when getting source element IDs") from e

    def scanElementChildrenDirect(self, instanceId: str, elementIdList: list) -> list:
        """Get the child IDs, types and data for a set of IDs.

        Args:
            instanceId (str): scan instance ID
            elementIdList (list): event hashes to resolve children for

        Returns:
            list: child events

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(elementIdList, list):
            raise TypeError(f"elementIdList is {type(elementIdList)}; expected list()")

        hashIds = []
        for hashId in elementIdList:
            if not hashId:
                continue
            if not hashId.isalnum():
                continue
            hashIds.append(hashId)

        if not hashIds:
            return []

        placeholders = ','.join(['%s'] * len(hashIds))
        qry = ("SELECT ROUND(c.generated)::float AS generated, c.data, "
               "s.data as source_data, "
               "c.module, c.type, c.confidence, c.visibility, c.risk, c.hash, "
               "c.source_event_hash, t.event_descr, t.event_type, s.scan_instance_id, "
               "c.false_positive as fp, s.false_positive as parent_fp "
               "FROM tbl_scan_results c, tbl_scan_results s, tbl_event_types t "
               "WHERE c.scan_instance_id = %s AND c.source_event_hash = s.hash AND "
               "s.scan_instance_id = c.scan_instance_id AND "
               f"t.event = c.type AND s.hash in ({placeholders})")
        qvars = [instanceId] + hashIds

        with self.dbhLock:
            try:
                self.dbh.execute(qry, qvars)
                return list(self.dbh.fetchall())
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("SQL error encountered when getting child element IDs") from e

    def scanElementSourcesAll(self, instanceId: str, childData: list) -> list:
        """Get the full set of upstream IDs which are parents to the supplied set of IDs.

        Args:
            instanceId (str): scan instance ID
            childData (list): list of child event rows

        Returns:
            list: [datamap, pc] where datamap is {hash: row}, pc is
                {parent_hash: [child_hashes]}.

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(childData, list):
            raise TypeError(f"childData is {type(childData)}; expected list()")

        if not childData:
            raise ValueError("childData is empty")

        # Get the first round of source IDs for the leafs
        keepGoing = True
        nextIds = list()
        datamap = dict()
        pc = dict()

        for row in childData:
            # these must be unique values!
            parentId = row[9]
            childId = row[8]
            datamap[childId] = row

            if parentId in pc:
                if childId not in pc[parentId]:
                    pc[parentId].append(childId)
            else:
                pc[parentId] = [childId]

            # parents of the leaf set
            if parentId not in nextIds:
                nextIds.append(parentId)

        while keepGoing:
            parentSet = self.scanElementSourcesDirect(instanceId, nextIds)
            nextIds = list()
            keepGoing = False

            for row in parentSet:
                parentId = row[9]
                childId = row[8]
                datamap[childId] = row

                if parentId in pc:
                    if childId not in pc[parentId]:
                        pc[parentId].append(childId)
                else:
                    pc[parentId] = [childId]
                if parentId not in nextIds:
                    nextIds.append(parentId)

                # Prevent us from looping at root
                if parentId != "ROOT":
                    keepGoing = True

        datamap[parentId] = row
        return [datamap, pc]

    def scanElementChildrenAll(self, instanceId: str, parentIds: list) -> list:
        """Get the full set of downstream IDs which are children of the supplied set of IDs.

        Args:
            instanceId (str): scan instance ID
            parentIds (list): parent event hashes to descend from

        Returns:
            list: flat list of descendant event hashes

        Raises:
            TypeError: arg type was invalid

        Note: This function is not the same as the scanElementParent* functions.
              This function returns only ids.
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(parentIds, list):
            raise TypeError(f"parentIds is {type(parentIds)}; expected list()")

        datamap = list()
        keepGoing = True
        nextIds = list()

        nextSet = self.scanElementChildrenDirect(instanceId, parentIds)
        for row in nextSet:
            datamap.append(row[8])

        for row in nextSet:
            if row[8] not in nextIds:
                nextIds.append(row[8])

        while keepGoing:
            nextSet = self.scanElementChildrenDirect(instanceId, nextIds)
            if nextSet is None or len(nextSet) == 0:
                keepGoing = False
                break

            for row in nextSet:
                datamap.append(row[8])
                nextIds = list()
                nextIds.append(row[8])

        return datamap

    def correlationResultCreate(
        self,
        instanceId: str,
        ruleId: str,
        ruleName: str,
        ruleDescr: str,
        ruleRisk: str,
        ruleYaml: str,
        correlationTitle: str,
        eventHashes: list
    ) -> str:
        """Create a correlation result in the database.

        Args:
            instanceId (str): scan instance ID
            ruleId (str): correlation rule ID
            ruleName (str): correlation rule name
            ruleDescr (str): correlation rule description
            ruleRisk (str): correlation rule risk level
            ruleYaml (str): correlation rule raw YAML
            correlationTitle (str): correlation title
            eventHashes (list): events mapped to the correlation result

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Returns:
            str: Correlation ID created
        """
        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(ruleId, str):
            raise TypeError(f"ruleId is {type(ruleId)}; expected str()")

        if not isinstance(ruleName, str):
            raise TypeError(f"ruleName is {type(ruleName)}; expected str()")

        if not isinstance(ruleDescr, str):
            raise TypeError(f"ruleDescr is {type(ruleDescr)}; expected str()")

        if not isinstance(ruleRisk, str):
            raise TypeError(f"ruleRisk is {type(ruleRisk)}; expected str()")

        if not isinstance(ruleYaml, str):
            raise TypeError(f"ruleYaml is {type(ruleYaml)}; expected str()")

        if not isinstance(correlationTitle, str):
            raise TypeError(f"correlationTitle is {type(correlationTitle)}; expected str()")

        if not isinstance(eventHashes, list):
            raise TypeError(f"eventHashes is {type(eventHashes)}; expected list()")

        uniqueId = str(hashlib.md5(str(time.time() + random.SystemRandom().randint(0, 99999999)).encode('utf-8')).hexdigest())  # noqa: DUO130

        qry = "INSERT INTO tbl_scan_correlation_results \
            (id, scan_instance_id, title, rule_name, rule_descr, rule_risk, rule_id, rule_logic) \
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"

        with self.dbhLock:
            try:
                self.dbh.execute(qry, (
                    uniqueId, instanceId, correlationTitle, ruleName, ruleDescr, ruleRisk, ruleId, ruleYaml
                ))
                self.conn.commit()
            except psycopg2.Error as e:
                self.conn.rollback()
                raise IOError("Unable to create correlation result in database") from e

        # Map events to the correlation result
        qry = "INSERT INTO tbl_scan_correlation_results_events \
            (correlation_id, event_hash) \
            VALUES (%s, %s)"

        with self.dbhLock:
            for eventHash in eventHashes:
                try:
                    self.dbh.execute(qry, (
                        uniqueId, eventHash
                    ))
                    self.conn.commit()
                except psycopg2.Error as e:
                    self.conn.rollback()
                    raise IOError("Unable to create correlation result in database") from e

        return uniqueId
