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


_NEARBY_RESPONSE = [
    {
        "place_id": 1,
        "lat": "37.7700",
        "lon": "-122.4200",
        "display_name": "Operakällaren, San Francisco",
        "class": "amenity",
        "type": "restaurant",
    },
    {
        "place_id": 2,
        "lat": "37.7799",
        "lon": "-122.4199",
        "display_name": "Civic Center BART Station, San Francisco",
        "class": "railway",
        "type": "station",
    },
]


def _fake_get_routing(reverse=None, geocode=None, nearby=None):
    def fake(path, **_kwargs):
        if "/reverse" in path:
            return reverse
        if "/geocode" in path:
            return geocode
        if "/nearby" in path:
            return [] if nearby is None else nearby
        return None
    return fake


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
        # /reverse emits one RAW_RIR_DATA; /nearby emits another (empty list
        # here — mock has no /nearby-shaped response). Count is two.
        self.assertEqual(types.count("RAW_RIR_DATA"), 2)
        self.assertIn(
            "1 Market St, San Francisco, CA, United States",
            data_by_type["PHYSICAL_ADDRESS"])
        self.assertEqual(data_by_type["COUNTRY_NAME"], "United States")
        self.assertIn("San Francisco, United States",
                      data_by_type["GEOINFO"])

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
        self.assertIn("Smalltown, United States", data_by_type["GEOINFO"])

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
        self.assertIn("Antarctica", data_by_type["GEOINFO"])

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
        self.assertIn("37.77,-122.42", data_by_type["PHYSICAL_COORDINATES"])

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
        # First event triggers /reverse + /nearby (two calls); second event
        # short-circuits in _seen for /reverse and in _nearby_cells for /nearby.
        self.assertEqual(client.get.call_count, 2)

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

    def test_reverse_geocode_appends_maps_deeplink_to_address(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        addr_events = [e for e in emitted if e.eventType == "PHYSICAL_ADDRESS"]
        self.assertEqual(len(addr_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            addr_events[0].data,
        )

    def test_forward_geocode_appends_maps_deeplink_to_coordinates(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _FORWARD_FULL
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(
            self._event("1 Market St, San Francisco", "PHYSICAL_ADDRESS"),
        )
        coord_events = [e for e in emitted if e.eventType == "PHYSICAL_COORDINATES"]
        self.assertEqual(len(coord_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            coord_events[0].data,
        )

    def test_nearby_emits_per_poi_geoinfo_and_one_raw_rir_data(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(
            reverse=_REVERSE_FULL, nearby=_NEARBY_RESPONSE,
        )
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)
        url = nearby_calls[0].args[0]
        self.assertIn("lat=37.77", url)
        self.assertIn("lon=-122.42", url)
        self.assertIn("radius_m=1000", url)
        self.assertIn("limit=10", url)

        geos = [e for e in emitted if e.eventType == "GEOINFO"
                and "Operakällaren" in e.data]
        self.assertEqual(len(geos), 1)
        self.assertIn("amenity:restaurant", geos[0].data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            geos[0].data,
        )

        nearby_raws = [e for e in emitted if e.eventType == "RAW_RIR_DATA"
                       and "Operakällaren" in e.data]
        self.assertEqual(len(nearby_raws), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            nearby_raws[0].data,
        )
