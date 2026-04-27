import pytest
import unittest

from modules.sfp_crt import sfp_crt
from sflib import SpiderFoot


@pytest.mark.usefixtures
class TestModuleCrt(unittest.TestCase):

    def test_opts(self):
        module = sfp_crt()
        self.assertEqual(len(module.opts), len(module.optdescs))

    def test_setup(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_crt()
        module.setup(sf, dict())

    def test_watchedEvents_should_return_list(self):
        module = sfp_crt()
        self.assertIsInstance(module.watchedEvents(), list)

    def test_producedEvents_should_return_list(self):
        module = sfp_crt()
        self.assertIsInstance(module.producedEvents(), list)

    def test_parseApiResponse_nonfatal_http_response_code_should_not_set_errorState(self):
        sf = SpiderFoot(self.default_options)

        http_codes = ["200", "404"]
        for code in http_codes:
            with self.subTest(code=code):
                module = sfp_crt()
                module.setup(sf, dict())
                result = module.parseApiResponse({"code": code, "content": None})
                self.assertIsNone(result)
                self.assertFalse(module.errorState)

    def test_parseApiResponse_fatal_http_response_error_code_should_set_errorState(self):
        sf = SpiderFoot(self.default_options)

        # 401/403 = real auth/access failures; 429 = rate-limited.
        # 5xx are now transient (see test below) and do NOT trip errorState.
        http_codes = ["401", "403", "429"]
        for code in http_codes:
            with self.subTest(code=code):
                module = sfp_crt()
                module.setup(sf, dict())
                result = module.parseApiResponse({"code": code, "content": None})
                self.assertIsNone(result)
                self.assertTrue(module.errorState)

    def test_parseApiResponse_transient_5xx_warns_without_errorState(self):
        sf = SpiderFoot(self.default_options)

        for code in ("500", "502", "503", "504"):
            with self.subTest(code=code):
                module = sfp_crt()
                module.setup(sf, dict())
                result = module.parseApiResponse({"code": code, "content": None})
                self.assertIsNone(result)
                self.assertFalse(module.errorState)
