# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The stem meters on the main VU's top 8x8 module (spec desk-stem-grid-2):
one column per stem, A1-A4 then B1-B4, a bar of 0-8 LEDs. The desk sends the
firmware an SVU line only when a stem's bar changed -- StemDeck sends each
meter 25 times a second, and the serial line carries the lamps too."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display"))

from a3_mixer_stem_leds import StemLeds  # noqa: E402


class StemLines(unittest.TestCase):
    def test_a_full_stem_lights_eight(self):
        self.assertEqual(StemLeds().line(1, 1.0), "SVU:0:8")

    def test_stem_b4_is_column_seven(self):
        self.assertEqual(StemLeds().line(8, 1.0), "SVU:7:8")

    def test_the_same_bar_twice_is_one_line(self):
        leds = StemLeds()
        leds.line(3, 1.0)
        self.assertIsNone(leds.line(3, 0.99))

    def test_silence_and_odd_peaks_are_zero(self):
        leds = StemLeds()
        leds.line(2, 1.0)
        self.assertEqual(leds.line(2, 0.0), "SVU:1:0")
        leds.line(2, 1.0)
        self.assertEqual(leds.line(2, "x"), "SVU:1:0")

    def test_minus_24_db_is_half(self):
        self.assertEqual(StemLeds().line(1, 10 ** (-24 / 20)), "SVU:0:4")


class TheMainMeterGivesUpItsTopModule(unittest.TestCase):
    """The desk scales the main meter to the rows the firmware draws: 24,
    the top module (rows 25-32) being the stems'. Read from both sources,
    so the two cannot drift apart."""

    SOFTWARE = Path(__file__).resolve().parents[1]
    FIRMWARE = SOFTWARE.parent / "hardware/mainboard/firmware/src/main.cpp"

    def test_the_desk_scales_the_outputs_to_24(self):
        import re
        script = (self.SOFTWARE / "scripts/a3-mixer.py").read_text()
        table = script[script.index("vu_channel_to_led_count"):]
        table = table[:table.index("}")]
        counts = dict(re.findall(r"(\d+)\s*:\s*(\d+)", table))
        self.assertEqual({counts[str(slot)] for slot in range(4, 12)}, {"24"})

    def test_the_firmware_draws_24_rows_and_the_stems_on_top(self):
        source = self.FIRMWARE.read_text()
        output = source[source.index("// output VU meters"):]
        self.assertIn("j < 24", output[:output.index("}")])
        self.assertIn('command.equals("SVU")', source)


if __name__ == "__main__":
    unittest.main()
