# test_sfp_ohdeere_maps.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_maps import sfp_ohdeere_maps
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereServerError,
)


_REVERSE_FULL = {
    "place_id": 12345,
    "lat": "37.77",
    "lon": "-122.42",
    "display_name": "1 Market St, San Francisco, CA, United States",
    "address": {
        "road": "1 Market St",
        "city": "San Francisco",
        "state": "CA",
        "postcode": "94105",
        "country": "United States",
        "country_code": "us",
    },
}


_FORWARD_FULL = [
    {
        "place_id": 67890,
        "lat": "37.77",
        "lon": "-122.42",
        "display_name": "1 Market St, San Francisco, CA, United States",
    }
]


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereMaps(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_maps()
        with mock.patch("modules.sfp_ohdeere_maps.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_maps()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_maps()
        self.assertEqual(set(module.watchedEvents()),
                         {"PHYSICAL_COORDINATES", "PHYSICAL_ADDRESS"})
        for t in ("PHYSICAL_ADDRESS", "PHYSICAL_COORDINATES",
                  "COUNTRY_NAME", "GEOINFO", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        evt = self._event("37.77,-122.42", "PHYSICAL_COORDINATES")
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(evt)
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_reverse_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("PHYSICAL_ADDRESS"), 1)
        self.assertEqual(types.count("COUNTRY_NAME"), 1)
        self.assertEqual(types.count("GEOINFO"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(
            data_by_type["PHYSICAL_ADDRESS"],
            "1 Market St, San Francisco, CA, United States")
        self.assertEqual(data_by_type["COUNTRY_NAME"], "United States")
        self.assertEqual(data_by_type["GEOINFO"],
                         "San Francisco, United States")

    def test_reverse_no_display_name_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = dict(_REVERSE_FULL)
        payload.pop("display_name")
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_ADDRESS", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_reverse_city_fallback_to_town(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = {
            "display_name": "Some Road, Smalltown, United States",
            "address": {
                "town": "Smalltown",
                "country": "United States",
            },
        }
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("40.0,-80.0", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["GEOINFO"], "Smalltown, United States")

    def test_reverse_no_city_falls_back_to_country_only(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = {
            "display_name": "Antarctica",
            "address": {"country": "Antarctica"},
        }
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("-75.0,0.0", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["GEOINFO"], "Antarctica")

    def test_reverse_malformed_coords_skipped_without_api_call(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(
                self._event("not-a-number", "PHYSICAL_COORDINATES"))
        client.get.assert_not_called()
        m_notify.assert_not_called()
        m_debug.assert_called()

    def test_forward_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _FORWARD_FULL
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("1 Market St, San Francisco",
                            "PHYSICAL_ADDRESS"))
        types = [e.eventType for e in emissions]
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(types.count("PHYSICAL_COORDINATES"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(data_by_type["PHYSICAL_COORDINATES"], "37.77,-122.42")

    def test_forward_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = []
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(
                self._event("Unknown Place, Nowhere", "PHYSICAL_ADDRESS"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_COORDINATES", types)
        self.assertIn("RAW_RIR_DATA", types)
        m_debug.assert_called()

    def test_dedup_same_input_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        _, module = self._module(client)
        evt = self._event("37.77,-122.42", "PHYSICAL_COORDINATES")
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_reverse_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_forward_server_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503 upstream")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(
                self._event("1 Market St", "PHYSICAL_ADDRESS"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_errorstate_short_circuits_both_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
            module.handleEvent(
                self._event("1 Market St", "PHYSICAL_ADDRESS"))
        self.assertEqual(client.get.call_count, 1)
