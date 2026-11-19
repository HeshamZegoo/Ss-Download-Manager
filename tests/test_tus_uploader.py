import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

from ssdm.tus_uploader import TusUploadJob


class Response:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


class TusUploadTests(unittest.TestCase):
    def test_creates_session_and_sends_chunks(self):
        state = {"offset": 0, "data": bytearray(), "posts": 0}
        finished = threading.Event()
        failures = []
        def post(url, **kwargs):
            state["posts"] += 1
            return Response(201, {"Location": "/uploads/abc"})
        def head(url, **kwargs):
            return Response(200, {"Upload-Offset": str(state["offset"])})
        def patch_chunk(url, data, **kwargs):
            state["data"].extend(data)
            state["offset"] += len(data)
            return Response(204, {"Upload-Offset": str(state["offset"])})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "file.bin"
            source.write_bytes(b"abcdef")
            sessions = []
            job = TusUploadJob(
                str(source), "https://upload.example.test/files/",
                lambda sent, total, speed: None,
                lambda path: finished.set(),
                lambda error: (failures.append(error), finished.set()),
                chunk_size=2, session_created=sessions.append,
            )
            with mock_patch("ssdm.tus_uploader.requests.post", post), \
                 mock_patch("ssdm.tus_uploader.requests.head", head), \
                 mock_patch("ssdm.tus_uploader.requests.patch", patch_chunk):
                job.start()
                self.assertTrue(finished.wait(5), "TUS upload did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(state["posts"], 1)
        self.assertEqual(bytes(state["data"]), b"abcdef")
        self.assertEqual(sessions, ["https://upload.example.test/uploads/abc"])

    def test_resumes_existing_session_without_creating_another(self):
        state = {"offset": 3, "data": bytearray(b"abc"), "posts": 0}
        finished = threading.Event()
        failures = []
        def post(url, **kwargs):
            state["posts"] += 1
            return Response(201, {"Location": "/new"})
        def head(url, **kwargs):
            return Response(200, {"Upload-Offset": str(state["offset"])})
        def patch_chunk(url, data, **kwargs):
            state["data"].extend(data)
            state["offset"] += len(data)
            return Response(204, {"Upload-Offset": str(state["offset"])})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "file.bin"
            source.write_bytes(b"abcdef")
            job = TusUploadJob(
                str(source), "https://upload.example.test/files/",
                lambda sent, total, speed: None,
                lambda path: finished.set(),
                lambda error: (failures.append(error), finished.set()),
                upload_url="https://upload.example.test/uploads/existing",
                chunk_size=2,
            )
            with mock_patch("ssdm.tus_uploader.requests.post", post), \
                 mock_patch("ssdm.tus_uploader.requests.head", head), \
                 mock_patch("ssdm.tus_uploader.requests.patch", patch_chunk):
                job.start()
                self.assertTrue(finished.wait(5), "TUS resume did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(state["posts"], 0)
        self.assertEqual(bytes(state["data"]), b"abcdef")


if __name__ == "__main__":
    unittest.main()
