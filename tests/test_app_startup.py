import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from ssdm.app import MainWindow


class AppStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_initializes_with_persistent_settings(self):
        window = MainWindow()
        self.assertGreaterEqual(window.max_active_uploads, 1)
        self.assertTrue(window.default_download_dir.exists())
        window.close()

    def test_app_starts_when_optional_torrent_engine_fails(self):
        from unittest.mock import patch

        with patch("ssdm.app.TorrentManager", side_effect=RuntimeError("engine unavailable")):
            window = MainWindow()
        self.assertIsNone(window.torrent_manager)
        self.assertIn("engine unavailable", window.torrent_error)
        window.close()


if __name__ == "__main__":
    unittest.main()
