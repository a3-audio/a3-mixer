# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's unit in the repo is the one the desk runs (2026-10-03).

The desk carried three hand patches no commit had: the venv's Python (the
system one lost its packages in the Debian upgrade), a restart after a crash,
and no stem-LED switch (the stems left the main VU, 2026-10-04). A desk installed from
the repo has to come up the same way."""

import configparser
import unittest
from pathlib import Path

SYSTEMD = Path(__file__).resolve().parents[2] / "platform-config/raspianos/etc/systemd"
UNITS = SYSTEMD / "system"
UNIT = UNITS / "a3-mixer.service"
DISPLAY_UNIT = UNITS / "a3-mixer-set-display.service"


def service(unit=UNIT):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(unit.read_text())
    return parser["Service"]


class TheDesksUnit(unittest.TestCase):
    def test_it_runs_the_venvs_python(self):
        self.assertTrue(service()["ExecStart"].startswith("/home/aaa/.venv/bin/python3 "))

    def test_no_stem_led_switch_any_more(self):
        """The stems left the main VU on 2026-10-04."""
        self.assertNotIn("A3_STEM_LEDS", UNIT.read_text())

    def test_a_crash_is_restarted(self):
        self.assertEqual(service().get("Restart"), "on-failure")


class TheDisplaysUnit(unittest.TestCase):
    def test_it_runs_the_display_script_on_the_venvs_python(self):
        self.assertEqual(
            service(DISPLAY_UNIT)["ExecStart"],
            "/home/aaa/.venv/bin/python /home/aaa/a3-mixer/software/scripts/"
            "a3-mixer-set-display/a3-mixer-set-display.py")

    def test_a_crash_is_restarted(self):
        self.assertEqual(service(DISPLAY_UNIT).get("Restart"), "on-failure")


class OnePlaceForTheUnits(unittest.TestCase):
    """Two copies of each unit drifted apart until one started a path the
    repository no longer has (2026-10-04). system/ is the place the docs name."""

    def test_no_unit_file_outside_system(self):
        self.assertEqual(sorted(p.name for p in SYSTEMD.glob("*.service")), [])


if __name__ == "__main__":
    unittest.main()
