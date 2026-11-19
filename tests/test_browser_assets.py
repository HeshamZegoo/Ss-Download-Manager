import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrowserExtensionTests(unittest.TestCase):
    def test_chromium_extension_uses_native_messaging(self):
        manifest = json.loads((ROOT / "browser/chromium/manifest.json").read_text())
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertIn("nativeMessaging", manifest["permissions"])
        self.assertIn("contextMenus", manifest["permissions"])
        self.assertTrue((ROOT / "browser/chromium/service_worker.js").is_file())

    def test_firefox_extension_uses_native_messaging_and_fixed_id(self):
        manifest = json.loads((ROOT / "browser/firefox/manifest.json").read_text())
        self.assertEqual(manifest["manifest_version"], 2)
        self.assertIn("nativeMessaging", manifest["permissions"])
        self.assertEqual(
            manifest["browser_specific_settings"]["gecko"]["id"],
            "ss-download-manager@heshamzegoo",
        )
        self.assertTrue((ROOT / "browser/firefox/background.js").is_file())

    def test_installer_registers_all_four_browser_families(self):
        script = (ROOT / "browser/install-browser-host.ps1").read_text()
        for browser in ("Google\\Chrome", "Microsoft\\Edge", "BraveSoftware\\Brave-Browser", "Mozilla"):
            self.assertIn(browser, script)


if __name__ == "__main__":
    unittest.main()
