import unittest
from pathlib import Path


class HtmlInterfaceTests(unittest.TestCase):
    def test_original_html_interface_is_packaged_with_bridge(self):
        html = Path(__file__).parents[1] / "ssdm" / "ui" / "idm-modern.html"
        self.assertTrue(html.is_file())
        source = html.read_text(encoding="utf-8")
        self.assertIn("qrc:///qtwebchannel/qwebchannel.js", source)
        self.assertIn("new QWebChannel", source)
        self.assertIn("Copyright © 2026 HeshamZegoo", source)
        self.assertNotIn("setInterval(function()", source)


if __name__ == "__main__":
    unittest.main()
