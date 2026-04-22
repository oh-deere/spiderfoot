"""Thin helper for running Alembic migrations from Python."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def _config(database_url: str) -> Config:
    """Build an Alembic ``Config`` pointing at the repo's alembic tree.

    Args:
        database_url: libpq-style Postgres URL (e.g.
            ``postgresql://u:p@h:p/db``). Written into both the
            returned config and ``SPIDERFOOT_DATABASE_URL`` so
            ``alembic/env.py`` picks it up.

    Returns:
        Config: ready-to-use Alembic config.
    """
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    os.environ["SPIDERFOOT_DATABASE_URL"] = database_url
    return cfg


def run_alembic_upgrade(database_url: str, revision: str = "head") -> None:
    """Run ``alembic upgrade <revision>`` against the given URL.

    Args:
        database_url: Postgres URL.
        revision: Alembic revision identifier. Defaults to ``head``.
    """
    command.upgrade(_config(database_url), revision)


def run_alembic_downgrade(database_url: str, revision: str = "base") -> None:
    """Run ``alembic downgrade <revision>`` against the given URL.

    Args:
        database_url: Postgres URL.
        revision: Alembic revision identifier. Defaults to ``base``
            (tears every migration down).
    """
    command.downgrade(_config(database_url), revision)
