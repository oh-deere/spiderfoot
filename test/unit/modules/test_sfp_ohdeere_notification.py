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
