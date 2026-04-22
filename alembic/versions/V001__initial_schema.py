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
            guid        VARCHAR NOT NULL PRIMARY KEY,
            name        VARCHAR NOT NULL,
            seed_target VARCHAR NOT NULL,
            created     BIGINT DEFAULT 0,
            started     BIGINT DEFAULT 0,
            ended       BIGINT DEFAULT 0,
            status      VARCHAR NOT NULL
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
            scan_instance_id  VARCHAR NOT NULL REFERENCES tbl_scan_instance(guid),
            hash              VARCHAR NOT NULL,
            type              VARCHAR NOT NULL REFERENCES tbl_event_types(event),
            generated         BIGINT NOT NULL,
            confidence        INTEGER NOT NULL DEFAULT 100,
            visibility        INTEGER NOT NULL DEFAULT 100,
            risk              INTEGER NOT NULL DEFAULT 0,
            module            VARCHAR NOT NULL,
            data              VARCHAR,
            false_positive    INTEGER NOT NULL DEFAULT 0,
            source_event_hash VARCHAR DEFAULT 'ROOT'
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
