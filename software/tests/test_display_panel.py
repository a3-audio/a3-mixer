# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fünf Displays, und eines darf die anderen vier nicht mit ins Grab nehmen.

Gefunden am 2026-09-12: `a3-mixer-set-display.service` war seit dem 2026-09-10
tot, abgebrochen in der Initialisierung des sechsten Displays. Zwei Fehler in
einer Funktion, beide durch Lesen belegbar -- `i2c(port=0, ...)` wo der
Multiplexer auf Bus 1 sitzt, und ein Zeichnen auf `device_dev_5`, das in jener
Funktion gar nicht existiert.

Der eigentliche Befund ist aber der dritte: ein Skript, das die sechs Displays
als sechs fast gleiche Funktionen hintereinander aufruft, stirbt am ersten, das
nicht antwortet, und lässt die übrigen dunkel. Ein fehlendes Display ist eine
Meldung wert, kein Grund, den Dienst zu beenden.

Die Regel steht in einem eigenen Modul, weil sich das Skript ohne die
Pi-Hardware (luma, smbus, TCA9548A) nicht einmal importieren lässt -- derselbe
Grund wie bei a3_mixer_recall.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display")
)

from display_panel import MULTIPLEXER_CHANNELS, PANELS, draw_panels


class PanelTable(unittest.TestCase):
    def test_every_panel_sits_on_the_bus_the_multiplexer_uses(self):
        # TCA9548A.I2C_setup() spricht den Multiplexer über SMBus(1) an. Ein
        # Display hinter diesem Multiplexer kann also nur auf Bus 1 antworten.
        # Das sechste stand auf Bus 0 -- dem Kameraanschluss des Pi, meist gar
        # nicht aktiviert -- und daran ist der Dienst gestorben.
        for panel in PANELS:
            self.assertEqual(1, panel.port, panel.label)

    def test_every_panel_has_its_own_multiplexer_channel(self):
        channels = [panel.channel for panel in PANELS]
        self.assertEqual(len(channels), len(set(channels)))

    # Fuenf, nicht sechs. Das sechste war nie da: der Kopf des alten Skripts
    # sagte "5 Oled Displays", die Adresskonstanten hiessen _2 bis _6, und
    # disp_1..disp_5 benutzten die Multiplexer-Kanaele 2 bis 6. Nur disp_6
    # griff auf Kanal 7 -- und daran ist der Dienst acht Tage lang gestorben.
    # Vom Maintainer bestaetigt: "es gibt keinen kanal 7".
    def test_there_are_five(self):
        self.assertEqual(5, len(PANELS))

    def test_the_channels_are_the_ones_the_multiplexer_has(self):
        self.assertEqual(list(MULTIPLEXER_CHANNELS),
                         [panel.channel for panel in PANELS])

    def test_no_panel_claims_a_channel_that_does_not_exist(self):
        for panel in PANELS:
            self.assertIn(panel.channel, MULTIPLEXER_CHANNELS, panel.label)

    # Vier Kanalzuege und der FX-Return, vom Maintainer aufgezaehlt:
    # "es gibt 5 (kanal 1-4 und FX-Return)". Das fuenfte trug die Aufschrift
    # "Line In" -- dieselbe Copy-Paste-Schicht, aus der auch das sechste
    # Display kam, das es nie gab.
    def test_the_fifth_is_the_aux_return(self):
        self.assertEqual("Aux Return", PANELS[-1].label)

    def test_the_first_four_are_the_channel_strips(self):
        self.assertEqual(["Deck 1", "Deck 2", "Deck 3", "Deck 4"],
                         [panel.label for panel in PANELS[:4]])

    def test_each_label_is_its_own(self):
        labels = [panel.label for panel in PANELS]
        self.assertEqual(len(labels), len(set(labels)))


class OneDeadDisplay(unittest.TestCase):
    def setUp(self):
        self.drawn = []
        self.reported = []

    def show(self, panel):
        if panel.label == "Deck 3":
            raise OSError("no answer at 0x3c")
        self.drawn.append(panel.label)

    def report(self, message):
        self.reported.append(message)

    def test_the_others_are_still_drawn(self):
        draw_panels(PANELS, self.show, self.report)
        self.assertEqual(len(PANELS) - 1, len(self.drawn))
        self.assertNotIn("Deck 3", self.drawn)

    def test_the_dead_one_is_named_in_the_report(self):
        draw_panels(PANELS, self.show, self.report)
        self.assertEqual(1, len(self.reported))
        self.assertIn("Deck 3", self.reported[0])

    def test_the_dead_ones_come_back_as_the_return_value(self):
        failed = draw_panels(PANELS, self.show, self.report)
        self.assertEqual(["Deck 3"], [panel.label for panel in failed])

    def test_all_of_them_are_attempted_even_if_the_first_one_dies(self):
        attempted = []

        def every_one_fails(panel):
            attempted.append(panel.label)
            raise OSError("nothing on this bus at all")

        failed = draw_panels(PANELS, every_one_fails, self.report)
        self.assertEqual(len(PANELS), len(attempted))
        self.assertEqual(len(PANELS), len(failed))


class NothingWrong(unittest.TestCase):
    def test_a_full_panel_reports_nothing_and_returns_nothing(self):
        reported = []
        failed = draw_panels(PANELS, lambda panel: None, reported.append)
        self.assertEqual([], failed)
        self.assertEqual([], reported)


W, H = 128, 64


def stem(pair):
    return 1 << (pair - 1)


class ChannelSelector(unittest.TestCase):
    """A channel's display is an input selector: eight stem meters under
    D1 | D2 and, in the ninth slot, A -- the channel's analog input, a meter
    under its letter (maintainer, 2026-10-07: "where STEM stands, A for
    analog again, below it the VU meter of the analog input"; it replaces
    the STEM toggle of 2026-10-04). It shows what is selected -- the cursor
    -- and what plays: the active bracket, over a stem or over A."""

    def picture(self, cursor=8, levels=(0.5,) * 9, mask=0, width=W, height=H):
        from display_panel import channel_picture
        return channel_picture(cursor, levels, mask, width, height)

    def test_three_headings_over_their_meters(self):
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["D1", "D2", "A"])
        meters = p.meters
        for heading, (first, last) in zip(p.headings[:2], ((0, 3), (4, 7))):
            self.assertEqual(heading.box[0], meters[first].box[0])
            self.assertEqual(heading.box[2], meters[last].box[2])
            self.assertLess(heading.box[3], meters[first].box[1])

    def test_a_stands_over_the_analog_meter(self):
        p = self.picture()
        a, analog = p.headings[2].box, p.meters[8].box
        self.assertLessEqual(a[0], analog[0])
        self.assertGreaterEqual(a[2], analog[2])
        self.assertLessEqual(abs((a[0] + a[2]) - (analog[0] + analog[2])), 1)
        self.assertLess(a[3], analog[1])
        self.assertEqual(a[1], p.headings[0].box[1])

    def test_nine_meters_the_ninth_analog(self):
        from display_panel import ANALOG_INPUT
        self.assertEqual(ANALOG_INPUT, 8)
        boxes = [m.box for m in self.picture().meters]
        self.assertEqual(len(boxes), 9)
        for (x0, y0, x1, y1), following in zip(boxes, boxes[1:] + [None]):
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)
            if following:
                self.assertLess(x1, following[0])

    def test_the_analog_meter_is_a_stems_size_and_height(self):
        p = self.picture()
        stem_box, analog = p.meters[0].box, p.meters[8].box
        self.assertEqual(analog[2] - analog[0], stem_box[2] - stem_box[0])
        self.assertEqual((analog[1], analog[3]), (stem_box[1], stem_box[3]))

    def test_no_toggle_any_more(self):
        self.assertIsNone(self.picture().toggle)
        self.assertIsNone(self.picture(mask=stem(3)).toggle)

    def test_the_groups_stand_apart(self):
        p = self.picture()
        boxes = [m.box for m in p.meters]
        inner = boxes[1][0] - boxes[0][2]
        self.assertGreater(boxes[4][0] - boxes[3][2], inner)
        self.assertGreater(boxes[8][0] - boxes[7][2], inner)

    def test_the_groups_are_divided_by_lines(self):
        """D1 | D2 | A stand apart: a vertical line in each gap, below the
        headings, the meters' height."""
        p = self.picture()
        slots = [m.box for m in p.meters]
        self.assertEqual(len(p.dividers), 2)
        for (x0, y0, x1, y1), (left, right) in zip(p.dividers, ((3, 4), (7, 8))):
            self.assertEqual(x0, x1)
            self.assertGreaterEqual(x0 - slots[left][2], 3)
            self.assertGreaterEqual(slots[right][0] - x0, 3)
            self.assertGreater(y0, p.headings[0].box[3])
            self.assertEqual((y0, y1), (slots[0][1], slots[0][3]))

    def test_the_meters_keep_their_width(self):
        boxes = [m.box for m in self.picture().meters]
        self.assertTrue(all(x1 - x0 + 1 >= 9 for x0, _, x1, _ in boxes))

    def test_a_meter_is_only_its_level_and_clip(self):
        """No assignment and no peak travel with a meter; whether it clips
        does (2026-10-04)."""
        from display_panel import Meter
        self.assertEqual(Meter._fields, ("box", "level", "clip"))

    def test_the_levels_are_the_meters(self):
        levels = tuple(i / 9 for i in range(9))
        self.assertEqual([m.level for m in self.picture(levels=levels).meters], list(levels))

    def assert_arrow_over(self, p, slot):
        """The cursor is a small arrow box between the headings and the top
        of the meters, centred over `slot`."""
        x0, y0, x1, y1 = p.cursor
        self.assertGreater(y0, max(h.box[3] for h in p.headings))
        self.assertLess(y1, slot[1])
        self.assertLessEqual(abs((x0 + x1) - (slot[0] + slot[2])), 1)

    def test_the_cursor_is_an_arrow_above_its_meter(self):
        """Maintainer, 2026-10-04: a "^" turned over, a small triangle
        pointing down at the selected meter -- the inverted column went."""
        p = self.picture(cursor=4)
        self.assert_arrow_over(p, p.meters[4].box)

    def test_the_arrow_is_as_wide_as_a_meter_and_a_few_rows_tall(self):
        p = self.picture(cursor=0)
        x0, y0, x1, y1 = p.cursor
        meter = p.meters[0].box
        self.assertEqual(x1 - x0, meter[2] - meter[0])
        self.assertIn(y1 - y0 + 1, (4, 5))

    def test_the_cursor_on_a_is_the_same_arrow_above_its_meter(self):
        p = self.picture(cursor=8)
        self.assert_arrow_over(p, p.meters[8].box)
        on_a_stem = self.picture(cursor=0).cursor
        self.assertEqual((p.cursor[2] - p.cursor[0], p.cursor[1], p.cursor[3]),
                         (on_a_stem[2] - on_a_stem[0], on_a_stem[1], on_a_stem[3]))

    def test_the_meters_stay_readable_under_the_arrow(self):
        p = self.picture()
        x0, y0, x1, y1 = p.meters[0].box
        self.assertGreaterEqual(y1 - y0 + 1, 40)
        self.assertEqual(y1, H - 1)

    def test_the_headings_keep_their_size(self):
        for heading in self.picture().headings:
            h = heading.box
            self.assertEqual(h[3] - h[1] + 1, 12)

    def test_it_follows_the_panel(self):
        p = self.picture(width=128, height=32)
        boxes = [m.box for m in p.meters] + [h.box for h in p.headings]
        for box in boxes + [p.cursor]:
            self.assertTrue(box[3] < 32, box)


def assert_bracket_over(case, p, meter):
    """The active bracket -- a "]" turned 90 degrees counter-clockwise, a
    top line with a short leg down at each end -- frames `meter`'s top: one
    column wider than the meter on each side, its top line below the
    cursor's arrow and above the meter, its legs reaching down beside the
    meter."""
    x0, y0, x1, y1 = p.active
    case.assertEqual((x0, x1), (meter[0] - 1, meter[2] + 1))
    case.assertGreater(y0, p.cursor[3])
    case.assertEqual(y0, meter[1] - 1)
    case.assertGreater(y1, meter[1])
    case.assertLess(y1 - y0 + 1, 8)


class ActiveBracket(unittest.TestCase):
    """Maintainer, 2026-10-04: the stem that plays on the channel -- the
    lowest bit of its mask -- carries a bracket open at the bottom, the
    same mark as the return's active mode. No stem playing is the analog
    input playing: A carries it (2026-10-07)."""

    def picture(self, mask, cursor=2):
        from display_panel import channel_picture
        return channel_picture(cursor, (0.5,) * 9, mask, W, H)

    def test_the_playing_stem_carries_the_bracket(self):
        p = self.picture(stem(6))
        assert_bracket_over(self, p, p.meters[5].box)

    def test_the_lowest_stem_is_the_one_that_plays(self):
        p = self.picture(stem(3) | stem(6))
        assert_bracket_over(self, p, p.meters[2].box)

    def test_no_stem_the_analog_input_carries_it(self):
        p = self.picture(0)
        assert_bracket_over(self, p, p.meters[8].box)

    def test_the_bracket_and_the_cursor_on_one_stem(self):
        p = self.picture(stem(3), cursor=2)
        assert_bracket_over(self, p, p.meters[2].box)

    def every_bracket(self):
        for pair in range(1, 9):
            yield pair, self.picture(stem(pair))
        yield "A", self.picture(0)

    def test_a_stem_playing_leaves_a_unmarked(self):
        for pair in range(1, 9):
            p = self.picture(stem(pair))
            self.assertLess(p.active[2], p.meters[8].box[0], pair)

    def test_it_stays_on_the_panel(self):
        for pair, p in self.every_bracket():
            x0, y0, x1, y1 = p.active
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H, pair)

    def test_its_legs_stand_in_the_gaps(self):
        """The legs never cover a meter's own columns, its own or a
        neighbour's: the meters stay whole under the bracket."""
        for pair, p in self.every_bracket():
            for leg in (p.active[0], p.active[2]):
                for meter in p.meters:
                    self.assertFalse(meter.box[0] <= leg <= meter.box[2], (pair, leg))

    def test_it_never_touches_a_divider(self):
        """At least one dark column between a leg and a divider line --
        stem 4 and 5 stand beside D1 | D2, stem 8 and A beside A's."""
        for pair, p in self.every_bracket():
            for divider in p.dividers:
                self.assertTrue(divider[0] < p.active[0] - 1 or divider[0] > p.active[2] + 1,
                                (pair, divider))

    def test_the_arrow_stays_above_it(self):
        for pair, p in self.every_bracket():
            self.assertGreater(p.active[1], p.cursor[3], pair)
            self.assertGreater(p.active[1], max(h.box[3] for h in p.headings), pair)


class ReturnMeter(unittest.TestCase):
    """The return is drawn like a channel (2026-10-04): two mono meters,
    STEM (StemDeck's aux bus) and ANALOG (the analog return), under their
    names; the mode that plays carries the active bracket over its meter, as
    a channel's playing stem does, and the cursor is the same down arrow,
    over STEM, ANALOG or the CUE field (ReturnCue)."""

    def picture(self, cursor=None, mode=None, levels=(0.5, 0.5), cue=False):
        from display_panel import STEM_MODE, return_picture
        cursor = STEM_MODE if cursor is None else cursor
        mode = STEM_MODE if mode is None else mode
        return return_picture(cursor, mode, cue, levels, W, H)

    def heading(self, picture, text):
        return next(h for h in picture.headings if h.text == text)

    def test_only_stem_and_analog_from_left_to_right(self):
        """Maintainer, 2026-10-04: the AUX title irritated and went; the
        return shows its two options and nothing between them."""
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["STEM", "ANALOG"])
        lefts = [h.box[0] for h in p.headings]
        self.assertEqual(lefts, sorted(lefts))

    def test_two_mono_meters_under_their_headings(self):
        from display_panel import Meter
        p = self.picture(levels=(0.1, 0.4))
        self.assertEqual([m.level for m in p.meters], [0.1, 0.4])
        self.assertTrue(all(type(m) is Meter for m in p.meters))
        for text, meter in (("STEM", p.meters[0]), ("ANALOG", p.meters[1])):
            heading = self.heading(p, text).box
            self.assertTrue(heading[0] <= meter.box[0] and meter.box[2] <= heading[2], text)
            self.assertLess(heading[3], meter.box[1])

    def test_the_mode_that_plays_has_the_active_bracket(self):
        """Maintainer, 2026-10-04: the bracket replaces the inverted
        heading, so "active" looks the same on every display."""
        from display_panel import ANALOG_MODE, STEM_MODE
        for mode, index in ((STEM_MODE, 0), (ANALOG_MODE, 1)):
            for cursor in (STEM_MODE, ANALOG_MODE):
                p = self.picture(cursor=cursor, mode=mode)
                assert_bracket_over(self, p, p.meters[index].box)

    def test_the_headings_are_plain(self):
        from display_panel import Heading
        self.assertEqual(Heading._fields, ("box", "text"))

    def test_the_cursor_is_an_arrow_above_stem_or_analog(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        for cursor, index in ((STEM_MODE, 0), (ANALOG_MODE, 1)):
            p = self.picture(cursor=cursor)
            x0, y0, x1, y1 = p.cursor
            meter = p.meters[index].box
            self.assertGreater(y0, max(h.box[3] for h in p.headings))
            self.assertLess(y1, meter[1])
            self.assertLessEqual(abs((x0 + x1) - (meter[0] + meter[2])), 1)

    def test_the_return_arrow_reads_like_the_channels(self):
        from display_panel import channel_picture
        channel = channel_picture(0, (0.0,) * 9, False, W, H).cursor
        ret = self.picture().cursor
        self.assertEqual((ret[1], ret[3]), (channel[1], channel[3]))
        self.assertGreaterEqual(ret[2] - ret[0], channel[2] - channel[0])

    def test_the_meters_stand_inside_the_panel(self):
        for x0, y0, x1, y1 in [m.box for m in self.picture().meters]:
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)

    def test_there_is_no_scale_any_more(self):
        from display_panel import Picture
        self.assertNotIn("ticks", Picture._fields)


class ReturnCue(unittest.TestCase):
    """Maintainer, 2026-10-04: the return gets a cue of its own, switched on
    its display -- a CUE field at the right edge behind a divider, in the
    slot where a channel shows A, so both displays read the same. The
    cursor runs over STEM, ANALOG and CUE; the active bracket stays over the
    playing mode and never stands on CUE."""

    def picture(self, cursor=1, mode=1, cue=False, levels=(0.5, 0.5)):
        from display_panel import return_picture
        return return_picture(cursor, mode, cue, levels, W, H)

    def channel(self, cursor=0):
        from display_panel import channel_picture
        return channel_picture(cursor, (0.5,) * 9, 0, W, H)

    def test_the_cue_field_reads_cue(self):
        self.assertEqual(self.picture().toggle.text, "CUE")

    def test_it_is_filled_while_the_cue_is_on(self):
        self.assertTrue(self.picture(cue=True).toggle.on)
        self.assertFalse(self.picture(cue=False).toggle.on)

    def test_it_stands_in_the_channels_a_slot(self):
        """Its size is the slot a channel's A heading spans, not a pixel
        number of its own: the two displays sit side by side on the desk."""
        x0, _, x1, _ = self.channel().headings[2].box
        _, y0, _, y1 = self.channel().meters[8].box
        self.assertEqual(self.picture().toggle.box, (x0, y0, x1, y1))

    def test_a_divider_sets_it_apart_where_the_channels_does(self):
        p, channel = self.picture(), self.channel()
        self.assertEqual(len(p.dividers), 1)
        self.assertEqual(p.dividers[0], channel.dividers[-1])

    def test_the_meters_stay_left_of_the_divider(self):
        """With a column of dark between a meter -- or its bracket -- and
        the line."""
        from display_panel import ANALOG_MODE, STEM_MODE
        for mode in (STEM_MODE, ANALOG_MODE):
            p = self.picture(mode=mode)
            line = p.dividers[0][0]
            for meter in p.meters:
                self.assertLess(meter.box[2], line - 1, mode)
            for heading in p.headings:
                self.assertLess(heading.box[2], line, mode)
            self.assertLess(p.active[2], line - 1, mode)

    def test_stem_and_analog_keep_their_look(self):
        """The meters and headings may move left, but keep their size."""
        from display_panel import RETURN_HEADING_OF_WIDTH, RETURN_METER_OF_HEADING
        heading = round(W * RETURN_HEADING_OF_WIDTH)
        p = self.picture()
        self.assertEqual([h.box[2] - h.box[0] + 1 for h in p.headings], [heading] * 2)
        self.assertEqual([m.box[2] - m.box[0] + 1 for m in p.meters],
                         [round(heading * RETURN_METER_OF_HEADING)] * 2)

    def test_the_cursor_on_cue_is_the_channels_arrow_on_a(self):
        from display_panel import ANALOG_INPUT, CUE_CURSOR
        self.assertEqual(CUE_CURSOR, 2)
        self.assertEqual(self.picture(cursor=CUE_CURSOR).cursor,
                         self.channel(cursor=ANALOG_INPUT).cursor)

    def test_the_cursor_on_stem_or_analog_is_not_on_cue(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        for cursor, index in ((STEM_MODE, 0), (ANALOG_MODE, 1)):
            p = self.picture(cursor=cursor)
            meter = p.meters[index].box
            self.assertLessEqual(abs((p.cursor[0] + p.cursor[2]) - (meter[0] + meter[2])), 1)

    def test_the_bracket_never_stands_on_cue(self):
        from display_panel import ANALOG_MODE, CUE_CURSOR, STEM_MODE
        for mode, index in ((STEM_MODE, 0), (ANALOG_MODE, 1)):
            for cursor in (STEM_MODE, ANALOG_MODE, CUE_CURSOR):
                for cue in (False, True):
                    p = self.picture(cursor=cursor, mode=mode, cue=cue)
                    assert_bracket_over(self, p, p.meters[index].box)
                    self.assertLess(p.active[2], p.toggle.box[0])

    def test_the_cue_moves_neither_meter_nor_heading(self):
        on, off = self.picture(cue=True), self.picture(cue=False)
        self.assertEqual([m.box for m in on.meters], [m.box for m in off.meters])
        self.assertEqual(on.headings, off.headings)

    def test_it_lays_out_on_a_short_panel_too(self):
        from display_panel import return_picture
        p = return_picture(2, 0, True, (0.5, 0.5), W, 32)
        for box in [m.box for m in p.meters] + [h.box for h in p.headings]:
            self.assertTrue(box[3] < 32, box)
        self.assertTrue(p.toggle.box[3] < 32 and p.cursor[3] < 32)


class MeterBallistics(unittest.TestCase):
    """Decided 2026-10-04: instant rise and a VU-like fall of 20 dB/s. The
    peak mark went with the return's segments: no display draws one."""

    def ballistics(self):
        from display_panel import Ballistics
        return Ballistics()

    def fall(self, seconds):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_FLOOR_DB
        return METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB * seconds

    def test_the_constants(self):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_STEPS_PER_SECOND
        self.assertEqual(METER_STEPS_PER_SECOND, 10)
        self.assertEqual(METER_FALL_DB_PER_SECOND, 20.0)

    def test_a_rise_is_instant(self):
        self.assertEqual(self.ballistics().feed(0.8, 0.1), 0.8)

    def test_it_falls_at_twenty_db_a_second(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        shown = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(0.1))
        for _ in range(9):
            shown = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(1.0))

    def test_it_stops_at_the_level_it_is_fed(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        for _ in range(30):
            shown = b.feed(0.5, 0.1)
        self.assertEqual(shown, 0.5)

    def test_it_never_falls_below_silence(self):
        b = self.ballistics()
        b.feed(0.1, 0.1)
        self.assertEqual(b.feed(0.0, 5.0), 0.0)


class InPixels(unittest.TestCase):
    """A panel is redrawn when its pixels change, not its floats: the bus
    carries ~17 draws a second, and a fall of less than a row is no draw."""

    def channel(self, cursor=8, level=0.0, mask=0):
        from display_panel import channel_picture
        return channel_picture(cursor, (level,) * 9, mask, W, H)

    def test_a_channel_meter_is_its_bar(self):
        p = self.channel(level=0.6)
        rows = p.meters[0].box[3] - p.meters[0].box[1] + 1
        self.assertEqual(p.meters[0].pixels(), round(0.6 * rows))

    def test_less_than_a_row_is_the_same_picture(self):
        from display_panel import pixel_key
        one, two, three = (self.channel(level=level) for level in (0.500, 0.505, 0.6))
        self.assertEqual(pixel_key(one), pixel_key(two))
        self.assertNotEqual(pixel_key(one), pixel_key(three))

    def test_a_silent_input_paints_nothing(self):
        self.assertEqual([m.pixels() for m in self.channel(cursor=0).meters], [0] * 9)

    def test_the_cursor_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(cursor=0)), pixel_key(self.channel(cursor=1)))
        self.assertNotEqual(pixel_key(self.channel(cursor=7)), pixel_key(self.channel(cursor=8)))

    def test_stem_or_analog_playing_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(mask=stem(1))),
                            pixel_key(self.channel(mask=0)))

    def test_the_active_stem_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(mask=stem(3))),
                            pixel_key(self.channel(mask=stem(5))))

    def test_a_second_stem_above_the_playing_one_is_the_same_picture(self):
        from display_panel import pixel_key
        self.assertEqual(pixel_key(self.channel(mask=stem(5))),
                         pixel_key(self.channel(mask=stem(5) | stem(6))))

    def test_the_playing_mode_is_part_of_the_picture(self):
        from display_panel import ANALOG_MODE, STEM_MODE, pixel_key, return_picture
        self.assertNotEqual(
            pixel_key(return_picture(STEM_MODE, STEM_MODE, False, (0.0, 0.0), W, H)),
            pixel_key(return_picture(STEM_MODE, ANALOG_MODE, False, (0.0, 0.0), W, H)))

    def test_the_return_cue_is_part_of_the_picture(self):
        """A cue switched on or off is one redraw of the return panel."""
        from display_panel import STEM_MODE, pixel_key, return_picture
        self.assertNotEqual(
            pixel_key(return_picture(STEM_MODE, STEM_MODE, False, (0.0, 0.0), W, H)),
            pixel_key(return_picture(STEM_MODE, STEM_MODE, True, (0.0, 0.0), W, H)))

    def test_the_return_in_rows(self):
        from display_panel import pixel_key, return_picture
        one = return_picture(1, 1, False, (0.500, 0.500), W, H)
        two = return_picture(1, 1, False, (0.505, 0.505), W, H)
        self.assertEqual(pixel_key(one), pixel_key(two))


class ClipIndication(unittest.TestCase):
    """Decided 2026-10-04: a meter shows when its signal went over full
    scale. meter_level stops at 0 dBFS, so a clean master at 0 dBFS and a
    +6 dB overload were the same full bar; the clip state tells them apart,
    lit by a step's held peak over 1.0 and held CLIP_HOLD_SECONDS after the
    last over."""

    def hold(self):
        from display_panel import ClipHold
        return ClipHold()

    def test_the_constants(self):
        from display_panel import CLIP_HOLD_SECONDS, CLIP_THRESHOLD
        self.assertEqual(CLIP_THRESHOLD, 1.0)
        self.assertEqual(CLIP_HOLD_SECONDS, 1.0)

    def test_full_scale_is_not_a_clip(self):
        self.assertFalse(self.hold().feed(1.0, 0.1))
        self.assertFalse(self.hold().feed(0.5, 0.1))

    def test_an_over_lights_it(self):
        self.assertTrue(self.hold().feed(1.0001, 0.1))
        self.assertTrue(self.hold().feed(2.0, 0.1))

    def test_it_holds_for_a_second_after_the_last_over(self):
        hold = self.hold()
        hold.feed(2.0, 0.1)
        lit = [hold.feed(0.5, 0.1) for _ in range(10)]
        self.assertEqual(lit, [True] * 9 + [False])

    def test_a_new_over_starts_the_hold_again(self):
        hold = self.hold()
        hold.feed(2.0, 0.1)
        for _ in range(5):
            hold.feed(0.5, 0.1)
        hold.feed(1.5, 0.1)
        lit = [hold.feed(0.5, 0.1) for _ in range(10)]
        self.assertEqual(lit, [True] * 9 + [False])

    def test_a_long_gap_clears_it_at_once(self):
        hold = self.hold()
        hold.feed(2.0, 0.1)
        self.assertFalse(hold.feed(0.0, 1.0))

    def test_odd_peaks_never_light_it(self):
        for odd in (None, "x", True, float("nan"), float("-inf")):
            with self.subTest(odd=odd):
                self.assertFalse(self.hold().feed(odd, 0.1))

    def test_the_level_is_unchanged_up_to_full_scale(self):
        from display_panel import meter_level
        self.assertEqual(meter_level(1.0), 1.0)
        self.assertEqual(meter_level(2.0), 1.0)
        self.assertAlmostEqual(meter_level(10 ** (-12 / 20)), 0.75)

    def test_a_meter_does_not_clip_unless_told(self):
        from display_panel import ANALOG_MODE, Meter, channel_picture, return_picture
        self.assertFalse(Meter((0, 0, 9, 9), 1.0).clip)
        pictures = (channel_picture(8, (1.0,) * 9, 0, W, H),
                    return_picture(ANALOG_MODE, ANALOG_MODE, False, (1.0, 1.0), W, H))
        for picture in pictures:
            self.assertEqual([m.clip for m in picture.meters], [False] * len(picture.meters))

    def test_a_channel_carries_each_stems_clip(self):
        from display_panel import channel_picture
        clips = (False, True, False, False, True, False, False, False, True)
        p = channel_picture(8, (1.0,) * 9, 0, W, H, clips=clips)
        self.assertEqual(tuple(m.clip for m in p.meters), clips)

    def test_the_return_carries_stem_and_analogs_clip(self):
        from display_panel import STEM_MODE, return_picture
        p = return_picture(STEM_MODE, STEM_MODE, False, (1.0, 0.2), W, H, clips=(True, False))
        self.assertEqual([m.clip for m in p.meters], [True, False])

    def test_a_clip_is_shown_on_the_bar(self):
        from display_panel import Meter
        self.assertTrue(Meter((0, 0, 9, 44), 0.6, True).hatched())
        self.assertFalse(Meter((0, 0, 9, 44), 0.6, False).hatched())
        # No bar, nothing to hatch: no pixel moves.
        self.assertFalse(Meter((0, 0, 9, 44), 0.0, True).hatched())

    def test_a_clip_is_part_of_the_picture(self):
        """A clip lighting or going out is one redraw, nothing more."""
        from display_panel import STEM_MODE, channel_picture, pixel_key, return_picture
        clean = channel_picture(8, (1.0,) * 9, 0, W, H)
        over = channel_picture(8, (1.0,) * 9, 0, W, H, clips=(True,) + (False,) * 8)
        self.assertNotEqual(pixel_key(clean), pixel_key(over))
        self.assertNotEqual(
            pixel_key(return_picture(STEM_MODE, STEM_MODE, False, (1.0, 0.0), W, H)),
            pixel_key(return_picture(STEM_MODE, STEM_MODE, False, (1.0, 0.0), W, H,
                                     clips=(True, False))))


class MeterLevels(unittest.TestCase):
    def test_levels_map_in_db(self):
        from display_panel import meter_level
        self.assertEqual(meter_level(1.0), 1.0)
        self.assertAlmostEqual(meter_level(10 ** (-24 / 20)), 0.5)
        self.assertEqual(meter_level(10 ** (-60 / 20)), 0.0)
        for odd in (0, -1, None, "x", True, float("nan")):
            self.assertEqual(meter_level(odd), 0.0, odd)


class SelectorAnnouncements(unittest.TestCase):
    def test_a_cursor_is_zero_to_eight(self):
        from display_panel import cursor_announcement
        self.assertEqual(cursor_announcement((0,)), 0)
        self.assertEqual(cursor_announcement((8,)), 8)
        for args in ((9,), (-1,), (True,), (1.0,), ("1",), (1, 2), ()):
            self.assertIsNone(cursor_announcement(args), args)

    def test_a_mode_is_zero_or_one(self):
        from display_panel import mode_announcement
        self.assertEqual(mode_announcement((1,)), 1)
        for args in ((2,), (-1,), (True,), ()):
            self.assertIsNone(mode_announcement(args), args)


class StemPanels(unittest.TestCase):
    def test_channels_zero_to_three_are_the_four_decks(self):
        from display_panel import panel_for_channel
        self.assertEqual([panel_for_channel(i).label for i in range(4)],
                         ["Deck 1", "Deck 2", "Deck 3", "Deck 4"])

    def test_the_return_is_the_aux_return_panel(self):
        from display_panel import return_panel
        self.assertEqual(return_panel().label, "Aux Return")

    def test_the_mapping_hands_out_the_table_rows_themselves(self):
        from display_panel import PANELS, panel_for_channel, return_panel
        self.assertIs(panel_for_channel(0), PANELS[0])
        self.assertIs(return_panel(), PANELS[4])

    def test_a_channel_the_desk_does_not_have_is_refused(self):
        from display_panel import panel_for_channel
        for index in (-1, 4, 5):
            with self.assertRaises(IndexError):
                panel_for_channel(index)


def return_announcement_cursor(args):
    from display_panel import return_announcement
    announced = return_announcement(args)
    return None if announced is None else announced[0]


class StemAnnouncements(unittest.TestCase):
    def test_a_channel_announcement_is_a_mask(self):
        from display_panel import channel_announcement
        self.assertEqual(channel_announcement((0b100001,)), 0b100001)
        self.assertEqual(channel_announcement((255,)), 255)
        self.assertEqual(channel_announcement((0,)), 0)

    def test_a_damaged_channel_announcement_is_none(self):
        from display_panel import channel_announcement
        for args in ((), ("x",), (256,), (-1,), (None,), (1.5,), ("3",), (True,)):
            self.assertIsNone(channel_announcement(args), args)

    def test_a_return_announcement_is_cursor_and_eight_pairs(self):
        from display_panel import return_announcement
        self.assertEqual(return_announcement((1, 1, 0, 0, 1, 1, 1, 1, 1)),
                         (1, (True, False, False, True, True, True, True, True)))
        self.assertEqual(return_announcement((0,) * 9), (0, (False,) * 8))

    def test_the_cursor_is_analog_stem_or_cue(self):
        """The truth's words: 0 = analog, 1 = stem, 2 = cue (2026-10-04).
        A cursor past them used to pass and then broke the return's
        picture."""
        self.assertEqual(return_announcement_cursor((1,) + (1,) * 8), 1)
        self.assertEqual(return_announcement_cursor((2,) + (1,) * 8), 2)
        self.assertIsNone(return_announcement_cursor((3,) + (1,) * 8))

    def test_a_return_cue_is_on_or_off(self):
        """/aux-return/cue/led: f, 1.0 = on, as Core sends a lamp."""
        from display_panel import cue_announcement
        self.assertIs(cue_announcement((1.0,)), True)
        self.assertIs(cue_announcement((0.0,)), False)
        self.assertIs(cue_announcement((1,)), True)
        self.assertIs(cue_announcement((0,)), False)

    def test_a_damaged_return_cue_is_none(self):
        from display_panel import cue_announcement
        for args in ((), (0.5,), (2.0,), (-1.0,), (True,), ("1",), (None,),
                     (float("nan"),), (1.0, 1.0)):
            self.assertIsNone(cue_announcement(args), args)

    def test_a_damaged_return_announcement_is_none(self):
        from display_panel import return_announcement
        for args in ((), (1, 1), (1,) + (1,) * 7, (1,) + (1,) * 9,
                     (10,) + (1,) * 8, (1, 2) + (1,) * 7, ("a",) + (1,) * 8,
                     (1, True) + (1,) * 7):
            self.assertIsNone(return_announcement(args), args)


if __name__ == "__main__":
    unittest.main()
