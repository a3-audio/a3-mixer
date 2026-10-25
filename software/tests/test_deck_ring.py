# SPDX-FileCopyrightText: 2026 Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The deck ring (Plan 4e): in engine mode Core reports each channel's source
(`channel.source`, 0 = analog, k = deck k), its cursor
(`channel.source.cursor`) and which decks are there (`stemdeck.present`); the
channel's display then shows AN | A | B instead of the interim's D1 | D2 | A.
Without such a report the desk is the interim's."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import a3_mixer_osc as osc_module  # noqa: E402
from display_panel import (panel_for_channel, source_announcement,  # noqa: E402
                           present_announcement)
from test_displays import Rig, cursor_of  # noqa: E402


class DeckRing(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.displays = self.rig.displays()
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def picture_of(self, index):
        return self.displays._picture_for(panel_for_channel(index))(128, 64)

    def names(self, picture):
        return [heading.text for heading in picture.headings]

    def active_of(self, picture):
        return next(i for i, m in enumerate(picture.meters)
                    if m.box[0] - 1 == picture.active[0])

    def both_decks_there(self):
        self.displays.show_deck_present(0, True)
        self.displays.show_deck_present(1, True)

    def test_engine_mode_ring_shows_analog_and_deck_letters(self):
        self.both_decks_there()
        self.displays.show_source(1, 2)
        self.displays.show_source_cursor(1, 1)
        self.displays.drain()
        drawn = self.picture_of(1)
        self.assertEqual(self.names(drawn), ["AN", "A", "B"])
        self.assertEqual(self.active_of(drawn), 2)      # deck B plays
        self.assertEqual(cursor_of(drawn), 1)           # the cursor is on deck A
        self.assertEqual(self.names(self.picture_of(0)), ["AN", "A", "B"])

    def test_the_source_is_analog_until_it_is_reported(self):
        self.displays.show_source(1, 2)
        self.assertEqual(self.active_of(self.picture_of(0)), 0)
        self.assertEqual(cursor_of(self.picture_of(0)), 0)

    def test_reaper_mode_ring_is_unchanged(self):
        self.assertEqual(self.names(self.picture_of(0)), ["D1", "D2", "A"])
        self.displays.show_cursor(0, 4)
        self.assertEqual(cursor_of(self.picture_of(0)), 1)

    def test_a_deck_meter_is_its_stem_and_an_is_the_input(self):
        self.both_decks_there()
        self.displays.show_source(0, 0)
        self.displays.note_peak(1, 1.0)         # stem pair 1: deck A's stem on channel 1
        self.displays.step_meters()
        levels = [m.level for m in self.picture_of(0).meters]
        self.assertEqual(levels[0], 0.0)        # AN: no input heard
        self.assertGreater(levels[1], 0.0)      # A: the stem
        self.assertEqual(levels[2], 0.0)        # B

    def test_decks_are_absent_until_core_reports_them(self):
        self.displays.show_source(0, 0)
        self.assertEqual(self.names(self.picture_of(0)), ["AN", "-", "-"])
        self.displays.show_deck_present(0, True)
        self.assertEqual(self.names(self.picture_of(0)), ["AN", "A", "-"])

    def test_an_absent_deck_keeps_its_cursor_and_bracket(self):
        self.displays.show_source(0, 2)
        self.displays.show_source_cursor(0, 1)
        picture = self.picture_of(0)
        self.assertEqual(self.active_of(picture), 2)
        self.assertEqual(cursor_of(picture), 1)
        self.assertEqual(self.names(picture), ["AN", "-", "-"])

    def test_a_new_core_puts_the_interim_ring_back(self):
        self.both_decks_there()
        self.displays.show_source(0, 1)
        self.displays.show_source_cursor(0, 2)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.forget_engine()
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 4)
        self.assertEqual(self.names(self.picture_of(0)), ["D1", "D2", "A"])
        self.displays.show_source(0, 0)     # engine again: decks unreported, cursor home
        self.assertEqual(self.names(self.picture_of(0)), ["AN", "-", "-"])
        self.assertEqual(cursor_of(self.picture_of(0)), 0)

    def test_a_second_channels_report_posts_only_its_own_panel(self):
        self.displays.show_source(0, 0)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_source(1, 1)
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 1)

    def test_absent_deck_is_drawn_absent(self):
        self.displays.show_source(0, 0)
        self.displays.show_deck_present(0, True)
        self.displays.show_deck_present(1, True)
        self.displays.note_peak(1, 1.0)
        self.displays.step_meters()
        marks_present = len(self.picture_of(0).marks)
        self.displays.show_deck_present(0, False)
        picture = self.picture_of(0)
        self.assertEqual(self.names(picture), ["AN", "-", "B"])
        self.assertEqual(picture.meters[1].level, 0.0)
        self.assertEqual(len(picture.marks), marks_present - 2)
        self.displays.show_deck_present(0, True)
        self.assertEqual(self.names(self.picture_of(0)), ["AN", "A", "B"])

    def test_a_deck_report_redraws_every_channel(self):
        self.displays.show_source(0, 0)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_deck_present(1, False)
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 4)

    def test_announcements(self):
        self.assertEqual(source_announcement([2]), 2)
        for damaged in ([], [3], [-1], [1.0], ["1"], [1, 2]):
            self.assertIsNone(source_announcement(damaged))
        self.assertIs(present_announcement([1]), True)
        self.assertIs(present_announcement([0]), False)
        for damaged in ([], [2], [True], [1, 0]):
            self.assertIsNone(present_announcement(damaged))


class Painting(unittest.TestCase):
    def test_an_engine_channel_with_an_absent_deck_paints(self):
        from PIL import Image
        from a3_mixer_displays import paint
        from display_panel import engine_channel_picture
        lit = {}
        for present in ((True, True), (False, True)):
            image = Image.new("1", (128, 64))
            paint(image, engine_channel_picture(1, 2, present, (0.5, 0.9, 0.7), 128, 64))
            lit[present] = [p for p in image.getdata() if p]
        self.assertTrue(lit[(True, True)])
        self.assertLess(len(lit[(False, True)]), len(lit[(True, True)]))


class TheTruth(unittest.TestCase):
    def setUp(self):
        self.osc = osc_module.load()

    def test_the_engine_words_are_optional_and_listened_for_when_the_truth_has_them(self):
        for key in osc_module.ENGINE_KEYS:
            self.assertNotIn(key, osc_module.KEYS_USED)
        self.assertEqual(self.osc.engine_keys(), osc_module.ENGINE_KEYS)

    def test_a_deck_is_read_off_its_address(self):
        self.assertEqual(self.osc.deck_of("stemdeck.present", "/stemdeck/2/present"), 2)
        self.assertIsNone(self.osc.deck_of("stemdeck.present", "/stemdeck/3/present"))
        self.assertEqual(self.osc.channel_of("channel.source", "/channel/3/source"), 3)
        self.assertEqual(self.osc.channel_of("channel.source.cursor",
                                             "/channel/3/source/cursor"), 3)


if __name__ == "__main__":
    unittest.main()
