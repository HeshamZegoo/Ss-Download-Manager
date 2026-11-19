import re
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ssdm.downloader import DownloadJob


PAYLOAD = bytes((i % 251 for i in range(2 * 1024 * 1024 + 137)))


class _RangeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else len(PAYLOAD) - 1
            end = min(end, len(PAYLOAD) - 1)
            if start >= len(PAYLOAD):
                self.send_response(416)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            data = PAYLOAD[start:end + 1]
            for offset in range(0, len(data), 16 * 1024):
                self.wfile.write(data[offset:offset + 16 * 1024])
                self.wfile.flush()
                time.sleep(0.001)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            for offset in range(0, len(PAYLOAD), 16 * 1024):
                self.wfile.write(PAYLOAD[offset:offset + 16 * 1024])
                self.wfile.flush()
                time.sleep(0.001)

    def log_message(self, *_args):
        pass


class DownloaderIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/large.bin"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_parallel_range_download_writes_exact_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = str(Path(folder) / "result.bin")
            done = threading.Event()
            errors = []
            job = DownloadJob(
                self.url, destination, lambda *_: None,
                lambda *_: done.set(), errors.append,
                chunk_size=32 * 1024, max_connections=4,
            )
            job.start()
            self.assertTrue(done.wait(15), "parallel download did not finish")
            self.assertEqual(errors, [])
            self.assertEqual(Path(destination).read_bytes(), PAYLOAD)

    def test_segmented_download_can_pause_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = str(Path(folder) / "resumed.bin")
            paused = threading.Event()
            completed = threading.Event()
            errors = []
            job = DownloadJob(
                self.url, destination, lambda *_: None,
                lambda *_: completed.set(), errors.append,
                paused=lambda: paused.set(),
                chunk_size=16 * 1024, max_connections=4,
            )
            job.start()
            time.sleep(0.04)
            job.pause()
            self.assertTrue(paused.wait(10), "pause callback did not fire")
            job._thread.join(5)
            job.start()
            self.assertTrue(completed.wait(15), "resumed download did not finish")
            self.assertEqual(errors, [])
            self.assertEqual(Path(destination).read_bytes(), PAYLOAD)

    def test_single_connection_fallback_downloads_exact_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = str(Path(folder) / "fallback.bin")
            done = threading.Event()
            errors = []
            job = DownloadJob(
                self.url, destination, lambda *_: None,
                lambda *_: done.set(), errors.append,
                chunk_size=64 * 1024, max_connections=1,
            )
            job.start()
            self.assertTrue(done.wait(15), "single-stream download did not finish")
            self.assertEqual(errors, [])
            self.assertEqual(Path(destination).read_bytes(), PAYLOAD)


if __name__ == "__main__":
    unittest.main()
