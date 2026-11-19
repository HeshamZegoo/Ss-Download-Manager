import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ssdm.sftp_uploader import SFTPUploadJob


class RemoteFile(io.BytesIO):
    def __init__(self, initial, store):
        super().__init__(initial)
        self.store = store

    def close(self):
        self.store[:] = self.getvalue()
        super().close()


class FakeSFTP:
    remote = bytearray(b"abc")

    def stat(self, path):
        class Attr:
            st_size = len(FakeSFTP.remote)
        return Attr()

    def open(self, path, mode):
        if mode == "r+b":
            return RemoteFile(bytes(FakeSFTP.remote), FakeSFTP.remote)
        FakeSFTP.remote.clear()
        return RemoteFile(b"", FakeSFTP.remote)


class FakeSSHClient:
    policy = None

    def load_system_host_keys(self):
        pass

    def set_missing_host_key_policy(self, policy):
        FakeSSHClient.policy = policy

    def connect(self, **kwargs):
        self.connection = kwargs

    def open_sftp(self):
        return FakeSFTP()

    def close(self):
        pass


class SFTPUploadTests(unittest.TestCase):
    def test_resumes_remote_partial_file_and_requires_known_host_policy(self):
        FakeSFTP.remote = bytearray(b"abc")
        finished = threading.Event()
        failures = []
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "payload.bin"
            source.write_bytes(b"abcdefghij")
            job = SFTPUploadJob(
                str(source), "sftp://tester@example.test:22/remote/payload.bin", "secret",
                lambda sent, total, speed: progress.append((sent, total)),
                lambda path: finished.set(),
                lambda error: (failures.append(error), finished.set()),
            )
            with patch("ssdm.sftp_uploader.paramiko.SSHClient", FakeSSHClient), \
                 patch("ssdm.sftp_uploader.paramiko.RejectPolicy", return_value="reject-policy"):
                job.start()
                self.assertTrue(finished.wait(5), "SFTP upload did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(bytes(FakeSFTP.remote), b"abcdefghij")
        self.assertEqual(FakeSSHClient.policy, "reject-policy")
        self.assertTrue(progress)

    def test_rejects_non_sftp_destination(self):
        failures = []
        finished = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "payload.bin"
            source.write_bytes(b"abc")
            job = SFTPUploadJob(
                str(source), "https://example.test/file", "secret",
                lambda *_: None, lambda *_: finished.set(),
                lambda error: (failures.append(error), finished.set()),
            )
            job.start()
            self.assertTrue(finished.wait(5), "invalid destination did not fail")
        self.assertTrue(failures)
        self.assertIn("sftp://", failures[0])


if __name__ == "__main__":
    unittest.main()
