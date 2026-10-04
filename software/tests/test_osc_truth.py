# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mixer speaks the one truth, a3-core's a3-osc.json.

The desk carried Core's address as a literal, and it was wrong more often
than right: three branches, three addresses, none reachable after the rig
moved subnets. Since 2026-09-30 the desk reads a copy of the truth that is
put beside its script at deploy.

The mechanics are tested against a made-up truth -- odd patterns, odd ports,
the meter names out of order -- so a pass can only come from reading the
file. The real file is held against the desk in TheRealTruth.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import a3_mixer_osc  # noqa: E402

KEYS = a3_mixer_osc.KEYS_USED

MADE_UP = {
    "hosts": {"core": "10.9.9.10", "mixer": "10.9.9.11",
              "local": "127.0.0.9", "any": "0.0.0.0"},
    "listeners": [
        {"program": "core", "role": "osc", "host": "any", "port": 19000},
        {"program": "beat-analyzer", "role": "clock", "host": "any", "port": 17775},
        {"program": "mixer", "role": "osc", "host": "mixer", "port": 17772},
    ],
    "addresses": {
        key: {"pattern": "/t/" + key + ("/{ch}" if key.startswith("channel.") else ""),
              **({"ch": [1, 4]} if key.startswith("channel.") else {})}
        for key in KEYS + ("device.hello",) if key != "vu"
    } | {"vu": {"pattern": "/t/vu/{n}", "n": [1, 40]}},
    "vu_meters": ["free", "main_top1", "in2_pre", "main_sub", "in1_pre",
                  "main_top2", "main_top3", "in4_pre", "main_top4", "in3_pre",
                  "main_top5", "main_top6", "main_top7", "main_top8",
                  "stem_a1", "stem_a2", "stem_a3", "stem_a4",
                  "stem_b1", "stem_b2", "stem_b3", "stem_b4"],
}


def made_up(**changes):
    return a3_mixer_osc.MixerOsc(MADE_UP | changes)


class WhereTheDeskSends(unittest.TestCase):
    # From the desk, a listener on every interface of the Core machine is
    # reached at that machine's address -- not at the desk's own loopback.
    def test_core_is_the_core_machine(self):
        self.assertEqual(made_up().core(), ("10.9.9.10", 19000))

    def test_the_tap_goes_to_the_analyzer_on_the_core_machine(self):
        self.assertEqual(made_up().beatclock(), ("10.9.9.10", 17775))

    def test_the_desk_listens_where_the_truth_says(self):
        self.assertEqual(made_up().listen_port(), 17772)


class WhatTheDeskSays(unittest.TestCase):
    def test_a_channel_goes_out_counting_from_one(self):
        self.assertEqual(made_up().channel_address("channel.gain", 0),
                         "/t/channel.gain/1")
        self.assertEqual(made_up().channel_address("channel.gain", 3),
                         "/t/channel.gain/4")

    def test_a_pot_is_named_by_the_truths_key(self):
        self.assertEqual(a3_mixer_osc.CHANNEL_POTS["1"], "channel.gain")
        self.assertEqual(a3_mixer_osc.MASTER_POTS["6"], "master.aux-return")
        self.assertEqual(a3_mixer_osc.MASTER_POTS["2"], "filter.frequency")

    def test_the_fx_key_is_the_channel_filter(self):
        self.assertEqual(a3_mixer_osc.CHANNEL_KEYS["fx"], "channel.filter")
        self.assertEqual(a3_mixer_osc.CHANNEL_KEYS["cue"], "channel.cue")

    def test_an_address_without_a_channel(self):
        self.assertEqual(made_up().address("master.aux-return"), "/t/master.aux-return")


class WhatTheDeskHears(unittest.TestCase):
    def test_a_lamp_is_taken_apart(self):
        self.assertEqual(made_up().match("/t/channel.cue.led/2"),
                         ("channel.cue.led", {"ch": 2}))

    def test_an_address_the_truth_does_not_have_is_nothing(self):
        self.assertIsNone(made_up().match("/channel/0/led/pfl"))
        self.assertIsNone(made_up().match("/t/channel.cue.led/9"))

    def test_a_subscription_is_the_pattern_with_wildcards(self):
        self.assertEqual(made_up().subscription("channel.cue.led"),
                         "/t/channel.cue.led/*")
        self.assertEqual(made_up().subscription("vu"), "/t/vu/*")

    def test_the_lamps_carry_the_panels_names(self):
        self.assertEqual(a3_mixer_osc.LAMPS["channel.cue.led"], "cue")
        self.assertEqual(a3_mixer_osc.LAMPS["channel.filter.led"], "fx")


class WhichMeterIsWhichLed(unittest.TestCase):
    """The firmware's twelve slots stay what they were: 0-3 the inputs, 4-11
    the outputs. Which /vu number feeds a slot is looked up by name."""

    def test_the_inputs_are_the_pre_fader_meters(self):
        osc = made_up()
        self.assertEqual(osc.vu_slot(5), 0)   # in1_pre
        self.assertEqual(osc.vu_slot(3), 1)   # in2_pre
        self.assertEqual(osc.vu_slot(10), 2)  # in3_pre
        self.assertEqual(osc.vu_slot(8), 3)   # in4_pre

    def test_the_outputs_are_the_main_sub_and_seven_tops(self):
        osc = made_up()
        self.assertEqual(osc.vu_slot(4), 4)   # main_sub
        self.assertEqual(osc.vu_slot(2), 5)   # main_top1
        self.assertEqual(osc.vu_slot(13), 11)  # main_top7

    def test_a_meter_the_desk_does_not_show_is_none(self):
        osc = made_up()
        self.assertIsNone(osc.vu_slot(1))   # free
        self.assertIsNone(osc.vu_slot(14))  # main_top8
        self.assertIsNone(osc.vu_slot(0))


class TheMeterNumberIsReadDirectly(unittest.TestCase):
    """A thousand meters a second reach the desk (40 at 25 Hz). Searching the
    whole truth for each one filled a core of the Pi 3B+ and backed every
    message up behind them (2026-10-01: receive buffer full, ~70 drops/s), so
    the meter's number is read off its own pattern alone."""

    def test_the_number_of_a_meter(self):
        self.assertEqual(made_up().vu_number("/t/vu/7"), 7)
        self.assertEqual(made_up().vu_number("/t/vu/40"), 40)

    def test_out_of_the_truths_range_is_none(self):
        self.assertIsNone(made_up().vu_number("/t/vu/0"))
        self.assertIsNone(made_up().vu_number("/t/vu/41"))

    def test_anything_else_is_none(self):
        self.assertIsNone(made_up().vu_number("/t/vu/x"))
        self.assertIsNone(made_up().vu_number("/t/vu/7/peak"))
        self.assertIsNone(made_up().vu_number("/t/channel.volume/2"))


class StemMetersByName(unittest.TestCase):
    """The beat-analyzer's stem meters (issue a3-system#71) are found by
    their names, stem_a1 ... stem_b4 = pairs 1-8, like the LED meters."""

    def test_the_stem_meters_are_pairs_one_to_eight(self):
        osc = made_up()
        first = osc._data["vu_meters"].index("stem_a1") + 1
        self.assertEqual(osc.stem_pair(first), 1)
        self.assertEqual(osc.stem_pair(first + 7), 8)

    def test_other_meters_are_not_stems(self):
        self.assertIsNone(made_up().stem_pair(1))

    def test_the_aux_meters_are_the_returns_left_and_right(self):
        """Spec desk-stem-grid-2: the return shows the analog return's
        meter, aux_L and aux_R, beside the eight stems."""
        osc = made_up(vu_meters=["in1_pre", "aux_L", "aux_R"])
        self.assertEqual((osc.aux_side(2), osc.aux_side(3)), (0, 1))
        self.assertIsNone(osc.aux_side(1))
        self.assertIsNone(osc.aux_side(9))

    def test_the_stemdecks_aux_bus_is_the_returns_sa(self):
        """2026-10-04: SA meters StemDeck's AUX bus, stem_aux_L and
        stem_aux_R (/vu/49, /vu/50 in Core's truth), found by name."""
        osc = made_up(vu_meters=["aux_L", "aux_R", "stem_aux_L", "stem_aux_R"])
        self.assertEqual((osc.stem_aux_side(3), osc.stem_aux_side(4)), (0, 1))
        self.assertIsNone(osc.stem_aux_side(1))
        self.assertIsNone(osc.stem_aux_side(5))
        self.assertIsNone(osc.stem_aux_side(0))

    def test_a_truth_without_the_bus_meters_has_none(self):
        """The truth installed before them: SA falls back on the desk."""
        osc = made_up()
        self.assertTrue(all(osc.stem_aux_side(n) is None
                            for n in range(len(osc._data["vu_meters"]) + 2)))

    def test_a_truth_without_stems_has_no_stem_meters(self):
        osc = made_up(vu_meters=["in1_pre", "in2_pre"])
        self.assertIsNone(osc.stem_pair(1))
        self.assertIsNone(osc.stem_pair(41))


class TheDeskSaysWhichTruth(unittest.TestCase):
    """At start the desk names itself and the sha256 of its copy, so Core's
    window can show whether the copy is Core's own (/device/hello)."""

    def test_hello_names_the_desk_and_its_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a3-osc.json"
            path.write_text(json.dumps(MADE_UP))
            address, (name, digest) = a3_mixer_osc.load(path).hello()
        self.assertEqual(address, "/t/device.hello")
        self.assertEqual(name, "mixer")
        self.assertEqual(digest, hashlib.sha256(json.dumps(MADE_UP).encode()).hexdigest())


class FindingTheTruth(unittest.TestCase):
    def test_a_missing_file_says_where_it_looked(self):
        with self.assertRaises(a3_mixer_osc.TruthMissing) as caught:
            a3_mixer_osc.load("/nowhere/a3-osc.json")
        self.assertIn("/nowhere/a3-osc.json", str(caught.exception))

    def test_the_environment_points_elsewhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps(MADE_UP))
            old = os.environ.get("A3_OSC_TRUTH")
            os.environ["A3_OSC_TRUTH"] = str(path)
            try:
                self.assertEqual(a3_mixer_osc.load().listen_port(), 17772)
            finally:
                if old is None:
                    del os.environ["A3_OSC_TRUTH"]
                else:
                    os.environ["A3_OSC_TRUTH"] = old

    def test_by_default_it_is_the_copy_beside_the_script(self):
        self.assertEqual(a3_mixer_osc.BESIDE_THE_SCRIPT.name, "a3-osc.json")
        self.assertEqual(a3_mixer_osc.BESIDE_THE_SCRIPT.parent,
                         Path(a3_mixer_osc.__file__).resolve().parent)

    def test_a_key_the_truth_lacks_is_named(self):
        truth = MADE_UP | {"addresses": {k: v for k, v in MADE_UP["addresses"].items()
                                         if k != "master.booth"}}
        self.assertEqual(a3_mixer_osc.MixerOsc(truth).missing(), ["master.booth"])


def real_truth_path():
    """$A3_OSC_TRUTH, the installed file, or the a3-core checkout beside this one."""
    if os.environ.get("A3_OSC_TRUTH"):
        return Path(os.environ["A3_OSC_TRUTH"])
    installed = Path("/usr/share/a3/a3-osc.json")
    if installed.exists():
        return installed
    return (Path(__file__).resolve().parents[3] / "a3-core" / "platform-config"
            / "debian-x86_64" / "a3-core" / "usr" / "share" / "a3" / "a3-osc.json")


class TheRealTruth(unittest.TestCase):
    """The desk against a3-core's file. Fails rather than skips without it:
    a skip reads as OK, and OK against nothing is the kind that lies."""

    def setUp(self):
        self.path = real_truth_path()
        self.assertTrue(self.path.exists(), f"no a3-osc.json at {self.path}")
        self.osc = a3_mixer_osc.load(self.path)

    def test_it_has_every_address_the_desk_speaks(self):
        self.assertEqual(self.osc.missing(), [])

    def test_it_has_every_meter_the_desk_shows(self):
        meters = json.loads(self.path.read_text())["vu_meters"]
        for name in a3_mixer_osc.VU_SLOTS:
            self.assertIn(name, meters)

    def test_the_desk_can_reach_core_and_the_analyzer(self):
        self.assertEqual(self.osc.core()[0], self.osc.beatclock()[0])
        self.assertNotEqual(self.osc.core()[1], self.osc.beatclock()[1])


if __name__ == "__main__":
    unittest.main()
