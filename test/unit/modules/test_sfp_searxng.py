# test_sfp_searxng.py
import json
from unittest import mock

import pytest
import unittest

from modules.sfp_searxng import sfp_searxng
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget


def _fetch_ok(body: dict) -> dict:
    return {"code": "200", "content": json.dumps(body), "headers": {}}


def _fetch_status(code: str, body: str = "") -> dict:
    return {"code": code, "content": body, "headers": {}}


@pytest.mark.usefixtures("default_options")
class TestModuleSearxng(unittest.TestCase):

    def _module(self, url: str = "https://searxng.example.test"):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": url})
        target = SpiderFootTarget("example.com", "INTERNET_NAME")
        module.setTarget(target)
        return sf, module, target

    def _root_event(self):
        return SpiderFootEvent("ROOT", "example.com", "", "")

    def _domain_event(self, parent):
        return SpiderFootEvent("INTERNET_NAME", "example.com", "test_mod", parent)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_searxng()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events_are_lists(self):
        module = sfp_searxng()
        self.assertIsInstance(module.watchedEvents(), list)
        self.assertIsInstance(module.producedEvents(), list)
        self.assertIn("INTERNET_NAME", module.watchedEvents())
        self.assertIn("DOMAIN_NAME", module.watchedEvents())
        for t in ("LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
                  "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_empty_searxng_url_silently_no_ops(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": ""})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        evt = self._domain_event(self._root_event())

        with mock.patch.object(sf, "fetchUrl") as m_fetch, \
             mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(evt)

        m_fetch.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_internal_external_email_subdomain_raw(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        body = {
            "results": [
                {"url": "https://api.example.com/health", "title": "",
                 "content": "operator contact admin@example.com"},
                {"url": "https://other.org/mentions-example", "title": "",
                 "content": "example.com was mentioned"},
            ]
        }
        emissions = []
        with mock.patch.object(sf, "fetchUrl", return_value=_fetch_ok(body)), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)

        types_emitted = [e.eventType for e in emissions]
        self.assertEqual(types_emitted.count("LINKED_URL_INTERNAL"), 1)
        self.assertEqual(types_emitted.count("LINKED_URL_EXTERNAL"), 1)
        self.assertEqual(types_emitted.count("INTERNET_NAME"), 1)  # api.example.com
        self.assertEqual(types_emitted.count("EMAILADDR"), 1)
        self.assertEqual(types_emitted.count("RAW_RIR_DATA"), 1)

    def test_dedup_same_event_queried_only_once(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})) as m_fetch, \
             mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)  # same data → should dedup
        self.assertEqual(m_fetch.call_count, 1)

    def test_max_pages_triggers_multiple_fetches(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": "https://searxng.example.test",
                          "max_pages": 3})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})) as m_fetch, \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        self.assertEqual(m_fetch.call_count, 3)
        # three RAW_RIR_DATA events (one per page) even with empty results
        self.assertEqual(sum(1 for e in emissions
                             if e.eventType == "RAW_RIR_DATA"), 3)

    def test_http_500_logs_error_and_emits_nothing(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_status("500")), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(evt)
        self.assertEqual(emissions, [])
        m_error.assert_called()

    def test_malformed_json_logs_error_and_emits_nothing(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value={"code": "200",
                                             "content": "not-json",
                                             "headers": {}}), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(evt)
        self.assertEqual(emissions, [])
        m_error.assert_called()

    def test_empty_results_emits_only_raw_rir_data(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        types_emitted = [e.eventType for e in emissions]
        self.assertEqual(types_emitted, ["RAW_RIR_DATA"])

    def test_email_regex_extracts_multiple_addresses_from_snippet(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        body = {
            "results": [
                {"url": "https://example.com/contact",
                 "title": "",
                 "content": "Reach foo@example.com or bar+baz@other.org today."},
            ]
        }
        emissions = []
        with mock.patch.object(sf, "fetchUrl", return_value=_fetch_ok(body)), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        emails = sorted(e.data for e in emissions if e.eventType == "EMAILADDR")
        self.assertEqual(emails, ["bar+baz@other.org", "foo@example.com"])
