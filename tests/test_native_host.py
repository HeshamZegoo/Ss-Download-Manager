import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class NativeHostTests(unittest.TestCase):
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
