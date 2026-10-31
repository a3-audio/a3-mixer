# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shared fixture is what the Python desk computes (spec virtual-desk §6).

The LED scale and the display pictures exist twice now: here, and in the
virtual desk's C++ (the submodule a3-mixer-ui). This test holds
fixtures/desk-cases.json to the Python, and the desk's copy of it
(a3-mixer-ui/tests/fixtures/desk-cases.json) to this one; a3-mixer-ui's tests
hold the C++ to the copy. A change here without regenerating the file fails; a regenerated file
not copied to the desk fails; a copy the C++ was not ported to fails over there.
"""

import json
import sys
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DESK_COPY = Path(__file__).resolve().parents[2] / "a3-mixer-ui" / "tests" / "fixtures" / "desk-cases.json"
sys.path.insert(0, str(FIXTURES))

import make_desk_cases  # noqa: E402


class TheFixture(unittest.TestCase):
    def test_is_what_the_python_desk_computes(self):
        committed = json.loads((FIXTURES / "desk-cases.json").read_text())
        fresh = json.loads(make_desk_cases.as_text(make_desk_cases.cases()))
        self.assertEqual(committed, fresh,
                         "run software/tests/fixtures/make_desk_cases.py, copy it to a3-mixer-ui/tests/fixtures/ and port the change")

    def test_the_desks_copy_is_this_file(self):
        if not DESK_COPY.parent.parent.is_dir():
            self.skipTest("the a3-mixer-ui submodule is not checked out")
        self.assertEqual(json.loads((FIXTURES / "desk-cases.json").read_text()),
                         json.loads(DESK_COPY.read_text()),
                         "copy software/tests/fixtures/desk-cases.json to a3-mixer-ui/tests/fixtures/")

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
