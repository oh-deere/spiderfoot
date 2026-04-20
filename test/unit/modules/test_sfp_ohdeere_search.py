# test_sfp_ohdeere_search.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_search import sfp_ohdeere_search
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError, OhDeereServerError


def _search_response(results):
    return {
        "query": "site:example.com",
        "results": results,
        "answers": [],
        "suggestions": [],
        "infoboxes": [],
        "number_of_results": len(results),
    }


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereSearch(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_search()
        with mock.patch("modules.sfp_ohdeere_search.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data="example.com", etype="INTERNET_NAME"):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_search()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_search()
        self.assertEqual(set(module.watchedEvents()),
                         {"INTERNET_NAME", "DOMAIN_NAME"})
        for t in ("LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
                  "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._event())
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_all_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([
            {"url": "https://api.example.com/health", "title": "",
             "content": "contact admin@example.com"},
            {"url": "https://other.org/example-ref", "title": "",
             "content": "example.com was mentioned here"},
        ])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("LINKED_URL_INTERNAL"), 1)
        self.assertEqual(types.count("LINKED_URL_EXTERNAL"), 1)
        self.assertEqual(types.count("INTERNET_NAME"), 1)
        self.assertEqual(types.count("EMAILADDR"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)

    def test_dedup_same_input_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([])
        _, module = self._module(client)
        evt = self._event()
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types, ["RAW_RIR_DATA"])

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_server_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_errorstate_short_circuits_next_event(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._event(data="example.com"))
            module.handleEvent(self._event(data="other.example.com"))
        self.assertEqual(client.get.call_count, 1)

    def test_subdomain_discovery_emits_new_internet_name(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([
            {"url": "https://newhost.example.com/page", "title": "",
             "content": ""},
        ])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        hosts = [e.data for e in emissions if e.eventType == "INTERNET_NAME"]
        self.assertIn("LINKED_URL_INTERNAL", types)
        self.assertEqual(hosts, ["newhost.example.com"])
