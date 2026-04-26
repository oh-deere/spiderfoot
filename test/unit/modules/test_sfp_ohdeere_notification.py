# test_sfp_ohdeere_notification.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_notification import sfp_ohdeere_notification
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereNotification(unittest.TestCase):

    def _module(self, client, opts=None):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_notification()
        with mock.patch("modules.sfp_ohdeere_notification.get_client",
                        return_value=client):
            module.setup(sf, opts or {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        module.setScanId("scan-abc-123")
        return sf, module

    def _root_event(self, target="example.com"):
        return SpiderFootEvent("ROOT", target, "", "")

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_notification()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_notification()
        self.assertEqual(module.watchedEvents(), ["ROOT"])
        self.assertEqual(module.producedEvents(), [])

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        client.post.assert_not_called()

    def test_root_event_fires_start_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event(target="example.com"))
        self.assertEqual(client.post.call_count, 1)
        call = client.post.call_args
        body = call.kwargs.get("body", call.args[1] if len(call.args) > 1 else None)
        self.assertIn("Scan started", body["text"])
        self.assertIn("example.com", body["text"])
        self.assertIn("\U0001F50E", body["text"])

    def test_duplicate_root_events_single_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.handleEvent(self._root_event())
        self.assertEqual(client.post.call_count, 1)

    def test_finish_fires_complete_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        self.assertEqual(client.post.call_count, 2)
        complete_call = client.post.call_args_list[1]
        body = complete_call.kwargs.get("body",
                                        complete_call.args[1] if len(complete_call.args) > 1 else None)
        self.assertIn("Scan completed", body["text"])
        self.assertIn("\u2705", body["text"])

    def test_duplicate_finish_single_complete_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        module.finish()
        module.finish()
        self.assertEqual(client.post.call_count, 2)

    def test_ui_url_configured_includes_scan_link(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={
            "spiderfoot_ui_url": "https://spiderfoot.example.test",
        })
        module.handleEvent(self._root_event())
        body = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertIn(
            "https://spiderfoot.example.test/scaninfo?id=scan-abc-123",
            body["text"],
        )

    def test_slack_channel_configured_included_in_payload(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={"slack_channel": "shootingstar"})
        module.handleEvent(self._root_event())
        body = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertEqual(body["channel"], "shootingstar")

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        with mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._root_event())
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def _attach_db(self, module, instance=None, events=None, correlations=None):
        db = mock.MagicMock()
        db.scanInstanceGet.return_value = instance if instance is not None else [
            "scan-name", "example.com",
            1700000000.0,
            1700000000.0,
            1700000090.0,
            "FINISHED",
        ]
        db.scanResultEvent.return_value = events if events is not None else []
        db.scanCorrelationList.return_value = (
            correlations if correlations is not None else []
        )
        module._SpiderFootPlugin__sfdb__ = db
        return db

    def _completion_body(self, client):
        complete_call = client.post.call_args_list[1]
        return complete_call.kwargs.get(
            "body",
            complete_call.args[1] if len(complete_call.args) > 1 else None,
        )

    def test_rich_completion_includes_duration_total_top_types_top_findings(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        events = [
            ("h1", "sub.example.com", "example.com", "mod_a", "INTERNET_NAME"),
            ("h2", "alt.example.com", "example.com", "mod_a", "INTERNET_NAME"),
            ("h3", "x.example.com",   "example.com", "mod_a", "INTERNET_NAME"),
            ("h4", "a@example.com",   "example.com", "mod_b", "EMAILADDR"),
            ("h5", "b@example.com",   "example.com", "mod_b", "EMAILADDR"),
            ("h6", "https://example.com/", "example.com", "mod_c",
             "LINKED_URL_INTERNAL"),
        ]
        correlations = [
            (1, "Subdomain Takeover", "rule_st", "HIGH", "ST", "...", "...", 2),
            (2, "Open Email", "rule_oe", "MEDIUM", "OE", "...", "...", 1),
        ]
        self._attach_db(module, events=events, correlations=correlations)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertIn("*Duration:* 1m 30s", text)
        self.assertIn("*Events:* 6", text)
        self.assertIn("*Top event types:*", text)
        self.assertIn("INTERNET_NAME: 3", text)
        self.assertIn("EMAILADDR: 2", text)
        self.assertIn("*Top findings:*", text)
        self.assertIn("[HIGH] Subdomain Takeover", text)
        self.assertIn("[MEDIUM] Open Email", text)

    def test_top_findings_capped_at_five_and_sorted_by_risk(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        correlations = [
            (i, f"Finding {i}", "r", risk, "n", "d", "l", 1)
            for i, risk in enumerate([
                "LOW", "HIGH", "INFO", "MEDIUM", "HIGH",
                "LOW", "MEDIUM", "HIGH", "INFO", "LOW",
            ])
        ]
        self._attach_db(module, correlations=correlations)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        self.assertEqual(text.count("[HIGH]"), 3)
        self.assertEqual(text.count("[MEDIUM]"), 2)
        self.assertEqual(text.count("[LOW]"), 0)
        self.assertEqual(text.count("[INFO]"), 0)

    def test_empty_scan_emits_zero_events_no_sections(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        self._attach_db(module, events=[], correlations=[])
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertIn("*Events:* 0", text)
        self.assertNotIn("*Top event types:*", text)
        self.assertNotIn("*Top findings:*", text)

    def test_db_failure_falls_back_to_terse_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()

        self.assertEqual(client.post.call_count, 2)
        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertNotIn("*Duration:*", text)
        self.assertNotIn("*Events:*", text)
        self.assertFalse(module.errorState)

    def test_db_raises_falls_back_to_terse_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        db = mock.MagicMock()
        db.scanInstanceGet.side_effect = RuntimeError("db down")
        module._SpiderFootPlugin__sfdb__ = db
        module.handleEvent(self._root_event())
        module.finish()

        self.assertEqual(client.post.call_count, 2)
        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertNotIn("*Duration:*", text)
        self.assertFalse(module.errorState)

    def test_start_notification_unchanged_and_no_db_queries(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        db = self._attach_db(module)
        module.handleEvent(self._root_event())

        start_body = client.post.call_args_list[0].kwargs.get(
            "body", client.post.call_args_list[0].args[1])
        self.assertIn("\U0001F50E Scan started for example.com",
                      start_body["text"])
        db.scanInstanceGet.assert_not_called()
        db.scanResultEvent.assert_not_called()
        db.scanCorrelationList.assert_not_called()

    def test_ui_url_link_appended_to_first_line_in_rich_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={
            "spiderfoot_ui_url": "https://spiderfoot.example.test",
        })
        events = [("h1", "x", "y", "m", "INTERNET_NAME")]
        self._attach_db(module, events=events)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        first_line = text.splitlines()[0]
        self.assertIn(
            "https://spiderfoot.example.test/scaninfo?id=scan-abc-123",
            first_line,
        )
