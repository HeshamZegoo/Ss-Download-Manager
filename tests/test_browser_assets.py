import base64
import hashlib
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
        self.assertIn("ssdmActivatedAt", worker)
        self.assertIn("startedAt < cutoff", worker)
        self.assertLess(worker.index("port.postMessage({url, source})"), worker.index("chrome.downloads.cancel(downloadId"))

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
        self.assertIn("ssdmActivatedAt", background)
        self.assertIn("startedAt < cutoff", background)
        self.assertLess(background.index("port.postMessage({url, source})"), background.index("browser.downloads.cancel(downloadId"))

    def test_chromium_key_matches_pre_registered_extension_id(self):
        manifest = json.loads((ROOT / "browser/chromium/manifest.json").read_text())
        digest = hashlib.sha256(base64.b64decode(manifest["key"])).digest()[:16]
        extension_id = "".join(
            chr(ord("a") + (byte >> 4)) + chr(ord("a") + (byte & 15))
            for byte in digest
        )
        self.assertEqual(extension_id, "egoijdabioaaoapbipodjmlpikfjbejd")
        installer = (ROOT / "tools/register-browser-host.ps1").read_text()
        self.assertIn(extension_id, installer)

    def test_installed_native_host_manifest_allows_both_extension_ids(self):
        installer = (ROOT / "tools/register-browser-host.ps1").read_text()
        self.assertIn("allowed_origins", installer)
        self.assertIn("allowed_extensions", installer)
        self.assertIn("ss-download-manager@heshamzegoo", installer)

    def test_installer_registers_all_four_browser_families(self):
        script = (ROOT / "browser/install-browser-host.ps1").read_text().replace("\\", "/")
        for browser in ("Google/Chrome", "Microsoft/Edge", "BraveSoftware/Brave-Browser", "Mozilla"):
            self.assertIn(browser, script)

    def test_chrome_and_brave_setup_instructions_are_explicit(self):
        script = (ROOT / "tools/register-browser-host.ps1").read_text()
        self.assertIn("chrome://extensions/", script)
        self.assertIn("brave://extensions/", script)
        self.assertIn("egoijdabioaaoapbipodjmlpikfjbejd", script)
        self.assertIn("Reload for Ss Download Manager Integration", script)


if __name__ == "__main__":
    unittest.main()
