import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrowserExtensionTests(unittest.TestCase):
    def test_chromium_extension_uses_native_messaging_and_downloads(self):
        manifest = json.loads((ROOT / "browser/chromium/manifest.json").read_text())
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertIn("nativeMessaging", manifest["permissions"])
        self.assertIn("contextMenus", manifest["permissions"])
        self.assertIn("downloads", manifest["permissions"])
        worker = (ROOT / "browser/chromium/service_worker.js").read_text()
        self.assertIn("chrome.action.onClicked", worker)
        self.assertIn("chrome.downloads.onCreated", worker)
        self.assertIn("chrome.downloads.cancel", worker)
        self.assertTrue((ROOT / "browser/chromium/service_worker.js").is_file())

    def test_firefox_extension_uses_native_messaging_and_downloads(self):
        manifest = json.loads((ROOT / "browser/firefox/manifest.json").read_text())
        self.assertEqual(manifest["manifest_version"], 2)
        self.assertIn("nativeMessaging", manifest["permissions"])
        self.assertIn("downloads", manifest["permissions"])
        self.assertEqual(
            manifest["browser_specific_settings"]["gecko"]["id"],
            "ss-download-manager@heshamzegoo",
        )
        background = (ROOT / "browser/firefox/background.js").read_text()
        self.assertIn("browser.browserAction.onClicked", background)
        self.assertIn("browser.downloads.onCreated", background)
        self.assertIn("browser.downloads.cancel", background)
        self.assertTrue((ROOT / "browser/firefox/background.js").is_file())

    def test_installer_registers_all_four_browser_families(self):
        script = (ROOT / "browser/install-browser-host.ps1").read_text()
        for browser in ("Google\\\\Chrome", "Microsoft\\\\Edge", "BraveSoftware\\\\Brave-Browser", "Mozilla"):
            self.assertIn(browser, script)


if __name__ == "__main__":
    unittest.main()
