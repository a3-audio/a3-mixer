# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A pot's or fader's reading to the value the desk sends: dead zones at both
ends, the calibrated span between them, an optional centre detent.

Measured on the rig (2026-10-29): with every fader down the desk sent
0.000978 -- one count of the panel's 0..1023 converter -- and the engine
played that at about -66 dB, audible on the phones. The tops measured
1014-1022, never 1023. So the mapping happens here, on the desk, and what
goes on the wire is already 0 at the bottom and 1 at the top; Core and the
engine are unchanged.

Hardware-free like a3_mixer_panel: the file and the arithmetic are testable
without the Pi.
"""

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: The panel's converter: 0..1023, sent as counts / 1023 with six decimals.
FULL_SCALE = 1023

#: Each dead zone as a share of the calibrated span. At or below the low one
#: the value is exactly 0, at or above the high one exactly 1, and around a
#: centre detent exactly CENTRE.
#:
#: 2 %, not the 1 % first proposed: the panel's firmware sends a pot only
#: after it moved more than 12 counts, so the last value a fader sends on its
#: way down can stand 12 counts above where it rests, and the measured
#: bottoms reach 8 counts. 1 % of 1023 is 10 counts and would leave such a
#: fader a hair open; 2 % is 20.
DEAD_ZONE = 0.02

#: The value at a centre detent: the middle of the wire's 0..1.
CENTRE = 0.5

#: A span narrower than this is refused: a pot that was not moved to both
#: ends, not a pot with half the travel.
MIN_SPAN = FULL_SCALE // 2


@dataclass(frozen=True)
class Range:
    """Where a control's ends (and its centre detent) read, in counts."""
    low: int = 0
    high: int = FULL_SCALE
    centre: Optional[int] = None

    def usable(self):
        return self.high - self.low >= MIN_SPAN

    def zones(self):
        """(bottom, top, centre zone or None): the edges of the dead zones."""
        zone = DEAD_ZONE * (self.high - self.low)
        bottom, top = self.low + zone, self.high - zone
        if self.centre is None:
            return bottom, top, None
        below, above = self.centre - zone, self.centre + zone
        if not (bottom < below and above < top):
            return bottom, top, None
        return bottom, top, (below, above)


RAW = Range()


def counts_of(text):
    """Counts from the panel's value field ("0.000978" -> 1), held to the
    scale; None if the field was damaged in transit."""
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return min(FULL_SCALE, max(0, round(value * FULL_SCALE)))


def calibrated(counts, span=RAW):
    """The value to send for `counts` on a control calibrated to `span`; an
    unusable span maps as the raw range."""
    if not span.usable():
        span = RAW
    bottom, top, centre = span.zones()
    if counts <= bottom:
        return 0.0
    if counts >= top:
        return 1.0
    if centre is None:
        return (counts - bottom) / (top - bottom)
    below, above = centre
    if counts < below:
        return CENTRE * (counts - bottom) / (below - bottom)
    if counts > above:
        return CENTRE + (1.0 - CENTRE) * (counts - above) / (top - above)
    return CENTRE


class Calibration:
    """Every control's Range, by its panel id ("<track>:<index>", e.g. "0:5"
    for channel 1's fader, "master:0" for the main volume). A control not in
    it is the raw range."""

    def __init__(self, ranges=None):
        self._ranges = dict(ranges or {})

    def range_of(self, control):
        return self._ranges.get(control, RAW)

    def value(self, control, counts):
        return calibrated(counts, self.range_of(control))

    def ranges(self):
        return dict(self._ranges)

    def to_json(self):
        controls = {}
        for control, span in sorted(self._ranges.items()):
            entry = {"low": span.low, "high": span.high}
            if span.centre is not None:
                entry["centre"] = span.centre
            controls[control] = entry
        return {"version": 1, "controls": controls}


def calibration_path(environ=os.environ):
    """$A3_MIXER_CALIBRATION, else a3-mixer/calibration.json in the config
    dir of whoever runs the desk ($XDG_CONFIG_HOME, else ~/.config). The
    desk's unit runs as root, so on the desk that is /root/.config."""
    explicit = environ.get("A3_MIXER_CALIBRATION")
    if explicit:
        return Path(explicit)
    config = environ.get("XDG_CONFIG_HOME") or \
        str(Path(environ.get("HOME") or Path.home()) / ".config")
    return Path(config) / "a3-mixer" / "calibration.json"


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"not a count: {value!r}")
    return value


def _range_of(entry):
    centre = entry.get("centre")
    return Range(_count(entry["low"]), _count(entry["high"]),
                 None if centre is None else _count(centre))


def load(path, report):
    """The calibration in `path`. Missing or unreadable, the raw range for
    every control and a line through `report` -- the desk plays either way.
    An entry that is unusable on its own is dropped with a line."""
    try:
        data = json.loads(Path(path).read_text())
        controls = data["controls"]
        ranges = {str(control): _range_of(entry) for control, entry in controls.items()}
    except FileNotFoundError:
        report(f"no calibration at {path}, the raw range for every control")
        return Calibration()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as problem:
        report(f"calibration {path} unreadable ({problem!r}), "
               "the raw range for every control")
        return Calibration()
    usable = {}
    for control, span in ranges.items():
        if span.usable():
            usable[control] = span
        else:
            report(f"calibration of {control} unusable ({span}), its raw range")
    return Calibration(usable)


def save(path, calibration):
    """Written whole or not at all: a temporary file beside it, then renamed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(calibration.to_json(), indent=2) + "\n")
    os.replace(temporary, path)
