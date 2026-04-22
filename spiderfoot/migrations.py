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
    os.environ["SPIDERFOOT_DATABASE_URL"] = database_url
    return cfg


def run_alembic_upgrade(database_url: str, revision: str = "head") -> None:
    """Run alembic upgrade <revision> against the given URL."""
    command.upgrade(_config(database_url), revision)


def run_alembic_downgrade(database_url: str, revision: str = "base") -> None:
    """Run alembic downgrade <revision> (default: tear everything down)."""
    command.downgrade(_config(database_url), revision)
