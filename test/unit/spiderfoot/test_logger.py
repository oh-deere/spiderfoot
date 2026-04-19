# test_logger.py
import json
import logging
import unittest

from spiderfoot.logger import SpiderFootJsonFormatter


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
