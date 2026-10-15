# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""One line from the panel, taken apart -- or refused, never raised.

The serial reader indexed `words[1]..words[4]` of whatever came in. A short
or garbled line (a cut-off write, noise on the cable, a firmware boot banner)
raised IndexError or UnicodeDecodeError inside `serial_handler`, the reader
process died, and the watchdog took the whole desk down with it.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_panel import panel_fields


class PanelLineTest(unittest.TestCase):

    def test_a_full_line_gives_track_mode_index_value(self):
        self.assertEqual(panel_fields(b"T:0:B:2:1\r\n"), ("0", "B", "2", "1"))

    def test_a_short_line_is_refused(self):
        self.assertIsNone(panel_fields(b"T:0:B\r\n"))

    def test_an_empty_line_is_refused(self):
        self.assertIsNone(panel_fields(b""))

    def test_bytes_that_are_not_utf8_are_refused(self):
        self.assertIsNone(panel_fields(b"T:0:\xff\xfe:2:1\r\n"))

    def test_extra_fields_are_ignored(self):
        self.assertEqual(panel_fields(b"T:master:P:0:512:x\n"),
                         ("master", "P", "0", "512"))


if __name__ == "__main__":
    unittest.main()
