# test_sfp_holehe.py
import unittest
from unittest import mock

import pytest

from modules.sfp_holehe import sfp_holehe
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.holehe_runner import HoleheHit


@pytest.mark.usefixtures("default_options")
class TestModuleHolehe(unittest.TestCase):

    def _module(self, **opt_overrides):
        sf = SpiderFoot(self.default_options)
        module = sfp_holehe()
        module.setup(sf, dict(opt_overrides))
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _email_event(self, data="user@example.com"):
        root = SpiderFootEvent("ROOT", "example.com", "", "")
        return SpiderFootEvent("EMAILADDR", data, "test_module", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_holehe()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watches_emailaddr_only(self):
        _, module = self._module()
        self.assertEqual(module.watchedEvents(), ["EMAILADDR"])

    def test_produces_account_external_owned(self):
        _, module = self._module()
        self.assertEqual(module.producedEvents(), ["ACCOUNT_EXTERNAL_OWNED"])

    def test_max_emails_caps_probing(self):
        _, module = self._module(max_emails=2)
        with mock.patch("modules.sfp_holehe.probe_email",
                        return_value=[]) as p:
            for _ in range(5):
                module.handleEvent(self._email_event())
        self.assertEqual(p.call_count, 2)

    def test_hit_emits_account_external_owned_with_expected_format(self):
        _, module = self._module()
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            return_value=[HoleheHit(provider="github", domain="github.com")],
        ):
            module.handleEvent(self._email_event())
        self.assertEqual(len(emitted), 1)
        evt = emitted[0]
        self.assertEqual(evt.eventType, "ACCOUNT_EXTERNAL_OWNED")
        self.assertEqual(
            evt.data,
            "Holehe: github (Domain: github.com)\n"
            "<SFURL>https://github.com</SFURL>",
        )

    def test_skip_providers_opt_forwarded_to_runner(self):
        _, module = self._module(skip_providers="foo, bar")
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            return_value=[],
        ) as p:
            module.handleEvent(self._email_event())
        kwargs = p.call_args.kwargs
        self.assertEqual(kwargs["skip"], {"foo", "bar"})

    def test_runner_exception_trips_errorstate(self):
        _, module = self._module()
        with mock.patch(
            "modules.sfp_holehe.probe_email",
            side_effect=RuntimeError("boom"),
        ) as p:
            module.handleEvent(self._email_event())
            module.handleEvent(self._email_event())
        self.assertTrue(module.errorState)
        self.assertEqual(p.call_count, 1)


if __name__ == "__main__":
    unittest.main()
