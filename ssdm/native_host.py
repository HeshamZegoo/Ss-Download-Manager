"""Copyright © 2026 HeshamZegoo.

Native-messaging host used by the browser extensions.

The packaged Windows host executable runs this module. It accepts one or more
Chrome/Firefox native-messaging JSON frames and atomically places validated
HTTP(S) URLs in the desktop application's inbox.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "SsDownloadManager"
INBOX = APP_DIR / "browser_inbox.jsonl"
MAX_MESSAGE = 1024 * 1024


def _read_exact(stream, size: int, *, allow_eof: bool = False):
    """Read exactly size bytes from a pipe, which may return short chunks."""
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if allow_eof and not chunks:
                return None
            raise ValueError("Incomplete native-messaging frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_message(stream):
    header = _read_exact(stream, 4, allow_eof=True)
    if header is None:
        return None
    size = struct.unpack("<I", header)[0]
    if size <= 0 or size > MAX_MESSAGE:
        raise ValueError("Invalid native-messaging message size")
    payload = _read_exact(stream, size)
    return json.loads(payload.decode("utf-8"))


def _write_message(stream, value):
    payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("<I", len(payload)) + payload)
    stream.flush()


def _accept(message):
    url = str(message.get("url", "")).strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"ok": False, "error": "Only valid HTTP(S) URLs are accepted"}
    APP_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"url": url, "source": str(message.get("source", "browser"))[:32]}
    # Append is atomic enough for short newline-delimited records and avoids
    # replacing messages sent by another browser process.
    with INBOX.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"ok": True}


def main():
    source = sys.stdin.buffer
    target = sys.stdout.buffer
    while True:
        try:
            message = _read_message(source)
            if message is None:
                break
            if not isinstance(message, dict):
                _write_message(target, {"ok": False, "error": "Invalid message"})
                continue
            try:
                result = _accept(message)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            _write_message(target, result)
        except Exception as exc:
            _write_message(target, {"ok": False, "error": str(exc)})
            break


if __name__ == "__main__":
    main()
