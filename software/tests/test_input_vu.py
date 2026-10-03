"""The input meters: eight NeoPixels per channel, four strips chained in
channel order, each strip's first pixel at its top -- measured on the desk on
2026-10-04 with fixed levels sent to /vu/1-4. The firmware had assumed twelve
a channel, so channel 1 spilled into meter 2 and channel 4 drew past the end
of the chain. Read from the firmware and the desk script, so the two cannot
drift apart again."""

import re
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
FIRMWARE = SOFTWARE.parent / "hardware/mainboard/firmware/src/main.cpp"
LEDS_PER_INPUT = 8
INPUTS = 4


def firmware():
    return FIRMWARE.read_text()


def input_strips():
    source = firmware()
    table = source[source.index("int vupxlstrips"):]
    table = table[:table.index("};")]
    rows = re.findall(r"\{([\d,\s]+)\}", table)
    return [[int(n) for n in row.split(",")] for row in rows]


class TheInputMetersHaveEightLeds(unittest.TestCase):
    def test_the_chain_is_four_strips_of_eight(self):
        found = re.search(r"npxl_leds\s*=\s*(\d+)", firmware())
        self.assertEqual(int(found.group(1)), INPUTS * LEDS_PER_INPUT)

    def test_each_channel_owns_its_own_strip_bottom_last(self):
        expected = [list(range(LEDS_PER_INPUT * (ch + 1) - 1, LEDS_PER_INPUT * ch - 1, -1))
                    for ch in range(INPUTS)]
        self.assertEqual(input_strips(), expected)

    def test_the_firmware_draws_every_led_of_a_strip(self):
        source = firmware()
        inputs = source[source.index("// per-channel VU meters"):]
        inputs = inputs[:inputs.index("pixels.show()")]
        self.assertIn(f"j < {LEDS_PER_INPUT}", inputs)
        self.assertIn(f"vupxlstrips[{INPUTS}][{LEDS_PER_INPUT}]", firmware())

    def test_the_desk_scales_the_inputs_to_the_strip(self):
        script = (SOFTWARE / "scripts/a3-mixer.py").read_text()
        table = script[script.index("vu_channel_to_led_count"):]
        table = table[:table.index("}")]
        counts = dict(re.findall(r"(\d+)\s*:\s*(\d+)", table))
        self.assertEqual({counts[str(slot)] for slot in range(INPUTS)}, {str(LEDS_PER_INPUT)})


if __name__ == "__main__":
    unittest.main()
