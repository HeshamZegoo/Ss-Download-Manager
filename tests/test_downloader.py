import unittest

from ssdm.downloader import filename_from_url, _int_header, _total_from_content_range


class DownloaderHelpersTests(unittest.TestCase):
    def test_filename_from_url_decodes_path(self):
        self.assertEqual(filename_from_url("https://example.test/files/my%20file.zip?token=x"), "my file.zip")

    def test_filename_from_url_falls_back(self):
        self.assertEqual(filename_from_url("https://example.test/"), "download.bin")

    def test_int_header(self):
        self.assertEqual(_int_header("123"), 123)
        self.assertIsNone(_int_header(None))
        self.assertIsNone(_int_header("unknown"))

    def test_total_from_content_range(self):
        self.assertEqual(_total_from_content_range("bytes 100-199/1000"), 1000)
        self.assertIsNone(_total_from_content_range("invalid"))


if __name__ == "__main__":
    unittest.main()
