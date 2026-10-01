# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk says which truth it speaks every 30 seconds, not only at start.

It said /device/hello only together with its question for Core's state, and
stopped once Core answered. A Core restarted after that forgot the hello and
never heard it again -- its window showed no desk although the desk was fine
(2026-10-01). Every 30 seconds the window stays current, and the age it shows
says how long ago the desk last spoke.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_recall import HelloEvery  # noqa: E402


class HelloEveryThirtySeconds(unittest.TestCase):
    def test_it_says_hello_at_once(self):
        self.assertTrue(HelloEvery().due(now=0.0))

    def test_not_again_before_thirty_seconds(self):
        hello = HelloEvery()
        hello.said(now=10.0)
        self.assertFalse(hello.due(now=39.9))

    def test_again_after_thirty_seconds(self):
        hello = HelloEvery()
        hello.said(now=10.0)
        self.assertTrue(hello.due(now=40.0))

    def test_it_never_gives_up(self):
        # Unlike the state question: Core may restart at any hour.
        hello = HelloEvery()
        hello.said(now=86400.0)
        self.assertTrue(hello.due(now=86430.0))

    def test_the_desk_uses_it(self):
        source = (Path(__file__).resolve().parents[1] / "scripts/a3-mixer.py").read_text()
        self.assertIn("HelloEvery()", source)
        self.assertIn("hello.due(", source)


if __name__ == "__main__":
    unittest.main()
