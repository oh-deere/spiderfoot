# test_holehe_runner.py
import asyncio
import unittest
from unittest import mock

from spiderfoot.holehe_runner import HoleheHit, probe_email


def _make_provider(name, domain, exists, rate_limit=False, raises=False, slow=False):
    """Build a fake holehe-shaped async provider: f(email, client, out)."""
    async def f(email, client, out):
        if slow:
            await asyncio.sleep(10)
        if raises:
            raise RuntimeError(f"{name} blew up")
        out.append({
            "name": name,
            "domain": domain,
            "exists": exists,
            "rateLimit": rate_limit,
        })
    f.__module__ = f"holehe.modules.fake.{name}"
    return f


class TestProbeEmail(unittest.TestCase):

    def _patch_funcs(self, funcs):
        """Patch the runner's provider-list builder to return ``funcs``."""
        return mock.patch(
            "spiderfoot.holehe_runner._get_provider_funcs",
            return_value=funcs,
        )

    def test_collects_only_exists_true_and_not_rate_limited(self):
        funcs = [
            _make_provider("a", "a.com", exists=True),
            _make_provider("b", "b.com", exists=False),
            _make_provider("c", "c.com", exists=True, rate_limit=True),
            _make_provider("d", "d.com", exists=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        names = sorted(h.provider for h in hits)
        self.assertEqual(names, ["a", "d"])
        self.assertTrue(all(isinstance(h, HoleheHit) for h in hits))

    def test_per_provider_exception_isolated(self):
        funcs = [
            _make_provider("ok", "ok.com", exists=True),
            _make_provider("bad", "bad.com", exists=True, raises=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual([h.provider for h in hits], ["ok"])

    def test_skip_set_excludes_providers(self):
        called = []

        def make_recording(name):
            async def f(email, client, out):
                called.append(name)
                out.append({"name": name, "domain": f"{name}.com",
                            "exists": True, "rateLimit": False})
            f.__module__ = f"holehe.modules.fake.{name}"
            return f

        funcs = [make_recording("keep"), make_recording("drop")]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip={"drop"}, timeout_s=5)
        self.assertEqual(called, ["keep"])
        self.assertEqual([h.provider for h in hits], ["keep"])

    def test_timeout_returns_partial_results(self):
        funcs = [
            _make_provider("fast1", "f1.com", exists=True),
            _make_provider("fast2", "f2.com", exists=True),
            _make_provider("slow", "slow.com", exists=True, slow=True),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=0.5)
        names = sorted(h.provider for h in hits)
        self.assertEqual(names, ["fast1", "fast2"])

    def test_empty_when_no_provider_returns_exists_true(self):
        funcs = [
            _make_provider("a", "a.com", exists=False),
            _make_provider("b", "b.com", exists=False),
        ]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual(hits, [])

    def test_hit_carries_provider_and_domain(self):
        funcs = [_make_provider("github", "github.com", exists=True)]
        with self._patch_funcs(funcs):
            hits = probe_email("e@x.com", skip=set(), timeout_s=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].provider, "github")
        self.assertEqual(hits[0].domain, "github.com")


if __name__ == "__main__":
    unittest.main()
