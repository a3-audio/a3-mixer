#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's words, ports and addresses -- out of the one truth.

Every fact about who talks to whom, on which port, with which words, lives in
a3-core's a3-osc.json (decided 2026-09-30). The desk runs on a machine of its
own, so it reads a copy that is put beside this script at deploy
(`a3-osc.json`, not in git), or the file $A3_OSC_TRUTH names.

This module holds the desk's own tables -- which pot, key and lamp is which
address -- as the truth's *keys*, never as addresses. It is the counterpart
of a3-core's a3_osc.py, cut to what the desk asks, and like the panel tables
it needs no board, neopixel or serial to import.

A fact the file does not have is an error, not a default: a default is a
second truth, and the desk's old literal for Core's address was wrong more
often than it was right.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from a3_mixer_truth import cache_path

#: The old copy the deploy put beside the script -- a fallback for one
#: release, until every desk has fetched Core's truth once.
BESIDE_THE_SCRIPT = Path(__file__).resolve().with_name("a3-osc.json")

#: The channel strip's pots, by the index the firmware reports.
CHANNEL_POTS = {
    "0": "channel.aux-send",
    "1": "channel.gain",
    "2": "channel.eq.high",
    "3": "channel.eq.mid",
    "4": "channel.eq.low",
    "5": "channel.volume",
}

#: The channel strip's keys, by what a3_mixer_panel.channel_button says they
#: do. The fx key switches the channel through the master filter.
CHANNEL_KEYS = {
    "fx": "channel.filter",
    "cue": "channel.cue",
}

#: The master section's pots, by the index the firmware reports.
MASTER_POTS = {
    "0": "master.volume",
    "1": "filter.resonance",
    "2": "filter.frequency",
    "3": "master.booth",
    "4": "master.phones-mix",
    "5": "master.phones-volume",
    "6": "master.aux-return",
}

#: The lamps Core tells the desk about, and the panel's name for each --
#: the name a3_mixer_panel.led_colour takes.
LAMPS = {
    "channel.cue.led": "cue",
    "channel.filter.led": "fx",
}

#: The firmware's twelve meter slots, by what they measure: four inputs of
#: eight LEDs, then eight outputs of thirty-two (decided 2026-09-30: the main
#: sub and main tops 1-7). The slots are the firmware's numbering and stay;
#: which /vu number feeds one is the channel map's.
VU_SLOTS = (
    "in1_pre", "in2_pre", "in3_pre", "in4_pre",
    "main_sub", "main_top1", "main_top2", "main_top3",
    "main_top4", "main_top5", "main_top6", "main_top7",
)

#: Every address key the desk sends or listens for.
KEYS_USED = tuple(CHANNEL_POTS.values()) + tuple(CHANNEL_KEYS.values()) \
    + tuple(MASTER_POTS.values()) + tuple(LAMPS) \
    + ("filter.mode", "filter.led", "beat", "tap", "state.recall", "vu",
       "device.hello", "channel.stem.turn", "aux-return.stem.turn",
       "aux-return.stem.push", "channel.stem", "aux-return.stem",
       "channel.stem.push", "channel.stem.cursor", "aux-return.stem.mode", "core.here",
       "aux-return.cue.led")


def _pattern_regex(pattern):
    """"/channel/{ch}/volume" as a regex with a named group per placeholder."""
    return re.compile(re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>\\d+)", re.escape(pattern)))


#: The inputs' stereo meters, by slot and side (spec stereo-channel-meters,
#: 2026-10-06): a channel's LEDs show the louder of its two. While the truth
#: has them, the mono in<N>_pre light nothing; a truth from before has none,
#: and the desk falls back to the mono ones.
INPUT_METERS = ("in1_pre_L", "in1_pre_R", "in2_pre_L", "in2_pre_R",
                "in3_pre_L", "in3_pre_R", "in4_pre_L", "in4_pre_R")
MONO_INPUT_METERS = VU_SLOTS[:4]

#: The beat-analyzer's stem meters, pairs 1-8: deck A's stems, then deck B's.
STEM_METERS = ("stem_a1", "stem_a2", "stem_a3", "stem_a4",
               "stem_b1", "stem_b2", "stem_b3", "stem_b4")

#: The analog return's meter, left and right: the return display's ANALOG.
AUX_METERS = ("aux_L", "aux_R")

#: StemDeck's AUX bus, left and right: the return display's STEM (2026-10-04).
#: A truth from before has no such names, and the desk falls back.
STEM_AUX_METERS = ("stem_aux_L", "stem_aux_R")


class TruthMissing(Exception):
    """No truth to read -- the desk cannot know where Core is."""


class MixerOsc:
    def __init__(self, data, digest=None):
        self._data = data
        self._digest = digest
        # Compiled once: the desk matches every message it hears, a thousand
        # meters a second among them, on a Pi 3B+.
        self._matchers = {key: _pattern_regex(entry["pattern"])
                          for key, entry in data["addresses"].items()}
        self._has_stereo_inputs = set(INPUT_METERS) <= set(data.get("vu_meters", []))
        # Asked for every meter that arrives, before python-osc sees it (#6).
        self._shown_meters = frozenset(
            n for n in range(1, len(data.get("vu_meters", [])) + 1)
            if self._lights_something(n))

    # -- where ------------------------------------------------------------

    def _listener(self, program, role):
        for listener in self._data["listeners"]:
            if listener["program"] == program and listener["role"] == role:
                return listener
        raise KeyError(f"nobody listens as {program}.{role} in a3-osc.json")

    def _on_the_core_machine(self, program, role):
        """(ip, port) of a listener, seen from the desk. A listener on every
        interface ("any") is on the Core machine, where everything but the
        desk runs -- from here that is Core's address, not the loopback."""
        listener = self._listener(program, role)
        host = "core" if listener["host"] == "any" else listener["host"]
        return self._data["hosts"][host], listener["port"]

    def core(self):
        return self._on_the_core_machine("core", "osc")

    def beatclock(self):
        return self._on_the_core_machine("beat-analyzer", "clock")

    def listen_port(self):
        return self._listener("mixer", "osc")["port"]

    # -- what ---------------------------------------------------------------

    def address(self, key, **fields):
        return self._data["addresses"][key]["pattern"].format(**fields)

    def channel_address(self, key, index):
        """The address for channel `index` (0-3): on the wire, 1-4."""
        return self.address(key, ch=index + 1)

    def subscription(self, key):
        """The pattern for pythonosc's dispatcher: placeholders as `*`."""
        return re.sub(r"\{\w+\}", "*", self._data["addresses"][key]["pattern"])

    def match(self, address):
        """("channel.cue.led", {"ch": 2}) for "/channel/2/cue/led", or None
        for an address the truth does not have or a number out of range."""
        for key, regex in self._matchers.items():
            fields = self._fields(key, regex, address)
            if fields is not None:
                return key, fields
        return None

    def channel_of(self, key, address):
        """The channel (1-4) if `address` is exactly `key`'s, else None. A
        handler asks this rather than match(): python-osc 1.9.3 hands it
        every address its wildcard map is a prefix of."""
        regex = self._matchers.get(key)
        fields = regex and self._fields(key, regex, address)
        return fields.get("ch") if fields else None

    def is_address(self, key, address):
        """Whether `address` is exactly `key`'s: channel_of() for an address
        without a channel."""
        regex = self._matchers.get(key)
        return bool(regex) and self._fields(key, regex, address) is not None

    def vu_number(self, address):
        """The n of /vu/<n>, or None: the meter path's own match, without
        searching the rest of the truth."""
        regex = self._matchers.get("vu")
        fields = regex and self._fields("vu", regex, address)
        return fields["n"] if fields else None

    def _fields(self, key, regex, address):
        """The numbers in `address` if it is `key`'s and they are in range."""
        found = regex.fullmatch(address)
        if not found:
            return None
        entry = self._data["addresses"][key]
        fields = {name: int(value) for name, value in found.groupdict().items()}
        if all(entry.get(name, [value, value])[0] <= value
               <= entry.get(name, [value, value])[1]
               for name, value in fields.items()):
            return fields
        return None

    def stem_pair(self, number):
        """The stem pair (1-8) /vu/<number> meters, or None: found by name,
        stem_a1 ... stem_b4, like the LED meters (issue a3-system#71)."""
        meters = self._data.get("vu_meters", [])
        if not 1 <= number <= len(meters):
            return None
        name = meters[number - 1]
        return STEM_METERS.index(name) + 1 if name in STEM_METERS else None

    def aux_side(self, number):
        """0 for the analog return's left meter (aux_L), 1 for its right
        (aux_R), None for any other /vu/<number> (spec desk-stem-grid-2)."""
        return self._side(number, AUX_METERS)

    def stem_aux_side(self, number):
        """0 for StemDeck's AUX bus left meter (stem_aux_L), 1 for its right
        (stem_aux_R), None for any other /vu/<number>."""
        return self._side(number, STEM_AUX_METERS)

    def _side(self, number, names):
        meters = self._data.get("vu_meters", [])
        if not 1 <= number <= len(meters):
            return None
        name = meters[number - 1]
        return names.index(name) if name in names else None

    def input_side(self, number):
        """(slot 0-3, side 0 left / 1 right) for an input's stereo meter, or
        None for any other /vu/<number>."""
        found = self._side(number, INPUT_METERS)
        return None if found is None else divmod(found, 2)

    def vu_slot(self, number):
        """The firmware slot /vu/<number> lights, or None if the desk does
        not show that meter. A mono input meter lights nothing while the
        truth has the stereo ones (input_side)."""
        meters = self._data.get("vu_meters", [])
        if not 1 <= number <= len(meters):
            return None
        name = meters[number - 1]
        if name in MONO_INPUT_METERS and self._has_stereo_inputs:
            return None
        return VU_SLOTS.index(name) if name in VU_SLOTS else None

    def shows_meter(self, number):
        """Whether the desk shows /vu/<number> anywhere -- an LED, a display
        meter -- by the same names vu_handler asks. A meter it does not show
        is dropped before dispatch (a3-audio/a3-mixer#6)."""
        return number in self._shown_meters

    def _lights_something(self, number):
        return any(found is not None for found in (
            self.stem_pair(number), self.aux_side(number),
            self.stem_aux_side(number), self.input_side(number),
            self.vu_slot(number)))

    @property
    def digest(self):
        """The sha256 of the truth's bytes: Core's fingerprint, when it is the
        body Core served."""
        return self._digest

    def hello(self):
        """(address, [name, sha256 of the copy]): the desk tells Core which
        truth it speaks, and Core's window shows whether it is Core's own."""
        return self.address("device.hello"), ["mixer", self._digest]

    def missing(self):
        """The keys the desk uses that the truth does not have."""
        return [key for key in KEYS_USED if key not in self._data["addresses"]]


def truth_path():
    """Where the desk's truth is (spec truth-from-core, step 2): $A3_OSC_TRUTH,
    else what Core last served (a3_mixer_truth's cache), else the old copy
    beside the script -- kept as a fallback for one release -- else None."""
    named = os.environ.get("A3_OSC_TRUTH")
    if named:
        return Path(named)
    for candidate in (cache_path(), BESIDE_THE_SCRIPT):
        if candidate.exists():
            return candidate
    return None


def load(path=None):
    """The truth from `path`, else truth_path(). TruthMissing if there is
    none: the desk then waits for Core's (a3-mixer.py)."""
    path = Path(path) if path else truth_path()
    if path is None:
        raise TruthMissing(f"no truth at {cache_path()} or {BESIDE_THE_SCRIPT}")
    if not path.exists():
        raise TruthMissing(f"no a3-osc.json at {path}")
    # Unreadable is missing too (spec): the desk then waits for Core's truth
    # instead of crashing into a restart loop on a damaged cache.
    try:
        raw = path.read_bytes()
        return MixerOsc(json.loads(raw), hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as problem:
        raise TruthMissing(f"{path} is unreadable: {problem!r}") from None
