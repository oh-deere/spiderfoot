# test_sfp_ohdeere_wiki.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_wiki import sfp_ohdeere_wiki
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError


_WIKI_RESPONSE = {
    "results": [
        {
            "title": "Acme Corporation",
            "path": "A/Acme_Corporation",
            "bookName": "wikipedia_en_all_maxi",
            "snippet": "Acme Corporation is a fictional company used as an archetype.",
        }
    ]
}


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereWiki(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_wiki()
        with mock.patch("modules.sfp_ohdeere_wiki.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype="COMPANY_NAME"):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_wiki()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_wiki()
        self.assertEqual(set(module.watchedEvents()),
                         {"COMPANY_NAME", "HUMAN_NAME"})
        for t in ("DESCRIPTION_ABSTRACT", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._event("Acme Corporation"))
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_description_abstract_and_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _WIKI_RESPONSE
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event("Acme Corporation"))
        types = [e.eventType for e in emissions]
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(types.count("DESCRIPTION_ABSTRACT"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(
            data_by_type["DESCRIPTION_ABSTRACT"],
            "Acme Corporation is a fictional company used as an archetype.",
        )

    def test_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = {"results": []}
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(self._event("Unknown Entity"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("DESCRIPTION_ABSTRACT", types)
        self.assertIn("RAW_RIR_DATA", types)
        m_debug.assert_called()

    def test_result_without_snippet_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = {
            "results": [{"title": "Acme", "path": "A/Acme", "bookName": "w"}]
        }
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event("Acme"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("DESCRIPTION_ABSTRACT", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event("Acme"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()
