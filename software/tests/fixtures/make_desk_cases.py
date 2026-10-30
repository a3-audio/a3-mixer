#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's shared cases: what the Python desk computes, written down for
the virtual desk's C++ to compute the same (spec virtual-desk §6).

    python3 software/tests/fixtures/make_desk_cases.py     # rewrites desk-cases.json
"""

import json
import sys
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOFTWARE / "scripts"))
sys.path.insert(0, str(SOFTWARE / "scripts" / "a3-mixer-set-display"))

import a3_mixer_meters as meters  # noqa: E402
import a3_mixer_osc as osc  # noqa: E402
import display_panel as panel  # noqa: E402

FIXTURE = Path(__file__).with_name("desk-cases.json")
#: The OLEDs are 128 x 64 (spec §2); the virtual desk paints at that size and scales.
WIDTH, HEIGHT = 128, 64
#: A channel's three meters: D1's stem n, D2's stem n, A.
LEVELS = [0.5, 0.875, 0.375]


def _sweep(low, high, step):
    count = int(round((high - low) / step))
    return [low + i * step for i in range(count + 1)]


def tables():
    return {"channel_pots": osc.CHANNEL_POTS, "master_pots": osc.MASTER_POTS,
            "channel_keys": osc.CHANNEL_KEYS, "lamps": osc.LAMPS,
            "keys_used": sorted(set(osc.KEYS_USED)), "delay_keys": list(osc.DELAY_KEYS)}


def leds():
    return {"channel": [[db, meters.channel_leds(db), meters.bar_fraction(db)]
                        for db in _sweep(-50.0, 3.0, 0.5)],
            "main": [[db, meters.main_led_index(db)] for db in _sweep(-70.0, 5.0, 0.25)],
            "channel_colours": list(meters.CHANNEL_LED_COLOURS)}


def _picture(picture):
    return {"headings": [[*h.box, h.text] for h in picture.headings],
            "meters": [[*m.box, m.pixels(), m.hatched(),
                        -1 if m.hold_row() is None else m.hold_row()] for m in picture.meters],
            "cursor": None if picture.cursor is None else list(picture.cursor),
            "dividers": [list(d) for d in picture.dividers],
            "toggle": None if picture.toggle is None
            else [*picture.toggle.box, bool(picture.toggle.on), picture.toggle.text],
            "active": None if picture.active is None else list(picture.active),
            "marks": [list(m) for m in picture.marks]}


def _channel_masks(index):
    """None, D1's, D2's, both (an older Core) and a foreign stem only."""
    d1, d2 = 1 << index, 1 << (panel.STEMS_PER_DECK + index)
    return (0, d1, d2, d1 | d2, 1 << ((index + 1) % panel.CHANNEL_COUNT))


def channel_cases():
    clips = [True, False, True]
    holds = [min(1.0, level + 0.25) for level in LEVELS]
    return [{"channel": index, "cursor": cursor, "mask": mask, "levels": LEVELS, "clips": clips,
             "holds": holds, "width": WIDTH, "height": HEIGHT,
             "picture": _picture(panel.channel_picture(index, cursor, LEVELS, mask, WIDTH, HEIGHT,
                                                       clips, holds))}
            for index in range(panel.CHANNEL_COUNT)
            # The ring, then a cursor off it (an older Core's): A.
            for cursor in (*panel.channel_ring(index), (index + 1) % panel.CHANNEL_COUNT)
            for mask in _channel_masks(index)]


def return_cases():
    """The FX Return (P47): one meter and the CUE field, off and on."""
    level, clip, hold = 0.875, True, 1.0
    return [{"cue": cue, "level": level, "clip": clip, "hold": hold, "width": WIDTH, "height": HEIGHT,
             "picture": _picture(panel.return_picture(cue, level, WIDTH, HEIGHT, clip, hold))}
            for cue in (False, True)]


#: Every value Core announces per delay row (a3-osc.json), one off its steps,
#: and None (not said yet).
DELAY_VALUES = {"beat": (0.125, 0.25, 0.5, 0.75, 1.0, 2.0, 1.5, None),
                "feedback": (0.0, 0.05, 0.7, 0.95, None),
                "color": (-1.0, -0.5, -0.1, 0.0, 0.1, 0.3, 1.0, None),
                "spread": (0.0, 15.0, 60.0, 180.0, None)}


def delay_text_cases():
    """What a delay row's value reads on the return display (the virtual desk
    shows the same texts)."""
    return [{"row": row, "value": value, "text": panel.delay_text(row, value)}
            for row, values in DELAY_VALUES.items() for value in values]


def engine_channel_cases():
    """The engine-mode ring D1 D2 D3 D4 A: levels, clips and holds in that order."""
    levels = [0.5, 0.875, 0.375, 0.625, 0.25]
    clips, holds = [False, True, False, False, True], [0.75, 1.0, 0.5, 0.875, 0.5]
    presences = ((True,) * 4, (True, False, True, False), (False, True, False, True),
                 (False,) * 4)
    return [{"source": source, "cursor": cursor, "present": list(present), "levels": levels,
             "clips": clips, "holds": holds, "width": WIDTH, "height": HEIGHT,
             "picture": _picture(panel.engine_channel_picture(source, cursor, present, levels,
                                                              WIDTH, HEIGHT, clips, holds))}
            for source in range(5) for cursor in range(5) for present in presences]


def cases():
    return {"_comment": "Generated by make_desk_cases.py from the Python desk -- never edit by hand.",
            "tables": tables(), "leds": leds(),
            "channel_pictures": channel_cases(), "return_pictures": return_cases(),
            "engine_channel_pictures": engine_channel_cases(), "delay_texts": delay_text_cases()}


def as_text(data):
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    FIXTURE.write_text(as_text(cases()))
    print(f"wrote {FIXTURE}")
