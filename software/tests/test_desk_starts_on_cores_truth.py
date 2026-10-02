# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the desk's truth comes from at start (spec truth-from-core, step 2):
$A3_OSC_TRUTH, else the cache of what Core served, else the old copy beside
the script, else none -- and then it waits for Core instead of exiting into
a restart loop."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import a3_mixer_osc     # noqa: E402
import a3_mixer_truth   # noqa: E402


class WhereTheTruthComesFrom(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.cache = self.home / ".cache/a3/a3-osc.json"
        self.old = self.home / "beside" / "a3-osc.json"
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("A3_OSC_TRUTH", None)
        self.beside = mock.patch.object(a3_mixer_osc, "BESIDE_THE_SCRIPT", self.old)
        self.beside.start()
        self.addCleanup(self.beside.stop)

    def put(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")

    def test_the_cache_is_used_first(self):
        self.put(self.cache)
        self.put(self.old)
        self.assertEqual(a3_mixer_osc.truth_path(), self.cache)

    def test_the_old_copy_is_the_fallback(self):
        self.put(self.old)
        self.assertEqual(a3_mixer_osc.truth_path(), self.old)

    def test_no_truth_at_all_is_none(self):
        self.assertIsNone(a3_mixer_osc.truth_path())

    def test_a3_osc_truth_wins(self):
        self.put(self.cache)
        with mock.patch.dict(os.environ, {"A3_OSC_TRUTH": "/x/a3-osc.json"}):
            self.assertEqual(a3_mixer_osc.truth_path(), Path("/x/a3-osc.json"))


class AnUnreadableCache(unittest.TestCase):
    """Spec: missing *or unreadable* -> wait for Core (final review)."""

    def test_garbage_is_missing_not_a_crash(self):
        for raw in (b"", b"{", b"[]", b'{"no": "addresses"}'):
            path = Path(tempfile.mkdtemp()) / "a3-osc.json"
            path.write_bytes(raw)
            with self.assertRaises(a3_mixer_osc.TruthMissing, msg=raw):
                a3_mixer_osc.load(path)


class TheBootstrapIsTheTruths(unittest.TestCase):
    """The two literals a desk knows before it has a truth (a3-core's guard
    allows them by name) are the truth's own."""

    def test_port_and_word(self):
        data = json.loads(Path(os.environ["A3_OSC_TRUTH"]).read_text())
        port = next(l["port"] for l in data["listeners"]
                    if l["program"] == "devices" and l["role"] == "announce")
        self.assertEqual(port, a3_mixer_truth.ANNOUNCE_PORT)
        self.assertEqual(data["addresses"]["core.here"]["pattern"],
                         a3_mixer_truth.ANNOUNCE_ADDRESS)


class AnOldCopyIsIncomplete(unittest.TestCase):
    def test_the_desk_counts_core_here_among_its_words(self):
        # An old copy without it is then "incomplete" and the desk takes
        # Core's truth on its first start.
        self.assertIn("core.here", a3_mixer_osc.KEYS_USED)


class TheDeskWaitsInsteadOfLooping(unittest.TestCase):
    """A missing truth, or one without a word the desk uses, made the desk
    exit -- and systemd started it into the same exit (2026-09-30 onward)."""

    def setUp(self):
        self.source = (SCRIPTS / "a3-mixer.py").read_text()

    def test_an_incomplete_truth_waits_for_cores(self):
        self.assertIn("wait_for_truth(", self.source)
        self.assertNotIn('sys.exit(f"a3-mixer: {missing}")', self.source)
        self.assertNotIn('sys.exit("a3-mixer: a3-osc.json has no "', self.source)

    def test_the_keeper_runs_beside_the_desk(self):
        self.assertIn("target=keep", self.source)

    def test_the_wait_skips_its_own_and_checks_the_words(self):
        call = self.source.split("wait_for_truth(announce_socket", 1)[1].split("\n    say(", 1)[0]
        self.assertIn("own=", call)
        self.assertIn("usable=usable", call)

    def test_an_override_is_not_followed(self):
        self.assertIn("follows_core(os.environ)", self.source)


if __name__ == "__main__":
    unittest.main()
