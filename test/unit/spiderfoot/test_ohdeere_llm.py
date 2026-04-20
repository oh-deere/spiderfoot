# test_ohdeere_llm.py
import unittest
from unittest import mock

from spiderfoot.ohdeere_client import OhDeereClientError
from spiderfoot.ohdeere_llm import (
    OhDeereLLMError,
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


class TestRunPrompt(unittest.TestCase):

    def _mock_client(self, disabled=False, post_return=None, get_returns=None):
        client = mock.MagicMock()
        client.disabled = disabled
        if post_return is not None:
            client.post.return_value = post_return
        if get_returns is not None:
            client.get.side_effect = list(get_returns)
        return client

    def test_disabled_client_raises(self):
        client = self._mock_client(disabled=True)
        with self.assertRaises(OhDeereClientError):
            run_prompt("hello", base_url="http://llm", client=client)

    def test_happy_path_submit_poll_return(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE",
                          "result": "the answer is 42"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            result = run_prompt("what is the answer?",
                                base_url="http://llm", client=client)
        self.assertEqual(result, "the answer is 42")
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.get.call_count, 1)

    def test_multi_poll_until_done(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[
                {"id": "job-1", "status": "QUEUED"},
                {"id": "job-1", "status": "RUNNING"},
                {"id": "job-1", "status": "DONE", "result": "final"},
            ],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            result = run_prompt("x", base_url="http://llm", client=client)
        self.assertEqual(result, "final")
        self.assertEqual(client.get.call_count, 3)

    def test_timeout_raises_timeout_error(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "RUNNING"}] * 100,
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"), \
             mock.patch("spiderfoot.ohdeere_llm.time.monotonic",
                        side_effect=[0.0] + [100.0] * 100):
            with self.assertRaises(OhDeereLLMTimeout):
                run_prompt("x", base_url="http://llm",
                           timeout_s=10, client=client)

    def test_failed_status_raises_failure(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "FAILED",
                          "error": "model crashed"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            with self.assertRaises(OhDeereLLMFailure) as ctx:
                run_prompt("x", base_url="http://llm", client=client)
        self.assertIn("model crashed", str(ctx.exception))

    def test_cancelled_status_raises_failure(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "CANCELLED"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            with self.assertRaises(OhDeereLLMFailure):
                run_prompt("x", base_url="http://llm", client=client)

    def test_prompt_truncation_warning(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE", "result": "ok"}],
        )
        big_prompt = "x" * 300_000
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"), \
             self.assertLogs("spiderfoot.ohdeere_llm", "WARNING") as cm:
            run_prompt(big_prompt, base_url="http://llm", client=client)
        posted = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertEqual(len(posted["prompt"]), 200_000)
        self.assertTrue(
            any("truncated" in msg.lower() for msg in cm.output),
            cm.output,
        )


class TestExceptionHierarchy(unittest.TestCase):

    def test_subclass_relationships(self):
        self.assertTrue(issubclass(OhDeereLLMTimeout, OhDeereLLMError))
        self.assertTrue(issubclass(OhDeereLLMFailure, OhDeereLLMError))
        self.assertTrue(issubclass(OhDeereLLMError, RuntimeError))
