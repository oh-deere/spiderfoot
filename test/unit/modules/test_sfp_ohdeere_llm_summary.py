# test_sfp_ohdeere_llm_summary.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_llm_summary import sfp_ohdeere_llm_summary
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereClientError  # noqa: F401
from spiderfoot.ohdeere_llm import OhDeereLLMFailure, OhDeereLLMTimeout


def _scan_result_rows():
    rows = []
    for i in range(3):
        rows.append((
            1700000000 + i,
            f"api{i}.example.com",
            "example.com",
            "sfp_dnsresolve",
            "INTERNET_NAME",
            100, 100, 0, f"hash{i}", "ROOT",
            "", "ENTITY", "scan-1", 0, 0,
        ))
    rows.append((
        1700000100,
        "admin@example.com",
        "api0.example.com",
        "sfp_searxng",
        "EMAILADDR",
        100, 100, 0, "hashE", "",
        "", "ENTITY", "scan-1", 0, 0,
    ))
    return rows


def _scan_instance_tuple(target="example.com"):
    return ("my scan", target, 1700000000, 1700000001, 1700000200, "FINISHED")


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereLLMSummary(unittest.TestCase):

    def _module(self, client, db_mock=None, scan_id="scan-1"):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_llm_summary()
        with mock.patch("modules.sfp_ohdeere_llm_summary.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        module.setScanId(scan_id)
        if db_mock is not None:
            module._SpiderFootPlugin__sfdb__ = db_mock
        return sf, module

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_llm_summary()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_llm_summary()
        self.assertEqual(module.watchedEvents(), ["ROOT"])
        self.assertEqual(module.producedEvents(), ["DESCRIPTION_ABSTRACT"])

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        db = mock.MagicMock()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.finish()
        db.scanResultEvent.assert_not_called()
        m_notify.assert_not_called()

    def test_handle_event_is_noop(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = []
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        root = SpiderFootEvent("ROOT", "example.com", "", "")
        evt = SpiderFootEvent("ROOT", "example.com", "test_mod", root)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt") as m_run:
            module.handleEvent(evt)
        m_run.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_summary_description_abstract(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="The target example.com has 3 subdomains"
                                     " and one exposed email."):
            module.finish()
        types = [e.eventType for e in emissions]
        self.assertEqual(types, ["DESCRIPTION_ABSTRACT"])
        self.assertEqual(
            emissions[0].data,
            "The target example.com has 3 subdomains and one exposed email.",
        )

    def test_prompt_includes_event_counts_and_samples(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="summary") as m_run:
            module.finish()
        prompt = m_run.call_args.args[0]
        self.assertIn("example.com", prompt)
        self.assertIn("INTERNET_NAME", prompt)
        self.assertIn("EMAILADDR", prompt)
        self.assertIn("api0.example.com", prompt)

    def test_duplicate_finish_single_summary(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="summary") as m_run:
            module.finish()
            module.finish()
            module.finish()
        self.assertEqual(m_run.call_count, 1)

    def test_llm_timeout_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error") as m_error, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        side_effect=OhDeereLLMTimeout("timeout")):
            module.finish()
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_llm_failure_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error") as m_error, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        side_effect=OhDeereLLMFailure("boom")):
            module.finish()
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_empty_scan_emits_no_events_abstract(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = []
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt") as m_run:
            module.finish()
        m_run.assert_not_called()
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0].eventType, "DESCRIPTION_ABSTRACT")
        self.assertIn("No events", emissions[0].data)
