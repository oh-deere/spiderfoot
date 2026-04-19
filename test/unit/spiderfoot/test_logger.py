# test_logger.py
import json
import logging
import os
import unittest
from unittest import mock

from spiderfoot.logger import (
    SpiderFootJsonFormatter,
    _log_files_enabled,
    _should_use_json,
)


def _make_record(msg="hello", level=logging.INFO, extras=None, exc_info=None):
    record = logging.LogRecord(
        name="spiderfoot.sflib",
        level=level,
        pathname="/src/spiderfoot/sflib.py",
        lineno=42,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    if extras:
        for k, v in extras.items():
            setattr(record, k, v)
    return record


class TestSpiderFootJsonFormatter(unittest.TestCase):

    def test_json_formatter_contains_standard_fields(self):
        formatter = SpiderFootJsonFormatter()
        record = _make_record(msg="Scan [abc123] completed.",
                              extras={"scanId": "abc123"})
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "spiderfoot.sflib")
        self.assertEqual(parsed["message"], "Scan [abc123] completed.")
        self.assertEqual(parsed["module"], "sflib")
        self.assertEqual(parsed["scanId"], "abc123")
        self.assertIn("timestamp", parsed)
        # RFC3339 with millisecond precision ending in Z
        self.assertTrue(parsed["timestamp"].endswith("Z"))
        self.assertRegex(parsed["timestamp"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    def test_json_formatter_omits_scanid_when_absent(self):
        formatter = SpiderFootJsonFormatter()
        record = _make_record()  # no scanId extra
        parsed = json.loads(formatter.format(record))
        self.assertNotIn("scanId", parsed)

    def test_json_formatter_includes_exception(self):
        formatter = SpiderFootJsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = _make_record(msg="it failed", level=logging.ERROR,
                              exc_info=exc_info)
        parsed = json.loads(formatter.format(record))
        self.assertIn("exception", parsed)
        self.assertIn("ValueError: boom", parsed["exception"])
        self.assertIn("Traceback", parsed["exception"])

    def test_json_formatter_handles_non_serializable_extras(self):
        formatter = SpiderFootJsonFormatter()

        class Opaque:
            def __str__(self):
                return "opaque-value"

        record = _make_record(extras={"scanId": Opaque()})
        # Should not raise — falls back to str() via default=str
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["scanId"], "opaque-value")


class TestShouldUseJson(unittest.TestCase):

    def _run(self, env_value, isatty_value):
        env = {} if env_value is None else {"SPIDERFOOT_LOG_FORMAT": env_value}
        with mock.patch.dict("os.environ", env, clear=False):
            if env_value is None:
                # Ensure the var is absent even if the outer env had it.
                os_env_backup = os.environ.pop("SPIDERFOOT_LOG_FORMAT", None)
                try:
                    with mock.patch("sys.stdout.isatty", return_value=isatty_value):
                        return _should_use_json()
                finally:
                    if os_env_backup is not None:
                        os.environ["SPIDERFOOT_LOG_FORMAT"] = os_env_backup
            else:
                with mock.patch("sys.stdout.isatty", return_value=isatty_value):
                    return _should_use_json()

    def test_env_json_forces_json(self):
        self.assertTrue(self._run("json", isatty_value=True))
        self.assertTrue(self._run("json", isatty_value=False))

    def test_env_text_forces_text(self):
        self.assertFalse(self._run("text", isatty_value=True))
        self.assertFalse(self._run("text", isatty_value=False))

    def test_env_unset_follows_tty(self):
        # Interactive terminal → text
        self.assertFalse(self._run(None, isatty_value=True))
        # Pipe/container → json
        self.assertTrue(self._run(None, isatty_value=False))

    def test_env_bogus_value_falls_through_to_tty(self):
        self.assertFalse(self._run("garbage", isatty_value=True))
        self.assertTrue(self._run("garbage", isatty_value=False))


class TestLogFilesEnabled(unittest.TestCase):

    def _run(self, env_value):
        env = {} if env_value is None else {"SPIDERFOOT_LOG_FILES": env_value}
        with mock.patch.dict("os.environ", env, clear=False):
            if env_value is None:
                os.environ.pop("SPIDERFOOT_LOG_FILES", None)
            return _log_files_enabled()

    def test_unset_defaults_to_enabled(self):
        self.assertTrue(self._run(None))

    def test_explicit_true(self):
        self.assertTrue(self._run("true"))
        self.assertTrue(self._run("TRUE"))
        self.assertTrue(self._run("anything-that-is-not-false"))

    def test_explicit_false(self):
        self.assertFalse(self._run("false"))
        self.assertFalse(self._run("False"))
        self.assertFalse(self._run("FALSE"))
