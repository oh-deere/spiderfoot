# test_sfp_ohdeere_geoip.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_geoip import sfp_ohdeere_geoip
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereServerError,
)


def _full_payload():
    return {
        "ip": "1.2.3.4",
        "country": {"iso_code": "US", "name": "United States"},
        "city": {"name": "San Francisco"},
        "location": {"lat": 37.77, "lon": -122.42, "accuracy_radius_km": 10},
        "asn": {"number": 13335, "org": "Cloudflare, Inc."},
    }


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereGeoip(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_geoip()
        # Patch get_client before setup so the module binds to the stub.
        with mock.patch("modules.sfp_ohdeere_geoip.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("1.2.3.4", "IP_ADDRESS"))
        return sf, module

    def _ip_event(self, value="1.2.3.4", etype="IP_ADDRESS"):
        root = SpiderFootEvent("ROOT", value, "", "")
        return SpiderFootEvent(etype, value, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_geoip()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_geoip()
        self.assertEqual(set(module.watchedEvents()),
                         {"IP_ADDRESS", "IPV6_ADDRESS"})
        for t in ("COUNTRY_NAME", "GEOINFO", "PHYSICAL_COORDINATES",
                  "BGP_AS_OWNER", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        sf, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._ip_event())
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_all_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _full_payload()
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("COUNTRY_NAME"), 1)
        self.assertEqual(types.count("GEOINFO"), 1)
        self.assertEqual(types.count("PHYSICAL_COORDINATES"), 1)
        self.assertEqual(types.count("BGP_AS_OWNER"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["COUNTRY_NAME"], "United States")
        self.assertEqual(data_by_type["GEOINFO"], "San Francisco, United States")
        self.assertIn("37.77,-122.42", data_by_type["PHYSICAL_COORDINATES"])
        self.assertEqual(data_by_type["BGP_AS_OWNER"], "Cloudflare, Inc.")

    def test_nullable_country_skips_country_and_geoinfo(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["country"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("COUNTRY_NAME", types)
        self.assertNotIn("GEOINFO", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_nullable_location_skips_physical_coordinates(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["location"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_COORDINATES", types)

    def test_nullable_asn_skips_bgp_as_owner(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["asn"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("BGP_AS_OWNER", types)

    def test_dedup_same_ip_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _full_payload()
        sf, module = self._module(client)
        evt = self._ip_event()
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_auth_error_sets_errorstate_and_logs(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._ip_event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_server_error_sets_errorstate_and_logs(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503 maxmind")
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._ip_event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_ipv6_event_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        ipv6_payload = _full_payload()
        ipv6_payload["ip"] = "2606:4700::1111"
        client.get.return_value = ipv6_payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event(value="2606:4700::1111",
                                              etype="IPV6_ADDRESS"))
        types = [e.eventType for e in emissions]
        self.assertIn("COUNTRY_NAME", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_errorstate_short_circuits_subsequent_events(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        sf, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._ip_event(value="1.2.3.4"))
            module.handleEvent(self._ip_event(value="5.6.7.8"))
        self.assertEqual(client.get.call_count, 1)

    def test_physical_coordinates_carries_maps_deeplink(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _full_payload()
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._ip_event())
        coord_events = [e for e in emitted
                        if e.eventType == "PHYSICAL_COORDINATES"]
        self.assertEqual(len(coord_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            coord_events[0].data,
        )
