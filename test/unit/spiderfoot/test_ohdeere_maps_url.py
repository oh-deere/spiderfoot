# test_ohdeere_maps_url.py
import unittest

from spiderfoot.ohdeere_maps_url import (
    DEFAULT_BASE_URL,
    DEFAULT_ZOOM,
    maps_deeplink,
)


class TestMapsDeeplink(unittest.TestCase):

    def test_default_base_and_zoom(self):
        url = maps_deeplink(59.33, 18.07)
        self.assertEqual(url, "https://maps.ohdeere.se/#15/59.33/18.07")

    def test_custom_zoom(self):
        url = maps_deeplink(59.33, 18.07, zoom=12)
        self.assertEqual(url, "https://maps.ohdeere.se/#12/59.33/18.07")

    def test_custom_base_url_strips_trailing_slash(self):
        url = maps_deeplink(59.33, 18.07, base_url="http://localhost:8080/")
        self.assertEqual(url, "http://localhost:8080/#15/59.33/18.07")

    def test_module_constants_are_exported(self):
        self.assertEqual(DEFAULT_BASE_URL, "https://maps.ohdeere.se")
        self.assertEqual(DEFAULT_ZOOM, 15)


if __name__ == "__main__":
    unittest.main()
