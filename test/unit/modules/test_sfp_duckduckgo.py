# test_sfp_duckduckgo.py
import json
import unittest
from unittest import mock

import pytest

from modules.sfp_duckduckgo import sfp_duckduckgo
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget


def _html_with_results(results):
    blocks = []
    for href, snippet in results:
        blocks.append(
            f'<div class="result results_links results_links_deep web-result">'
            f'<a class="result__a" href="{href}">title</a>'
            f'<a class="result__snippet" href="x">{snippet}</a>'
            f'</div>'
        )
    return "<html><body>" + "".join(blocks) + "</body></html>"


def _fetch_ok(body: str) -> dict:
    return {"code": "200", "content": body, "headers": {}}


@pytest.mark.usefixtures("default_options")
class TestModuleDuckDuckGo(unittest.TestCase):

    def _module(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_duckduckgo()
        module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _domain_event(self, value="example.com"):
        root = SpiderFootEvent("ROOT", value, "", "")
        return SpiderFootEvent("INTERNET_NAME", value, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_duckduckgo()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_duckduckgo()
        self.assertEqual(set(module.watchedEvents()),
                         {"INTERNET_NAME", "DOMAIN_NAME"})
        self.assertEqual(set(module.producedEvents()), {
            "LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
            "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA",
        })

    def test_subdomain_hit_emits_internal_url_and_internet_name(self):
        body = _html_with_results([
            ("https://sub.example.com/path", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = sorted(e.eventType for e in emitted)
        self.assertIn("LINKED_URL_INTERNAL", types)
        self.assertIn("INTERNET_NAME", types)
        names = [e for e in emitted if e.eventType == "INTERNET_NAME"]
        self.assertEqual(names[0].data, "sub.example.com")

    def test_external_url_emits_external_only(self):
        body = _html_with_results([
            ("https://other.org/x", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = [e.eventType for e in emitted]
        self.assertIn("LINKED_URL_EXTERNAL", types)
        self.assertNotIn("INTERNET_NAME", types)

    def test_self_echo_emits_internal_but_no_internet_name(self):
        body = _html_with_results([
            ("https://example.com/", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = [e.eventType for e in emitted]
        self.assertIn("LINKED_URL_INTERNAL", types)
        self.assertNotIn("INTERNET_NAME", types)

    def test_email_extracted_from_snippet(self):
        body = _html_with_results([
            ("https://example.com/contact", "Reach us at dev@example.com today"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        emails = [e.data for e in emitted if e.eventType == "EMAILADDR"]
        self.assertEqual(emails, ["dev@example.com"])

    def test_uddg_redirect_unwrapped(self):
        body = (
            '<html><body><div class="result results_links results_links_deep web-result">'
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">title</a>'
            '<a class="result__snippet" href="x">snippet</a>'
            '</div></body></html>'
        )
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        urls = [e.data for e in emitted if e.eventType == "LINKED_URL_INTERNAL"]
        self.assertEqual(urls, ["https://example.com/a"])

    def test_max_pages_one_means_one_fetch(self):
        body = _html_with_results([("https://example.com/", "x")])
        _, module = self._module()
        module.opts["max_pages"] = 1
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)) as m_fetch:
            module.handleEvent(self._domain_event())
        self.assertEqual(m_fetch.call_count, 1)

    def test_anomaly_response_trips_errorstate(self):
        body = '<html><body><div class="anomaly-modal">CAPTCHA!</div></body></html>'
        _, module = self._module()
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._domain_event())
        self.assertTrue(module.errorState)
        self.assertEqual(emitted, [])
        m_error.assert_called()

    def test_http_500_trips_errorstate(self):
        _, module = self._module()
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value={"code": "500",
                                              "content": "", "headers": {}}), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._domain_event())
        self.assertTrue(module.errorState)
        self.assertEqual(emitted, [])
        m_error.assert_called()

    def test_raw_rir_data_emitted_with_parsed_results(self):
        body = _html_with_results([
            ("https://sub.example.com/a", "snippet1"),
            ("https://other.org/b", "snippet2"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        raws = [e.data for e in emitted if e.eventType == "RAW_RIR_DATA"]
        self.assertEqual(len(raws), 1)
        parsed = json.loads(raws[0])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["url"], "https://sub.example.com/a")
        self.assertEqual(parsed[0]["snippet"], "snippet1")


if __name__ == "__main__":
    unittest.main()
