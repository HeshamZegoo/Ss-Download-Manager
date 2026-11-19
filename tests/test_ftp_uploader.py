import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ssdm.ftp_uploader import FTPUploadJob


class FakeFTP:
    remote = bytearray(b"abc")

    def __init__(self, *args, **kwargs):
        self.data = FakeFTP.remote

    def connect(self, *args, **kwargs): pass
    def login(self, *args, **kwargs): pass
    def cwd(self, *args, **kwargs): pass
    def size(self, name): return len(self.data)
    def storbinary(self, command, stream, blocksize=8192, callback=None, rest=None):
        if rest is None:
            self.data.clear()
        else:
            assert rest == len(self.data)
        while True:
            chunk = stream.read(blocksize)
            if not chunk:
                break
            self.data.extend(chunk)
            if callback:
                callback(chunk)
        return "226 Transfer complete"
    def quit(self): pass
    def close(self): pass


class FTPUploadTests(unittest.TestCase):
    def test_resumes_from_remote_size(self):
        FakeFTP.remote = bytearray(b"abc")
        finished = threading.Event()
        failures = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "payload.bin"
            source.write_bytes(b"abcdefghij")
            job = FTPUploadJob(
                str(source), "ftp://tester@example.test/remote/payload.bin", "secret",
                lambda sent, total, speed: None,
                lambda path: finished.set(),
                lambda error: (failures.append(error), finished.set()),
            )
            with patch("ssdm.ftp_uploader.ftplib.FTP", FakeFTP):
                job.start()
                self.assertTrue(finished.wait(5), "FTP upload did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(bytes(FakeFTP.remote), b"abcdefghij")


if __name__ == "__main__":
    unittest.main()
