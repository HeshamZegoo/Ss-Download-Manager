import unittest

from ssdm.torrent import TorrentManager


class FakeSession:
    def __init__(self):
        self.applied = None

    def apply_settings(self, settings):
        self.applied = settings


class TorrentTests(unittest.TestCase):
    def test_valid_magnet_requires_info_hash(self):
        self.assertTrue(TorrentManager.valid_magnet("magnet:?xt=urn:btih:0123456789abcdef"))
        self.assertFalse(TorrentManager.valid_magnet("magnet:?dn=missing-hash"))
        self.assertFalse(TorrentManager.valid_magnet("https://example.com/file.torrent"))

    def test_limits_apply_bytes_per_second_and_queue(self):
        class Dummy:
            session = FakeSession()
            limits = {}

        manager = Dummy()
        TorrentManager.set_limits(manager, 5, 256, 64)
        self.assertEqual(manager.session.applied, {
            "active_downloads": 5,
            "download_rate_limit": 256 * 1024,
            "upload_rate_limit": 64 * 1024,
        })
        self.assertEqual(manager.limits, {
            "max_active": 5, "download_kib": 256, "upload_kib": 64,
        })

    def test_zero_bandwidth_limits_mean_unlimited(self):
        class Dummy:
            session = FakeSession()
            limits = {}

        manager = Dummy()
        TorrentManager.set_limits(manager, 1, 0, 0)
        self.assertEqual(manager.session.applied["download_rate_limit"], 0)
        self.assertEqual(manager.session.applied["upload_rate_limit"], 0)

    def test_eta_handles_active_stalled_and_completed_torrents(self):
        self.assertEqual(TorrentManager.estimate_eta(1000, 400, 10), 60)
        self.assertIsNone(TorrentManager.estimate_eta(1000, 400, 0))
        self.assertEqual(TorrentManager.estimate_eta(1000, 1000, 0), 0)
        self.assertIsNone(TorrentManager.estimate_eta(0, 0, 0))

    def test_hash_filename_is_sanitized(self):
        self.assertEqual(TorrentManager._safe_hash(None, "ab:cd/ef"), "abcdef")


if __name__ == "__main__":
    unittest.main()
