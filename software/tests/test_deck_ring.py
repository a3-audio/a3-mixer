# SPDX-FileCopyrightText: 2026 Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The deck ring (Plan 4e): in engine mode Core reports each channel's source
(`channel.source`, 0 = analog, k = deck k), its cursor
(`channel.source.cursor`) and which decks are there (`stemdeck.present`); the
channel's display then shows 1 2 3 4 A (decks 1-4, analog last) instead of
the interim's D1 | D2 | A.
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

    def decks_there(self, *decks):
        for deck in decks or (0, 1, 2, 3):
            self.displays.show_deck_present(deck, True)

    def test_engine_mode_ring_shows_the_decks_then_analog(self):
        # D1 D2 D3 D4 A, analog last (maintainer, 2026-10-26).
        self.decks_there()
        self.displays.show_source(1, 2)
        self.displays.show_source_cursor(1, 1)
        self.displays.drain()
        drawn = self.picture_of(1)
        self.assertEqual(self.names(drawn), ["A", "B", "C", "D", "ST"])
        self.assertEqual(self.active_of(drawn), 1)      # deck 2 plays
        self.assertEqual(cursor_of(drawn), 0)           # the cursor is on deck 1
        self.assertEqual(self.names(self.picture_of(0)), ["A", "B", "C", "D", "ST"])

    def test_analog_is_the_last_slot(self):
        self.decks_there()
        self.displays.show_source(0, 0)
        self.displays.show_source_cursor(0, 0)
        drawn = self.picture_of(0)
        self.assertEqual(self.active_of(drawn), 4)
        self.assertEqual(cursor_of(drawn), 4)

    def test_decks_three_and_four_have_their_slots(self):
        self.decks_there()
        self.displays.show_source(0, 4)
        self.displays.show_source_cursor(0, 3)
        drawn = self.picture_of(0)
        self.assertEqual(self.active_of(drawn), 3)
        self.assertEqual(cursor_of(drawn), 2)

    def test_the_cursor_follows_cores_report(self):
        # A turn is Core's: its channel.source.cursor moves the arrow.
        self.decks_there()
        self.displays.show_source(0, 0)
        for cursor, slot in ((1, 0), (2, 1), (3, 2), (4, 3), (0, 4)):
            self.displays.show_source_cursor(0, cursor)
            self.assertEqual(cursor_of(self.picture_of(0)), slot)

    def test_the_source_is_analog_until_it_is_reported(self):
        self.displays.show_source(1, 2)
        self.assertEqual(self.active_of(self.picture_of(0)), 4)
        self.assertEqual(cursor_of(self.picture_of(0)), 4)

    def test_reaper_mode_ring_is_unchanged(self):
        self.assertEqual(self.names(self.picture_of(0)), ["A", "B", "ST"])
        self.displays.show_cursor(0, 4)
        self.assertEqual(cursor_of(self.picture_of(0)), 1)

    def test_deck_meters_are_their_stems_and_a_is_the_input(self):
        self.decks_there()
        self.displays.show_source(0, 0)
        self.displays.note_peak(1, 1.0)         # stem pair 1: deck 1's stem on channel 1
        self.displays.step_meters()
        levels = [m.level for m in self.picture_of(0).meters]
        self.assertGreater(levels[0], 0.0)      # D1: the stem
        self.assertEqual(levels[1:], [0.0] * 4)

    def test_decks_are_absent_until_core_reports_them(self):
        self.displays.show_source(0, 0)
        self.assertEqual(self.names(self.picture_of(0)), ["-", "-", "-", "-", "ST"])
        self.displays.show_deck_present(2, True)
        self.assertEqual(self.names(self.picture_of(0)), ["-", "-", "C", "-", "ST"])

    def test_an_absent_deck_keeps_its_cursor_and_bracket(self):
        self.displays.show_source(0, 2)
        self.displays.show_source_cursor(0, 1)
        picture = self.picture_of(0)
        self.assertEqual(self.active_of(picture), 1)
        self.assertEqual(cursor_of(picture), 0)
        self.assertEqual(self.names(picture), ["-", "-", "-", "-", "ST"])

    def test_a_new_core_puts_the_interim_ring_back(self):
        self.decks_there()
        self.displays.show_source(0, 1)
        self.displays.show_source_cursor(0, 2)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.forget_engine()
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 4)    # four channels
        self.assertEqual(self.names(self.picture_of(0)), ["A", "B", "ST"])
        self.displays.show_source(0, 0)     # engine again: decks unreported, cursor home
        self.assertEqual(self.names(self.picture_of(0)), ["-", "-", "-", "-", "ST"])
        self.assertEqual(cursor_of(self.picture_of(0)), 4)

    def test_a_second_channels_report_posts_only_its_own_panel(self):
        self.displays.show_source(0, 0)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_source(1, 1)
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 1)

    def test_absent_deck_is_drawn_absent(self):
        self.displays.show_source(0, 0)
        self.decks_there()
        self.displays.note_peak(1, 1.0)
        self.displays.step_meters()
        marks_present = len(self.picture_of(0).marks)
        self.displays.show_deck_present(0, False)
        picture = self.picture_of(0)
        self.assertEqual(self.names(picture), ["-", "B", "C", "D", "ST"])
        self.assertEqual(picture.meters[0].level, 0.0)
        self.assertEqual(len(picture.marks), marks_present - 2)
        self.displays.show_deck_present(0, True)
        self.assertEqual(self.names(self.picture_of(0)), ["A", "B", "C", "D", "ST"])

    def test_a_deck_report_redraws_every_channel(self):
        self.displays.show_source(0, 0)
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_deck_present(3, False)
        self.displays.drain()
        self.assertEqual(len(self.rig.drawn), 4)

    def test_a_deck_past_four_changes_nothing(self):
        self.displays.show_source(0, 0)
        self.displays.show_deck_present(4, True)
        self.assertEqual(self.names(self.picture_of(0)), ["-", "-", "-", "-", "ST"])

    def test_announcements(self):
        self.assertEqual(source_announcement([2]), 2)
        self.assertEqual(source_announcement([4]), 4)
        for damaged in ([], [5], [-1], [1.0], ["1"], [1, 2]):
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
        levels = (0.5, 0.9, 0.7, 0.6, 0.8)
        lit = {}
        for present in ((True,) * 4, (False, True, True, True)):
            image = Image.new("1", (128, 64))
            paint(image, engine_channel_picture(1, 2, present, levels, 128, 64))
            lit[present] = [p for p in image.getdata() if p]
        self.assertTrue(lit[(True,) * 4])
        self.assertLess(len(lit[(False, True, True, True)]), len(lit[(True,) * 4]))

    def test_every_source_and_cursor_paints(self):
        from PIL import Image
        from a3_mixer_displays import paint
        from display_panel import engine_channel_picture
        for source in range(5):
            for cursor in range(5):
                image = Image.new("1", (128, 64))
                paint(image, engine_channel_picture(source, cursor, (True,) * 4,
                                                    (0.5,) * 5, 128, 64))
                self.assertTrue([p for p in image.getdata() if p])


class TheTruth(unittest.TestCase):
    def setUp(self):
        self.osc = osc_module.load()

    def test_the_engine_words_are_optional_and_listened_for_when_the_truth_has_them(self):
        for key in osc_module.ENGINE_KEYS:
            self.assertNotIn(key, osc_module.KEYS_USED)
        self.assertEqual(self.osc.engine_keys(), osc_module.ENGINE_KEYS)

    def test_a_deck_is_read_off_its_address(self):
        self.assertEqual(self.osc.deck_of("stemdeck.present", "/stemdeck/2/present"), 2)
        self.assertEqual(self.osc.deck_of("stemdeck.present", "/stemdeck/4/present"), 4)
        self.assertIsNone(self.osc.deck_of("stemdeck.present", "/stemdeck/5/present"))
        self.assertEqual(self.osc.channel_of("channel.source", "/channel/3/source"), 3)
        self.assertEqual(self.osc.channel_of("channel.source.cursor",
                                             "/channel/3/source/cursor"), 3)


class EngineHeadingSize(unittest.TestCase):
    """On the real OLED the ring's headings were too small to read: they must
    be drawn at least as large as the REAPER-mode D1 | D2 | A headings."""

    def glyph_height(self, picture):
        from PIL import Image
        import a3_mixer_displays
        image = Image.new("1", (128, 64))
        a3_mixer_displays.paint(image, picture)
        top, bottom = picture.headings[0].box[1], picture.headings[0].box[3]
        rows = [y for y in range(top, bottom + 1)
                if any(image.getpixel((x, y)) for x in range(128))]
        return max(rows) - min(rows) + 1

    def test_engine_headings_are_at_least_as_tall_as_the_three_slot_ones(self):
        from display_panel import channel_picture, engine_channel_picture
        engine = engine_channel_picture(1, 0, (True,) * 4, (0.0,) * 5, 128, 64)
        three = channel_picture(0, 0, (0.0,) * 3, 0, 128, 64)
        self.assertGreaterEqual(self.glyph_height(engine), self.glyph_height(three))
        self.assertGreaterEqual(self.glyph_height(engine), 10)   # of a 12-row band


if __name__ == "__main__":
    unittest.main()
