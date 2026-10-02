# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk gets its truth from Core (spec truth-from-core, step 2): it hears
/core/here, fetches a fingerprint it does not have, verifies, stores and
restarts. A refused fetch keeps the desk running on what it has."""

import hashlib
import http.server
import os
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_truth import (ANNOUNCE_ADDRESS, announcement, cache_path,  # noqa: E402
                            fetch, keep, needs_fetch, take, verified,
                            wait_for_truth, write_whole)


def padded(text):
    raw = text.encode() + b"\0"
    return raw + b"\0" * (-len(raw) % 4)


def osc(address, *args):
    """An OSC message by hand -- strings and floats are all the tests need,
    and the desk's tests run without python-osc."""
    tags = "," + "".join("s" if isinstance(a, str) else "f" for a in args)
    body = b"".join(padded(a) if isinstance(a, str) else struct.pack(">f", a) for a in args)
    return padded(address) + padded(tags) + body


class FakeSocket:
    def __init__(self, packets):
        self.packets = list(packets)

    def recvfrom(self, size):
        return self.packets.pop(0), ("192.168.8.10", 40000)

    def running(self):
        return bool(self.packets)


def marked(body):
    return body, hashlib.sha256(body).hexdigest()


class TheAnnouncement(unittest.TestCase):
    def test_it_is_url_and_fingerprint(self):
        data = osc(ANNOUNCE_ADDRESS, "http://10.0.0.1:9080/api/truth", "a" * 64)
        self.assertEqual(announcement(data), ("http://10.0.0.1:9080/api/truth", "a" * 64))

    def test_anything_else_is_none(self):
        for data in (osc("/vu/1", 0.1, 0.2), osc(ANNOUNCE_ADDRESS, "only one"), b"garbage"):
            self.assertIsNone(announcement(data))


class Deciding(unittest.TestCase):
    def test_the_same_fingerprint_does_nothing(self):
        self.assertFalse(needs_fetch("a" * 64, "a" * 64))

    def test_a_different_one_fetches(self):
        self.assertTrue(needs_fetch("b" * 64, "a" * 64))

    def test_a_body_that_does_not_match_is_refused(self):
        body, good = marked(b'{"a":1}')
        self.assertTrue(verified(body, good, good))
        self.assertFalse(verified(body[:-1], good, good))
        self.assertFalse(verified(body, good, "c" * 64))


class TheCache(unittest.TestCase):
    def test_it_lives_in_the_users_cache(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOME": home}):
            self.assertEqual(cache_path(), Path(home) / ".cache/a3/a3-osc.json")

    def test_the_cache_is_written_whole_or_not_at_all(self):
        path = Path(tempfile.mkdtemp()) / "a3" / "a3-osc.json"
        write_whole(path, b"new")
        self.assertEqual(path.read_bytes(), b"new")
        self.assertEqual(list(path.parent.iterdir()), [path])   # no temp file left


class Taking(unittest.TestCase):
    def test_a_good_body_is_written(self):
        body, mark = marked(b'{"a":1}')
        path = Path(tempfile.mkdtemp()) / "a3" / "a3-osc.json"
        self.assertTrue(take("http://x", mark, path, fetch=lambda url: (body, mark)))
        self.assertEqual(path.read_bytes(), body)

    def test_a_failed_fetch_writes_nothing(self):
        path = Path(tempfile.mkdtemp()) / "a3-osc.json"
        path.write_bytes(b"old")

        def fails(url):
            raise OSError("connection refused")
        self.assertFalse(take("http://x", "a" * 64, path, fetch=fails))
        self.assertEqual(path.read_bytes(), b"old")

    def test_a_mismatched_body_writes_nothing(self):
        path = Path(tempfile.mkdtemp()) / "a3-osc.json"
        self.assertFalse(take("http://x", "a" * 64, path, fetch=lambda url: (b"x", "a" * 64)))
        self.assertFalse(path.exists())


class Fetching(unittest.TestCase):
    def setUp(self):
        self.body, self.mark = marked(b'{"hosts":{}}')
        body, mark = self.body, self.mark

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-A3-Truth", mark)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/truth"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_fetch_returns_body_and_header(self):
        self.assertEqual(fetch(self.url), (self.body, self.mark))


class TheLoop(unittest.TestCase):
    def test_news_is_taken_then_the_desk_restarts(self):
        body, mark = marked(b'{"a":1}')
        restarts, path = [], Path(tempfile.mkdtemp()) / "a3-osc.json"
        sock = FakeSocket([osc(ANNOUNCE_ADDRESS, "http://x", mark)])
        keep(sock, "a" * 64, path, lambda: restarts.append(1), print,
             sock.running, fetch=lambda url: (body, mark))
        self.assertEqual((restarts, path.read_bytes()), ([1], body))

    def test_the_same_fingerprint_is_heard_and_nothing_happens(self):
        restarts, fetched = [], []
        sock = FakeSocket([osc(ANNOUNCE_ADDRESS, "http://x", "a" * 64)])
        keep(sock, "a" * 64, Path(tempfile.mkdtemp()) / "t.json", lambda: restarts.append(1),
             print, sock.running, fetch=lambda url: fetched.append(url))
        self.assertEqual((restarts, fetched), ([], []))

    def test_a_refused_take_is_reported_and_no_restart(self):
        reports, restarts = [], []
        sock = FakeSocket([osc(ANNOUNCE_ADDRESS, "http://x", "b" * 64)])
        keep(sock, "a" * 64, Path(tempfile.mkdtemp()) / "t.json", lambda: restarts.append(1),
             reports.append, sock.running, fetch=lambda url: (b"x", "c" * 64))
        self.assertEqual((restarts, len(reports)), ([], 1))

    def test_waiting_ends_with_the_first_truth_taken(self):
        body, mark = marked(b'{"a":1}')
        path = Path(tempfile.mkdtemp()) / "a3-osc.json"
        sock = FakeSocket([osc("/vu/1", 0.1, 0.2), osc(ANNOUNCE_ADDRESS, "http://x", mark)])
        wait_for_truth(sock, path, print, fetch=lambda url: (body, mark))
        self.assertEqual(path.read_bytes(), body)


if __name__ == "__main__":
    unittest.main()
