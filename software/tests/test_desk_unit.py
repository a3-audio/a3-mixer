# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's unit in the repo is the one the desk runs (2026-10-03).

The desk carried three hand patches no commit had: the venv's Python (the
system one lost its packages in the Debian upgrade), a restart after a crash,
and the stem LEDs switched on once the Teensy knew SVU. A desk installed from
the repo has to come up the same way."""

import configparser
import unittest
from pathlib import Path

UNIT = (Path(__file__).resolve().parents[2]
        / "platform-config/raspianos/etc/systemd/system/a3-mixer.service")


def service():
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(UNIT.read_text())
    return parser["Service"]


class TheDesksUnit(unittest.TestCase):
    def test_it_runs_the_venvs_python(self):
        self.assertTrue(service()["ExecStart"].startswith("/home/aaa/.venv/bin/python3 "))

    def test_the_stem_leds_are_on(self):
        self.assertIn("A3_STEM_LEDS=1", UNIT.read_text())

    def test_a_crash_is_restarted(self):
        self.assertEqual(service().get("Restart"), "on-failure")


if __name__ == "__main__":
    unittest.main()
