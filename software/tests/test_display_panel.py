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
        self.assertEqual("FX Return", PANELS[-1].label)

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
    """A channel's display is an input selector: channel n's stem of D1, its
    stem of D2, and A -- the channel's analog input --, one meter each under
    D1 | D2 | A (2026-10-25: stem n plays only on channel n). It shows what is
    selected -- the cursor -- and what plays: the active bracket, over D1,
    D2 or A."""

    def picture(self, index=0, cursor=8, levels=(0.5,) * 3, mask=0, width=W, height=H):
        from display_panel import channel_picture
        return channel_picture(index, cursor, levels, mask, width, height)

    def test_the_ring_of_a_channel(self):
        from display_panel import ANALOG_INPUT, STEMS_PER_DECK, channel_ring
        self.assertEqual(STEMS_PER_DECK, 4)
        self.assertEqual(ANALOG_INPUT, 8)
        self.assertEqual([channel_ring(i) for i in range(4)],
                         [(0, 4, 8), (1, 5, 8), (2, 6, 8), (3, 7, 8)])

    def test_the_slot_of_a_cursor(self):
        from display_panel import channel_slot
        self.assertEqual([channel_slot(2, c) for c in (2, 6, 8)], [0, 1, 2])
        for off_ring in (0, 1, 3, 4, 5, 7):
            self.assertEqual(channel_slot(2, off_ring), 2, off_ring)

    def test_the_slot_that_plays(self):
        from display_panel import playing_slot
        self.assertEqual(playing_slot(2, 0), 2)
        self.assertEqual(playing_slot(2, stem(3)), 0)
        self.assertEqual(playing_slot(2, stem(7)), 1)
        self.assertEqual(playing_slot(2, stem(3) | stem(7)), 0)
        self.assertEqual(playing_slot(2, stem(1)), 2)
        self.assertEqual(playing_slot(2, stem(1) | stem(7)), 1)

    def test_three_headings_over_their_meters(self):
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["A", "B", "ST"])
        for heading, meter in zip(p.headings, p.meters):
            self.assertLess(heading.box[3], meter.box[1])

    def test_each_meter_is_centred_under_its_heading(self):
        p = self.picture()
        for heading, meter in zip(p.headings, p.meters):
            h, m = heading.box, meter.box
            self.assertLessEqual(h[0], m[0])
            self.assertGreaterEqual(h[2], m[2])
            self.assertLessEqual(abs((h[0] + h[2]) - (m[0] + m[2])), 1)

    def test_the_headings_span_the_old_grid(self):
        """The grid is unchanged: D1 and D2 head four stem slots each, as
        before, so the return panel beside it does not move."""
        from display_panel import _channel_columns
        slots = _channel_columns(W)
        p = self.picture()
        spans = [(slots[0][0], slots[3][1]), (slots[4][0], slots[7][1]), slots[8]]
        self.assertEqual([(h.box[0], h.box[2]) for h in p.headings], spans)

    def test_a_stands_over_the_analog_meter(self):
        p = self.picture()
        self.assertEqual(p.headings[2].box[1], p.headings[0].box[1])

    def test_three_meters_d1_d2_a(self):
        p = self.picture()
        boxes = [m.box for m in p.meters]
        self.assertEqual(len(boxes), 3)
        for box, heading in zip(boxes, p.headings):
            self.assertTrue(heading.box[0] <= box[0] <= heading.box[2], heading.text)
        for (x0, y0, x1, y1), following in zip(boxes, boxes[1:] + [None]):
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)
            if following:
                self.assertLess(x1, following[0])

    def test_every_meter_is_a_stems_size_and_height(self):
        boxes = [m.box for m in self.picture().meters]
        for box in boxes[1:]:
            self.assertEqual(box[2] - box[0], boxes[0][2] - boxes[0][0])
            self.assertEqual((box[1], box[3]), (boxes[0][1], boxes[0][3]))

    def test_no_toggle_any_more(self):
        self.assertIsNone(self.picture().toggle)
        self.assertIsNone(self.picture(mask=stem(1)).toggle)

    def test_the_groups_are_divided_by_lines(self):
        """D1 | D2 | A stand apart: a vertical line between each two
        meters, below the headings, the meters' height."""
        p = self.picture()
        boxes = [m.box for m in p.meters]
        self.assertEqual(len(p.dividers), 2)
        for (x0, y0, x1, y1), (left, right) in zip(p.dividers, ((0, 1), (1, 2))):
            self.assertEqual(x0, x1)
            self.assertGreaterEqual(x0 - boxes[left][2], 3)
            self.assertGreaterEqual(boxes[right][0] - x0, 3)
            self.assertGreater(y0, p.headings[0].box[3])
            self.assertEqual((y0, y1), (boxes[0][1], boxes[0][3]))

    def test_the_meters_keep_their_width(self):
        """A stem's width: as wide as the grid's stem slot."""
        from display_panel import _channel_columns
        x0, x1 = _channel_columns(W)[0]
        for box in [m.box for m in self.picture().meters]:
            self.assertEqual(box[2] - box[0], x1 - x0)
            self.assertGreaterEqual(box[2] - box[0] + 1, 9)

    def test_a_meter_is_its_level_clip_and_hold(self):
        """No assignment travels with a meter; whether it clips does
        (2026-10-04), and since 2026-10-07 its held peak (meter-ballistics)."""
        from display_panel import Meter
        self.assertEqual(Meter._fields, ("box", "level", "clip", "hold"))

    def test_the_levels_are_the_meters(self):
        levels = (0.25, 0.5, 0.75)
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
        pointing down at the selected meter."""
        p = self.picture(index=2, cursor=2)
        self.assert_arrow_over(p, p.meters[0].box)

    def test_the_cursor_on_d2_points_at_the_middle_meter(self):
        p = self.picture(index=1, cursor=5)
        self.assert_arrow_over(p, p.meters[1].box)

    def test_a_cursor_off_the_ring_shows_a(self):
        """A stored cursor outside channel n's ring (an older Core) is A,
        as Core takes it back."""
        p = self.picture(index=1, cursor=0)
        self.assert_arrow_over(p, p.meters[2].box)

    def test_the_arrow_is_as_wide_as_a_meter_and_a_few_rows_tall(self):
        p = self.picture(cursor=0)
        x0, y0, x1, y1 = p.cursor
        meter = p.meters[0].box
        self.assertEqual(x1 - x0, meter[2] - meter[0])
        self.assertIn(y1 - y0 + 1, (4, 5))

    def test_the_cursor_on_a_is_the_same_arrow_above_its_meter(self):
        p = self.picture(cursor=8)
        self.assert_arrow_over(p, p.meters[2].box)
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
    """Maintainer, 2026-10-04: what plays on the channel carries a bracket
    open at the bottom, the same mark as the return's active mode. On
    channel n that is D1's stem n, D2's stem n, or A when neither plays
    (2026-10-25). D1 wins when a mask carries both, and a foreign stem --
    only an older Core announces one -- is not this channel's: A."""

    def picture(self, mask, index=2, cursor=8):
        from display_panel import channel_picture
        return channel_picture(index, cursor, (0.5,) * 3, mask, W, H)

    def test_d1_plays_carries_the_bracket(self):
        p = self.picture(1 << 2)
        assert_bracket_over(self, p, p.meters[0].box)

    def test_d2_plays_carries_the_bracket(self):
        p = self.picture(1 << 6)
        assert_bracket_over(self, p, p.meters[1].box)

    def test_both_own_stems_bracket_d1(self):
        p = self.picture((1 << 2) | (1 << 6))
        assert_bracket_over(self, p, p.meters[0].box)

    def test_a_foreign_stem_shows_a(self):
        p = self.picture(1 << 0)
        assert_bracket_over(self, p, p.meters[2].box)

    def test_no_stem_the_analog_input_carries_it(self):
        p = self.picture(0)
        assert_bracket_over(self, p, p.meters[2].box)

    def test_the_bracket_and_the_cursor_on_one_stem(self):
        p = self.picture(1 << 2, cursor=2)
        assert_bracket_over(self, p, p.meters[0].box)

    def every_bracket(self):
        for index in range(4):
            for mask in (0, 1 << index, 1 << (4 + index)):
                yield (index, mask), self.picture(mask, index=index)

    def test_a_stem_playing_leaves_a_unmarked(self):
        for index in range(4):
            for mask in (1 << index, 1 << (4 + index)):
                p = self.picture(mask, index=index)
                self.assertLess(p.active[2], p.meters[2].box[0], (index, mask))

    def test_it_stays_on_the_panel(self):
        for case, p in self.every_bracket():
            x0, y0, x1, y1 = p.active
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H, case)

    def test_its_legs_stand_in_the_gaps(self):
        """The legs never cover a meter's own columns, its own or a
        neighbour's: the meters stay whole under the bracket."""
        for case, p in self.every_bracket():
            for leg in (p.active[0], p.active[2]):
                for meter in p.meters:
                    self.assertFalse(meter.box[0] <= leg <= meter.box[2], (case, leg))

    def test_it_never_touches_a_divider(self):
        for case, p in self.every_bracket():
            for divider in p.dividers:
                self.assertTrue(divider[0] < p.active[0] - 1 or divider[0] > p.active[2] + 1,
                                (case, divider))

    def test_the_arrow_stays_above_it(self):
        for case, p in self.every_bracket():
            self.assertGreater(p.active[1], p.cursor[3], case)
            self.assertGreater(p.active[1], max(h.box[3] for h in p.headings), case)


class ReturnMeter(unittest.TestCase):
    """P47: the FX Return is the master of the delay channel. Its display is
    one mono meter under AUX-RETURN -- the return after RETURN -- and the CUE
    field: no source to choose, so no second meter, no arrow and no active
    bracket."""

    def picture(self, level=0.5, cue=False):
        from display_panel import return_picture
        return return_picture(cue, level, W, H)

    def test_one_meter_under_one_name(self):
        p = self.picture(level=0.4)
        self.assertEqual([h.text for h in p.headings], ["AUX-RETURN"])
        self.assertEqual([m.level for m in p.meters], [0.4])
        heading, meter = p.headings[0].box, p.meters[0].box
        self.assertTrue(heading[0] <= meter[0] and meter[2] <= heading[2])
        self.assertLess(heading[3], meter[1])

    def test_the_name_has_a_box_wide_enough_for_one_legible_line(self):
        """AUX-RETURN is never cut and never shrunk into 43 px: its box is
        wide, the meter keeps its width."""
        p = self.picture()
        heading, meter = p.headings[0].box, p.meters[0].box
        self.assertGreaterEqual(heading[2] - heading[0] + 1, 80)
        self.assertLessEqual(meter[2] - meter[0] + 1, 24)

    def test_no_arrow_and_no_bracket(self):
        p = self.picture()
        self.assertIsNone(p.cursor)
        self.assertIsNone(p.active)

    def test_the_meter_is_centred_under_its_name_left_of_the_divider(self):
        p = self.picture()
        line = p.dividers[0][0]
        meter, heading = p.meters[0].box, p.headings[0].box
        self.assertLessEqual(abs((meter[0] + meter[2]) - (heading[0] + heading[2])), 1)
        self.assertLess(heading[2], line - 1)
        self.assertLessEqual(abs(heading[0] - (line - 1 - heading[2])), 3)

    def test_the_meter_keeps_its_look(self):
        from display_panel import RETURN_HEADING_OF_WIDTH, RETURN_METER_OF_HEADING
        heading = round(W * RETURN_HEADING_OF_WIDTH)
        p = self.picture()
        self.assertEqual(p.headings[0].box[2] - p.headings[0].box[0] + 1, heading)
        self.assertEqual(p.meters[0].box[2] - p.meters[0].box[0] + 1, round(heading * RETURN_METER_OF_HEADING))

    def test_the_headings_are_plain(self):
        from display_panel import Heading
        self.assertEqual(Heading._fields, ("box", "text"))

    def test_the_meter_stands_inside_the_panel(self):
        x0, y0, x1, y1 = self.picture().meters[0].box
        self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)

    def test_there_is_no_scale_any_more(self):
        from display_panel import Picture
        self.assertNotIn("ticks", Picture._fields)

    def test_no_source_words_are_left(self):
        import display_panel
        for gone in ("STEM_MODE", "ANALOG_MODE", "RETURN_OPTIONS", "CUE_CURSOR",
                     "return_announcement", "mode_announcement"):
            self.assertFalse(hasattr(display_panel, gone), gone)


class ReturnCue(unittest.TestCase):
    """Maintainer, 2026-10-04: the return gets a cue of its own -- a CUE
    field at the right edge behind a divider, in the slot where a channel
    shows A, so both displays read the same. Since P47 the encoder's push
    toggles it directly."""

    def picture(self, cue=False, level=0.5):
        from display_panel import return_picture
        return return_picture(cue, level, W, H)

    def channel(self, cursor=0):
        from display_panel import channel_picture
        return channel_picture(0, cursor, (0.5,) * 3, 0, W, H)

    def test_the_cue_field_reads_cue(self):
        self.assertEqual(self.picture().toggle.text, "CUE")

    def test_it_is_filled_while_the_cue_is_on(self):
        self.assertTrue(self.picture(cue=True).toggle.on)
        self.assertFalse(self.picture(cue=False).toggle.on)

    def test_it_stands_in_the_channels_a_slot(self):
        """Its size is the slot a channel's A heading spans, not a pixel
        number of its own: the two displays sit side by side on the desk."""
        x0, _, x1, _ = self.channel().headings[2].box
        _, y0, _, y1 = self.channel().meters[2].box
        self.assertEqual(self.picture().toggle.box, (x0, y0, x1, y1))

    def test_a_divider_sets_it_apart_where_the_channels_does(self):
        p, channel = self.picture(), self.channel()
        self.assertEqual(len(p.dividers), 1)
        self.assertEqual(p.dividers[0], channel.dividers[-1])

    def test_the_cue_moves_neither_meter_nor_heading(self):
        on, off = self.picture(cue=True), self.picture(cue=False)
        self.assertEqual([m.box for m in on.meters], [m.box for m in off.meters])
        self.assertEqual(on.headings, off.headings)

    def test_it_lays_out_on_a_short_panel_too(self):
        from display_panel import return_picture
        p = return_picture(True, 0.5, W, 32)
        for box in [m.box for m in p.meters] + [h.box for h in p.headings]:
            self.assertTrue(box[3] < 32, box)
        self.assertTrue(p.toggle.box[3] < 32)


class TheDisplaysHaveNoFallOfTheirOwn(unittest.TestCase):
    """Since 2026-10-07 every meter on the desk moves by one ballistics
    (a3_mixer_meters.MeterBallistics) on Core's timing; the displays' own
    fall and its constant are gone."""

    def test_no_own_fall(self):
        import display_panel
        self.assertFalse(hasattr(display_panel, "Ballistics"))
        self.assertFalse(hasattr(display_panel, "METER_FALL_DB_PER_SECOND"))

    def test_ten_steps_a_second(self):
        """25 does not fit the desk's draw time (~16 ms a panel, measured
        2026-10-07); see METER_STEPS_PER_SECOND."""
        from display_panel import METER_STEPS_PER_SECOND
        self.assertEqual(METER_STEPS_PER_SECOND, 10)


class TheHoldLine(unittest.TestCase):
    """The held peak is a one-row line over the bar (meter-ballistics,
    2026-10-07), in the meter's own box, at the row a bar at that level
    has its top."""

    BOX = (10, 20, 19, 59)              # 40 rows

    def meter(self, level, hold):
        from display_panel import Meter
        return Meter(self.BOX, level, False, hold)

    def test_a_hold_above_the_bar_is_a_row(self):
        self.assertEqual(self.meter(0.25, 0.5).hold_row(), 59 - 20 + 1)

    def test_the_hold_at_full_scale_is_the_top_row(self):
        self.assertEqual(self.meter(0.0, 1.0).hold_row(), 20)

    def test_a_hold_inside_the_bar_is_no_line(self):
        self.assertIsNone(self.meter(0.5, 0.5).hold_row())
        self.assertIsNone(self.meter(0.5, 0.49).hold_row())

    def test_no_hold_is_no_line(self):
        self.assertIsNone(self.meter(0.0, 0.0).hold_row())
        from display_panel import Meter
        self.assertIsNone(Meter(self.BOX, 0.3).hold_row())

    def test_a_channel_carries_a_hold_per_meter(self):
        from display_panel import channel_picture
        holds = (0.9, 0.0, 0.0)
        p = channel_picture(0, 8, (0.1,) * 3, 0, W, H, holds=holds)
        self.assertIsNotNone(p.meters[0].hold_row())
        self.assertEqual([m.hold_row() for m in p.meters[1:]], [None] * 2)

    def test_the_return_carries_its_hold(self):
        from display_panel import return_picture
        self.assertIsNone(return_picture(False, 0.1, W, H).meters[0].hold_row())
        self.assertIsNotNone(return_picture(False, 0.1, W, H, hold=0.8).meters[0].hold_row())

    def test_a_moved_hold_is_a_new_picture(self):
        from display_panel import channel_picture, pixel_key
        one = channel_picture(0, 8, (0.1,) * 3, 0, W, H, holds=(0.9, 0.0, 0.0))
        two = channel_picture(0, 8, (0.1,) * 3, 0, W, H, holds=(0.6, 0.0, 0.0))
        self.assertNotEqual(pixel_key(one), pixel_key(two))


class InPixels(unittest.TestCase):
    """A panel is redrawn when its pixels change, not its floats: the bus
    carries ~17 draws a second, and a fall of less than a row is no draw."""

    def channel(self, cursor=8, level=0.0, mask=0):
        from display_panel import channel_picture
        return channel_picture(0, cursor, (level,) * 3, mask, W, H)

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
        self.assertEqual([m.pixels() for m in self.channel(cursor=0).meters], [0] * 3)

    def test_the_cursor_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(cursor=0)), pixel_key(self.channel(cursor=1)))
        self.assertNotEqual(pixel_key(self.channel(cursor=4)), pixel_key(self.channel(cursor=8)))

    def test_stem_or_analog_playing_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(mask=stem(1))),
                            pixel_key(self.channel(mask=0)))

    def test_the_active_stem_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(mask=stem(1))),
                            pixel_key(self.channel(mask=stem(5))))

    def test_d2_beside_a_playing_d1_is_the_same_picture(self):
        from display_panel import pixel_key
        self.assertEqual(pixel_key(self.channel(mask=stem(1))),
                         pixel_key(self.channel(mask=stem(1) | stem(5))))

    def test_the_return_cue_is_part_of_the_picture(self):
        """A cue switched on or off is one redraw of the return panel."""
        from display_panel import pixel_key, return_picture
        self.assertNotEqual(pixel_key(return_picture(False, 0.0, W, H)),
                            pixel_key(return_picture(True, 0.0, W, H)))

    def test_the_return_in_rows(self):
        from display_panel import pixel_key, return_picture
        one = return_picture(False, 0.500, W, H)
        two = return_picture(False, 0.505, W, H)
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
        self.assertAlmostEqual(meter_level(10 ** (-12 / 20)), 0.5)

    def test_a_meter_does_not_clip_unless_told(self):
        from display_panel import Meter, channel_picture, return_picture
        self.assertFalse(Meter((0, 0, 9, 9), 1.0).clip)
        pictures = (channel_picture(0, 8, (1.0,) * 3, 0, W, H),
                    return_picture(False, 1.0, W, H))
        for picture in pictures:
            self.assertEqual([m.clip for m in picture.meters], [False] * len(picture.meters))

    def test_a_channel_carries_each_stems_clip(self):
        from display_panel import channel_picture
        clips = (False, True, True)
        p = channel_picture(0, 8, (1.0,) * 3, 0, W, H, clips=clips)
        self.assertEqual(tuple(m.clip for m in p.meters), clips)

    def test_the_return_carries_its_clip(self):
        from display_panel import return_picture
        self.assertEqual([m.clip for m in return_picture(False, 1.0, W, H, clip=True).meters], [True])

    def test_a_clip_is_shown_on_the_bar(self):
        from display_panel import Meter
        self.assertTrue(Meter((0, 0, 9, 44), 0.6, True).hatched())
        self.assertFalse(Meter((0, 0, 9, 44), 0.6, False).hatched())
        # No bar, nothing to hatch: no pixel moves.
        self.assertFalse(Meter((0, 0, 9, 44), 0.0, True).hatched())

    def test_a_clip_is_part_of_the_picture(self):
        """A clip lighting or going out is one redraw, nothing more."""
        from display_panel import channel_picture, pixel_key, return_picture
        clean = channel_picture(0, 8, (1.0,) * 3, 0, W, H)
        over = channel_picture(0, 8, (1.0,) * 3, 0, W, H, clips=(True, False, False))
        self.assertNotEqual(pixel_key(clean), pixel_key(over))
        self.assertNotEqual(pixel_key(return_picture(False, 1.0, W, H)),
                            pixel_key(return_picture(False, 1.0, W, H, clip=True)))


class MeterLevels(unittest.TestCase):
    def test_levels_map_on_the_channel_leds_scale(self):
        """Each LED threshold at its eighth (test_display_led_scale has the
        whole table)."""
        from display_panel import meter_level
        self.assertEqual(meter_level(1.0), 1.0)
        self.assertAlmostEqual(meter_level(10 ** (-24 / 20)), 0.25)
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


class StemPanels(unittest.TestCase):
    def test_channels_zero_to_three_are_the_four_decks(self):
        from display_panel import panel_for_channel
        self.assertEqual([panel_for_channel(i).label for i in range(4)],
                         ["Deck 1", "Deck 2", "Deck 3", "Deck 4"])

    def test_the_return_is_the_fx_return_panel(self):
        from display_panel import return_panel
        self.assertEqual(return_panel().label, "FX Return")

    def test_the_mapping_hands_out_the_table_rows_themselves(self):
        from display_panel import PANELS, panel_for_channel, return_panel
        self.assertIs(panel_for_channel(0), PANELS[0])
        self.assertIs(return_panel(), PANELS[4])

    def test_a_channel_the_desk_does_not_have_is_refused(self):
        from display_panel import panel_for_channel
        for index in (-1, 4, 5):
            with self.assertRaises(IndexError):
                panel_for_channel(index)


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


if __name__ == "__main__":
    unittest.main()
