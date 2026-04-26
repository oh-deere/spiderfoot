# test_ohdeere_vision.py
import base64
import unittest
from unittest import mock

from spiderfoot.ohdeere_client import OhDeereClientError
from spiderfoot.ohdeere_llm import (
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
)
from spiderfoot.ohdeere_vision import (
    OhDeereVisionImageTooLarge,
    describe_image,
)


class TestDescribeImage(unittest.TestCase):

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
            describe_image(b"\x89PNG\r\n", base_url="http://llm", client=client)

    def test_happy_path_encodes_image_and_returns_result(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE",
                          "result": "a black cat"}],
        )
        raw = b"\x89PNG\r\n\x1a\nfakebytes"
        with mock.patch("spiderfoot.ohdeere_vision.time.sleep"):
            result = describe_image(
                raw,
                prompt="What is in this picture?",
                base_url="http://llm",
                client=client,
            )
        self.assertEqual(result, "a black cat")
        body = client.post.call_args.args[1]
        self.assertEqual(body["model"], "gemma4:e4b")
        self.assertEqual(body["prompt"], "What is in this picture?")
        self.assertEqual(body["image"], base64.b64encode(raw).decode("ascii"))

    def test_default_prompt_used_when_omitted(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE", "result": "x"}],
        )
        with mock.patch("spiderfoot.ohdeere_vision.time.sleep"):
            describe_image(b"png", base_url="http://llm", client=client)
        body = client.post.call_args.args[1]
        self.assertEqual(body["prompt"], "Describe this image.")

    def test_image_too_large_raises(self):
        client = self._mock_client()
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        with self.assertRaises(OhDeereVisionImageTooLarge):
            describe_image(oversized, base_url="http://llm", client=client)
        client.post.assert_not_called()

    def test_failed_status_raises_failure(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "FAILED",
                          "error": "vision backend down"}],
        )
        with mock.patch("spiderfoot.ohdeere_vision.time.sleep"):
            with self.assertRaises(OhDeereLLMFailure) as ctx:
                describe_image(b"png", base_url="http://llm", client=client)
        self.assertIn("vision backend down", str(ctx.exception))

    def test_timeout_raises_timeout_error(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "RUNNING"}] * 100,
        )
        with mock.patch("spiderfoot.ohdeere_vision.time.sleep"), \
             mock.patch("spiderfoot.ohdeere_vision.time.monotonic",
                        side_effect=[0.0] + [100.0] * 100):
            with self.assertRaises(OhDeereLLMTimeout):
                describe_image(b"png", base_url="http://llm",
                               timeout_s=10, client=client)


if __name__ == "__main__":
    unittest.main()
