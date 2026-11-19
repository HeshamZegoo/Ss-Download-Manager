import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ssdm.native_host import _read_message


class NativeHostTests(unittest.TestCase):

    def test_read_message_handles_partial_pipe_reads(self):
        class ShortReadStream:
            def __init__(self, payload):
                self.stream = io.BytesIO(payload)

            def read(self, size=-1):
                return self.stream.read(min(size, 2))

        message = {"url": "https://example.com/file.zip", "source": "test"}
        payload = json.dumps(message).encode("utf-8")
        frame = struct.pack("<I", len(payload)) + payload
        self.assertEqual(_read_message(ShortReadStream(frame)), message)

    def test_accepts_only_http_urls_and_writes_inbox(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, APPDATA=directory)
            messages = [
                {"url": "https://example.com/file.zip", "source": "test"},
                {"url": "file:///etc/passwd", "source": "test"},
            ]
            framed = b"".join(
                struct.pack("<I", len(payload)) + payload
                for payload in (json.dumps(item).encode() for item in messages)
            )
            process = subprocess.run(
                [sys.executable, "-m", "ssdm.native_host"],
                input=framed, capture_output=True, env=env, check=True,
            )
            output = process.stdout
            replies = []
            while output:
                size = struct.unpack("<I", output[:4])[0]
                replies.append(json.loads(output[4:4 + size]))
                output = output[4 + size:]
            self.assertEqual(replies, [{"ok": True}, {
                "ok": False, "error": "Only valid HTTP(S) URLs are accepted"
            }])
            inbox = Path(directory) / "SsDownloadManager" / "browser_inbox.jsonl"
            self.assertEqual(json.loads(inbox.read_text().splitlines()[0])["url"],
                             "https://example.com/file.zip")


if __name__ == "__main__":
    unittest.main()
