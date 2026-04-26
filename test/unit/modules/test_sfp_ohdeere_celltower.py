# test_sfp_ohdeere_celltower.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_celltower import sfp_ohdeere_celltower
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
)


_RESOLVE_CELL = {
    "mcc": 240, "mnc": 1, "lac": 12345, "cid": 67890,
    "radio": "GSM", "lon": 18.0686, "lat": 59.3293,
    "rangeM": 1500, "samples": 234, "changeable": False,
    "firstSeen": "2020-01-01T00:00:00Z",
    "lastSeen": "2024-12-31T00:00:00Z",
    "averageSignal": -85,
}

_NEARBY_RESPONSE = [
    {
        "cell": {
            "mcc": 240, "mnc": 1, "lac": 100, "cid": 42,
            "radio": "LTE", "lon": 18.0686, "lat": 59.3293,
            "rangeM": 1000, "samples": 10,
        },
        "distanceMeters": 123.4,
    },
    {
        "cell": {
            "mcc": 240, "mnc": 2, "lac": 100, "cid": 99,
            "radio": "GSM", "lon": 18.07, "lat": 59.33,
            "rangeM": 800, "samples": 5,
        },
        "distanceMeters": 250.0,
    },
]


def _fake_get_routing(cgi_record=None, nearby=None):
    def fake(path, **_kwargs):
        if "/cgi/nearby" in path:
            return [] if nearby is None else nearby
        if "/cgi/" in path:
            return cgi_record
        return None
    return fake


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereCelltower(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_celltower()
        with mock.patch("modules.sfp_ohdeere_celltower.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_celltower()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_celltower()
        self.assertEqual(set(module.watchedEvents()),
                         {"PHYSICAL_COORDINATES", "CGI_TOWER"})
        self.assertEqual(set(module.producedEvents()),
                         {"GEOINFO", "RAW_RIR_DATA", "PHYSICAL_COORDINATES"})

    def test_path_a_nearby_emits_per_tower_geoinfo_and_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("59.3293,18.0686", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)
        url = nearby_calls[0].args[0]
        self.assertIn("lat=59.33", url)
        self.assertIn("lon=18.07", url)
        self.assertIn("radius_m=5000", url)

        geos = [e for e in emitted if e.eventType == "GEOINFO"]
        self.assertEqual(len(geos), 2)
        self.assertIn("Cell tower [LTE] 240/1/100/42", geos[0].data)
        self.assertIn("range ~1000m", geos[0].data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.3293/18.0686</SFURL>",
            geos[0].data,
        )

        raws = [e for e in emitted if e.eventType == "RAW_RIR_DATA"]
        self.assertEqual(len(raws), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.33/18.07</SFURL>",
            raws[0].data,
        )

    def test_path_a_strips_sfurl_suffix_from_coord_input(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        coord = "59.3293,18.0686\n<SFURL>https://x</SFURL>"
        module.handleEvent(self._event(coord, "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)

    def test_path_a_cache_hit_skips_second_api_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("59.3293,18.0686", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("59.3299,18.0691", "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)

    def test_path_a_cap_drops_after_threshold(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.opts["nearby_max_unique_cells_per_scan"] = 2
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("59.33,18.07", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("40.71,-74.00", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("51.50,-0.12", "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 2)

    def test_path_b_resolve_emits_coords_geoinfo_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(cgi_record=_RESOLVE_CELL)
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))

        resolve_calls = [c for c in client.get.call_args_list
                         if "/cgi/240/1/12345/67890" in c.args[0]]
        self.assertEqual(len(resolve_calls), 1)

        types = [e.eventType for e in emitted]
        self.assertIn("PHYSICAL_COORDINATES", types)
        self.assertIn("GEOINFO", types)
        self.assertIn("RAW_RIR_DATA", types)

        coord = next(e for e in emitted if e.eventType == "PHYSICAL_COORDINATES")
        self.assertIn("59.3293,18.0686", coord.data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.3293/18.0686</SFURL>",
            coord.data,
        )

        geo = next(e for e in emitted if e.eventType == "GEOINFO")
        self.assertIn("Cell tower [GSM] 240/1/12345/67890", geo.data)
        self.assertIn("range ~1500m", geo.data)

    def test_path_b_unknown_cgi_404_no_emissions_no_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereClientError(
            "404 on GET https://celltower.ohdeere.internal/api/v1/cgi/240/1/0/0: "
        )
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("240,1,0,0", "CGI_TOWER"))
        self.assertEqual(emitted, [])
        self.assertFalse(module.errorState)

    def test_path_b_malformed_cgi_input_skipped(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("240,1,nope", "CGI_TOWER"))
        client.get.assert_not_called()
        self.assertEqual(emitted, [])
        self.assertFalse(module.errorState)

    def test_path_b_input_dedup(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(cgi_record=_RESOLVE_CELL)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))
        resolve_calls = [c for c in client.get.call_args_list
                         if "/cgi/240/1/12345/67890" in c.args[0]]
        self.assertEqual(len(resolve_calls), 1)

    def test_auth_error_trips_errorstate_and_short_circuits(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._event("59.33,18.07", "PHYSICAL_COORDINATES"))
            module.handleEvent(self._event("40.71,-74.00", "PHYSICAL_COORDINATES"))
        self.assertTrue(module.errorState)
        self.assertEqual(client.get.call_count, 1)
