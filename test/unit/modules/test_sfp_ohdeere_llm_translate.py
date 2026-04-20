# test_sfp_ohdeere_llm_translate.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_llm_translate import sfp_ohdeere_llm_translate
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_llm import OhDeereLLMFailure


_ENGLISH_TEXT = (
    "The quick brown fox jumps over the lazy dog. This is a test for "
    "the stopword heuristic — the words 'the', 'and', 'is' appear here."
)

_SWEDISH_TEXT = (
    "Den snabba bruna räven hoppar över den lata hunden. Detta är ett "
    "test på en icke-engelsk text som saknar engelska stoppord."
)


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereLLMTranslate(unittest.TestCase):

    def _module(self, client, opts=None):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_llm_translate()
        with mock.patch("modules.sfp_ohdeere_llm_translate.get_client",
                        return_value=client):
            module.setup(sf, opts or {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype="LEAKSITE_CONTENT"):
        root = SpiderFootEvent("ROOT", "example.com", "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_llm_translate()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_llm_translate()
        self.assertEqual(
            set(module.watchedEvents()),
            {"LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"},
        )
        self.assertEqual(
            set(module.producedEvents()),
            {"LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"},
        )

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        module.handleEvent(self._event(_SWEDISH_TEXT))
        module.finish()
        self.assertEqual(len(module._buffer), 0)

    def test_non_english_triggers_translation(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="The quick brown fox...") as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 1)
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0].eventType, "LEAKSITE_CONTENT")
        self.assertEqual(emissions[0].data, "The quick brown fox...")

    def test_english_content_skipped(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt") as m_run:
            module.handleEvent(self._event(_ENGLISH_TEXT))
            module.finish()
        m_run.assert_not_called()
        m_notify.assert_not_called()

    def test_skip_english_false_translates_english_too(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"skip_english": False})
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="translated") as m_run:
            module.handleEvent(self._event(_ENGLISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 1)

    def test_max_events_cap_drops_remainder(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"max_events": 2})
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run, \
             mock.patch.object(module, "debug") as m_debug:
            for _ in range(5):
                module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 2)
        self.assertEqual(m_notify.call_count, 2)
        m_debug.assert_called()

    def test_max_content_length_truncates(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"max_content_length": 50})
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run:
            long_text = _SWEDISH_TEXT * 10
            module.handleEvent(self._event(long_text))
            module.finish()
        submitted_prompt = m_run.call_args.args[0]
        self.assertLess(len(submitted_prompt), 1000)

    def test_llm_failure_stops_processing(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        side_effect=OhDeereLLMFailure("boom")) as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.handleEvent(self._event(_SWEDISH_TEXT + " (second)"))
            module.finish()
        self.assertEqual(m_run.call_count, 1)
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)

    def test_duplicate_finish_single_pass(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
            module.finish()
        self.assertEqual(m_run.call_count, 1)
