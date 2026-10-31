# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shared fixture is what the Python desk computes (spec virtual-desk §6).

The LED scale and the display pictures exist twice now: here, and in the
virtual desk's C++ (ui/). Both read fixtures/desk-cases.json; this test holds
the file to the Python, ui/tests hold the C++ to the file. A change here
without regenerating the file fails; a regenerated file the C++ was not ported
to fails over there.
"""

import json
import sys
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(FIXTURES))

import make_desk_cases  # noqa: E402


class TheFixture(unittest.TestCase):
    def test_is_what_the_python_desk_computes(self):
        committed = json.loads((FIXTURES / "desk-cases.json").read_text())
        fresh = json.loads(make_desk_cases.as_text(make_desk_cases.cases()))
        self.assertEqual(committed, fresh,
                         "run software/tests/fixtures/make_desk_cases.py and port the change to ui/")

    def test_covers_every_cursor_and_the_return(self):
        cases = make_desk_cases.cases()
        self.assertEqual({c["cursor"] for c in cases["channel_pictures"]}, set(range(9)))
        self.assertEqual(len(cases["channel_pictures"]), 80)
        self.assertEqual({c["channel"] for c in cases["channel_pictures"]}, set(range(4)))
        self.assertEqual([c["cue"] for c in cases["return_pictures"]], [False, True])
        for case in cases["return_pictures"]:
            self.assertNotIn("cursor", case)
            self.assertNotIn("mode", case)


if __name__ == "__main__":
    unittest.main()
