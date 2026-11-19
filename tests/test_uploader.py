import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ssdm.uploader import UploadJob


class _PutHandler(BaseHTTPRequestHandler):
    received = b""

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received = self.rfile.read(length)
        self.send_response(201)
        self.end_headers()

    def log_message(self, *_args):
        pass


class UploadJobIntegrationTests(unittest.TestCase):
    def test_http_put_upload_sends_exact_file(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _PutHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = b"ssdm-upload-test" * 8192
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "payload.bin"
                source.write_bytes(payload)
                completed = threading.Event()
                failures = []
                job = UploadJob(
                    str(source),
                    f"http://127.0.0.1:{server.server_port}/upload",
                    lambda *_: None,
                    lambda *_: completed.set(),
                    failures.append,
                )
                job.start()
                self.assertTrue(completed.wait(10), "upload did not finish")
                self.assertEqual(failures, [])
                self.assertEqual(_PutHandler.received, payload)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
