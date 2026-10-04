# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live displays, with the hardware faked: one device per panel for the
life of the process, rebuilt only after a failure, and nothing raised.

Since 2026-10-01 the OSC thread only posts what to show; drawing happens on a
thread of its own, and a panel shows the latest of what was posted -- a fast
spin used to queue one full draw per click behind the meters. Tests call
drain() to draw what is posted, the live desk runs it on start()."""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_displays import DrawTimer, Displays, Multiplexer, Picture, paint


def stem(pair):
    """The mask Core announces for a channel playing that one pair."""
    return 1 << (pair - 1)


def cursor_of(picture):
    """The input the cursor is under: the meter that starts where it does."""
    return [m.box[0] for m in picture.meters].index(picture.cursor[0])


class Rig:
    def __init__(self):
        self.selected = []
        self.built = []
        self.drawn = []
        self.fail_draw = False
        self.reports = []

    def select(self, multiplexer, channel):
        self.selected.append(channel)

    def make_device(self, panel):
        device = type("Device", (), {"persist": False, "width": 128, "height": 64})()
        self.built.append((panel.label, device))
        return device

    def draw(self, device, squares):
        if self.fail_draw:
            raise OSError("nack")
        self.drawn.append((device, squares))

    def displays(self, **options):
        return Displays(self.select, self.make_device, self.draw, self.reports.append,
                        **options)


class OneDevicePerPanel(unittest.TestCase):
    def test_two_draws_build_the_device_once(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_cursor(0, 0)
        displays.drain()
        displays.show_cursor(0, 1)
        displays.drain()
        self.assertEqual(1, len(rig.built))
        self.assertEqual(2, len(rig.drawn))

    def test_the_device_persists_past_exit(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_cursor(0, 0)
        displays.drain()
        self.assertTrue(rig.built[0][1].persist)

    def test_the_multiplexer_is_selected_before_every_draw(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_cursor(0, 0)
        displays.drain()
        displays.show_cursor(0, 1)
        displays.drain()
        displays.show_return(1, (True,) * 8)   # the return's own display
        displays.drain()
        self.assertEqual([2, 2, 6], rig.selected)

    def test_each_panel_has_its_own_device(self):
        rig = Rig()
        displays = rig.displays()
        displays.blank_all()
        displays.drain()
        self.assertEqual(5, len(rig.built))


class LatestWins(unittest.TestCase):
    def test_posting_draws_nothing_yet(self):
        rig = Rig()
        rig.displays().show_channel(0, stem(1))
        self.assertEqual([], rig.drawn)

    def test_a_fast_spin_is_one_draw_of_where_it_ended(self):
        rig = Rig()
        displays = rig.displays()
        for pair in (1, 2, 3, 4):
            displays.show_cursor(0, pair - 1)
        displays.drain()
        self.assertEqual(1, len(rig.drawn))
        self.assertEqual(cursor_of(rig.drawn[0][1]), 3)

    def test_each_panel_keeps_its_own_latest(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, stem(1))
        displays.show_return(1, (True,) * 8)
        displays.show_channel(0, stem(2))
        displays.drain()
        self.assertEqual(2, len(rig.drawn))   # each panel once, with its latest

    def test_the_thread_draws_what_is_posted(self):
        rig = Rig()
        drawn = threading.Event()
        draw = rig.draw
        rig.draw = lambda device, squares: (draw(device, squares), drawn.set())
        displays = rig.displays()
        displays.start()
        displays.show_channel(0, stem(1))
        self.assertTrue(drawn.wait(2.0))


class WhatIsDrawn(unittest.TestCase):
    def test_a_channel_is_sized_to_the_device(self):
        rig = Rig()
        rig.make_device = lambda panel: type(
            "Device", (), {"persist": False, "width": 128, "height": 32})()
        displays = rig.displays()
        displays.show_channel(0, stem(1))
        displays.drain()
        _, picture = rig.drawn[0]                       # Deck 1, first in the table
        self.assertEqual([h.text for h in picture.headings], ["D1", "D2", "A"])
        self.assertEqual([m.solid for m in picture.meters], [True] + [False] * 8)
        self.assertTrue(all(m.box[3] < 32 for m in picture.meters))

    def test_the_return_shows_sa_and_a(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_return(0, (True,) * 8)
        displays.show_return_mode(1)
        displays.drain()
        _, picture = rig.drawn[-1]
        self.assertEqual([h.text for h in picture.headings], ["SA", "A"])
        self.assertEqual([m.solid for m in picture.meters], [True, True, False, False])
        self.assertEqual(cursor_of(picture), 2)         # cursor 0 = analog = A's pair


class AfterAFailure(unittest.TestCase):
    def test_a_failed_draw_drops_the_device_and_the_next_rebuilds(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_cursor(0, 0)
        displays.drain()
        rig.fail_draw = True
        displays.show_cursor(0, 1)
        displays.drain()
        rig.fail_draw = False
        displays.show_cursor(0, 2)
        displays.drain()
        self.assertEqual(2, len(rig.built))
        self.assertEqual(cursor_of(rig.drawn[-1][1]), 2)   # drawn after the rebuild

    def test_a_failure_never_raises_and_is_reported_once(self):
        rig = Rig()
        displays = rig.displays()
        rig.fail_draw = True
        displays.show_cursor(1, 0)
        displays.drain()
        displays.show_cursor(1, 1)
        displays.drain()
        self.assertEqual(1, len(rig.reports))


class TryingAgain(unittest.TestCase):
    """A failed draw is tried again a little later with the panel's latest
    picture -- not left until the panel next changes."""

    def test_a_failed_draw_is_tried_again_later(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_cursor(0, 2)
        displays.drain()
        self.assertEqual(1, len(scheduled))
        rig.fail_draw = False
        scheduled[0][1]()
        displays.drain()
        self.assertEqual(cursor_of(rig.drawn[-1][1]), 2)

    def test_the_retry_draws_what_was_posted_since(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_cursor(0, 2)
        displays.drain()
        rig.fail_draw = False
        displays.show_cursor(0, 4)
        displays.drain()
        scheduled[0][1]()
        displays.drain()
        self.assertEqual(cursor_of(rig.drawn[-1][1]), 4)

    def test_a_good_draw_schedules_nothing(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        displays.show_cursor(0, 2)
        displays.drain()
        self.assertEqual([], scheduled)


class Meters(unittest.TestCase):
    """Meters are noted on the OSC thread; a step on the displays' own clock
    takes the loudest peak since the last step, runs it through the meter's
    ballistics and redraws every panel whose pixels moved. What a turn posts
    is drawn with the latest levels."""

    def setUp(self):
        self.now = 0.0
        self.rig = Rig()
        self.displays = self.rig.displays(clock=lambda: self.now)
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def levels(self, label):
        """The meters as the panel would be drawn now."""
        from display_panel import PANELS
        panel = next(p for p in PANELS if p.label == label)
        return [m.level for m in self.displays._picture_for(panel)(128, 64).meters]

    def peaks(self, label):
        from display_panel import PANELS
        panel = next(p for p in PANELS if p.label == label)
        return [m.peak for m in self.displays._picture_for(panel)(128, 64).meters]

    def step(self):
        """One step a tenth of a second after the last, as on the desk."""
        from display_panel import METER_STEPS_PER_SECOND
        self.now += 1.0 / METER_STEPS_PER_SECOND
        self.displays.step_meters()
        self.displays.drain()

    def fall(self, seconds):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_FLOOR_DB
        return METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB * seconds

    def test_a_channel_meters_every_stem_and_its_own_analog_input(self):
        self.displays.note_peak(3, 1.0)
        self.displays.note_analog(1, 1.0)
        self.step()
        self.assertEqual(self.levels("Deck 2"), [0, 0, 1.0, 0, 0, 0, 0, 0, 1.0])
        self.assertEqual(self.levels("Deck 1"), [0, 0, 1.0, 0, 0, 0, 0, 0, 0])

    def test_a_is_the_analog_return_left_and_right(self):
        self.displays.note_aux(0, 10 ** (-24 / 20))
        self.displays.note_aux(1, 10 ** (-12 / 20))
        self.step()
        _, _, left, right = self.levels("Aux Return")
        self.assertAlmostEqual(left, 0.5)
        self.assertAlmostEqual(right, 0.75)

    def test_without_the_bus_meters_sa_is_the_loudest_stem_on_the_return(self):
        """The truth before stem_aux_L/R: SA falls back to what it showed
        until 2026-10-04, the loudest stem playing on the return, both sides."""
        self.displays.show_return(1, (False, True, False, True) + (False,) * 4)
        self.displays.note_peak(1, 1.0)                 # not on the return
        self.displays.note_peak(2, 10 ** (-24 / 20))
        self.step()
        sa_left, sa_right, _, _ = self.levels("Aux Return")
        self.assertAlmostEqual(sa_left, 0.5)
        self.assertAlmostEqual(sa_right, 0.5)

    def test_with_the_bus_meters_sa_is_the_stemdecks_aux_bus(self):
        self.displays.show_return(1, (True,) * 8)
        self.displays.note_peak(1, 1.0)                 # on the return, but the bus rules
        self.displays.note_stem_aux(0, 10 ** (-24 / 20))
        self.displays.note_stem_aux(1, 10 ** (-12 / 20))
        self.step()
        sa_left, sa_right, _, _ = self.levels("Aux Return")
        self.assertAlmostEqual(sa_left, 0.5)
        self.assertAlmostEqual(sa_right, 0.75)

    def test_a_bus_that_was_heard_stays_the_source_in_silence(self):
        """Once the truth has the bus meters, a quiet bus is a quiet SA --
        not the stems again."""
        self.displays.show_return(1, (True,) * 8)
        self.displays.note_stem_aux(0, 0.0)
        self.displays.note_peak(1, 1.0)
        self.step()
        self.assertEqual(self.levels("Aux Return")[:2], [0.0, 0.0])

    def test_a_step_redraws_every_panel_whose_meters_moved(self):
        self.displays.note_peak(1, 1.0)                 # on every channel's meters
        self.step()
        self.assertEqual(4, len(self.rig.drawn))

    def test_unmoved_meters_are_not_redrawn(self):
        self.step()
        self.assertEqual([], self.rig.drawn)

    def test_the_meter_holds_the_peak_between_steps(self):
        """StemDeck sends a 40 ms peak 25 times a second; a step every 100 ms
        must show the loudest of them, not the last."""
        self.displays.note_peak(1, 1.0)
        self.displays.note_peak(1, 0.001)
        self.step()
        self.assertEqual(self.levels("Deck 1")[0], 1.0)

    def test_the_meter_falls_smoothly(self):
        self.displays.note_peak(1, 1.0)
        self.step()
        self.displays.note_peak(1, 0.001)
        self.step()
        self.assertAlmostEqual(self.levels("Deck 1")[0], 1.0 - self.fall(0.1))

    def test_the_peak_mark_holds_a_second(self):
        self.displays.note_analog(0, 1.0)
        self.step()
        for _ in range(10):
            self.displays.note_analog(0, 0.001)
            self.step()
        self.assertAlmostEqual(self.peaks("Deck 1")[8], 1.0)
        self.displays.note_analog(0, 0.001)
        self.step()
        self.assertAlmostEqual(self.peaks("Deck 1")[8], 1.0 - self.fall(0.1))

    def test_a_move_of_less_than_a_pixel_posts_nothing(self):
        """The bus carries ~17 draws a second (measured 2026-10-04): a panel
        whose floats moved but whose pixels did not is not redrawn."""
        self.displays.note_peak(1, 1.0)
        self.step()
        self.rig.drawn.clear()
        self.displays.note_peak(1, 10 ** (-0.3 / 20))  # 0.3 dB down: under one row
        self.step()
        self.assertNotEqual(self.levels("Deck 1")[0], 1.0)
        self.assertEqual([], self.rig.drawn)

    def test_a_fall_redraws_until_it_rests(self):
        self.displays.note_peak(1, 1.0)
        self.step()
        draws = 0
        for _ in range(60):                             # six seconds of silence
            self.rig.drawn.clear()
            self.step()
            draws += len(self.rig.drawn)
        self.assertGreater(draws, 0)
        self.assertEqual([], self.rig.drawn)            # at rest: nothing more

    def test_a_meter_that_stopped_is_silence(self):
        self.displays.note_analog(0, 1.0)
        self.now = 5.0
        self.step()
        self.assertEqual(self.levels("Deck 1")[8], 0.0)

    def test_noting_a_peak_draws_nothing(self):
        self.displays.note_peak(1, 1.0)
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)

    def test_the_clock_steps_at_the_rate(self):
        from display_panel import METER_STEPS_PER_SECOND
        self.displays.note_peak(1, 1.0)
        self.displays.tick()
        self.displays.drain()
        self.assertEqual(4, len(self.rig.drawn))
        self.rig.drawn.clear()
        self.now = 0.5 / METER_STEPS_PER_SECOND
        self.displays.note_peak(1, 0.5)
        self.displays.tick()
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)
        self.now = 1.0 / METER_STEPS_PER_SECOND
        self.displays.note_peak(1, 0.001)
        self.displays.tick()
        self.displays.drain()
        self.assertEqual(4, len(self.rig.drawn))        # the fall moved a row

    def test_a_turn_during_a_step_goes_first(self):
        """A step redraws every moved panel (~85 ms on the desk); a turn
        arriving meanwhile is drawn next, not after the batch."""
        self.displays.note_peak(1, 1.0)
        order = []
        labels = {id(device): name for name, device in self.rig.built}
        draw = self.rig.draw

        def draw_and_turn(device, picture):
            draw(device, picture)
            order.append(labels[id(device)])
            if len(order) == 1:
                self.displays.show_cursor(3, 4)         # Deck 4, last of the decks

        self.displays._draw_fields = draw_and_turn
        self.step()
        self.assertEqual(order, ["Deck 1", "Deck 4", "Deck 2", "Deck 3"])

    def test_a_turn_keeps_the_levels(self):
        self.displays.note_analog(0, 1.0)
        self.step()
        self.rig.drawn.clear()
        self.displays.show_cursor(0, 2)
        self.displays.drain()
        _, picture = self.rig.drawn[0]
        self.assertEqual(cursor_of(picture), 2)
        self.assertEqual(picture.meters[8].level, 1.0)


class WhatPlaysWhere(unittest.TestCase):
    """What plays on a channel, and its cursor, show on its own display."""

    def setUp(self):
        self.rig = Rig()
        self.displays = self.rig.displays()
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def test_a_stem_change_redraws_its_own_display(self):
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertTrue(self.rig.drawn[0][1].meters[2].solid)

    def test_a_cursor_redraws_its_own_display(self):
        self.displays.show_cursor(1, 6)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertEqual(cursor_of(self.rig.drawn[0][1]), 6)

    def test_the_cursor_starts_on_a(self):
        self.displays.show_channel(0, 0)
        self.displays.drain()
        self.assertEqual(cursor_of(self.rig.drawn[0][1]), 8)

    def test_there_is_no_wave_or_menu_any_more(self):
        for gone in ("show_menu", "step_waves", "show_cue"):
            self.assertFalse(hasattr(self.displays, gone), gone)


class Painting(unittest.TestCase):
    """The painter on a real 128x64 1-bit image (rule: a page test must
    paint). A3_SNAPSHOTS=<dir> saves each state as a PNG."""

    def paint_state(self, name, picture):
        from PIL import Image
        image = Image.new("1", (128, 64))
        paint(image, picture)
        folder = __import__("os").environ.get("A3_SNAPSHOTS")
        if folder:
            image.resize((512, 256)).save(Path(folder) / f"desk-meters-{name}.png")
        return image

    def lit(self, image, box):
        return [(x, y) for x in range(box[0], box[2] + 1)
                for y in range(box[1], box[3] + 1) if image.getpixel((x, y))]

    def states(self):
        from display_panel import channel_picture, return_picture
        levels = (0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 0.0, 0.6, 0.7)
        peaks = (0.4, 0.95, 0.1, 0.5, 1.0, 0.55, 0.0, 0.8, 0.85)
        return {
            "channel-analog": channel_picture(8, 0, levels, 128, 64, peaks=peaks),
            "channel-stem": channel_picture(2, stem(5), levels, 128, 64, peaks=peaks),
            "channel-silent": channel_picture(0, stem(1), (0.0,) * 9, 128, 64),
            "return-stem": return_picture(1, 1, (0.8, 0.7, 0.3, 0.25), 128, 64,
                                          peaks=(1.0, 0.85, 0.5, 0.25)),
            "return-analog": return_picture(0, 0, (0.4, 0.45, 0.9, 0.75), 128, 64,
                                            peaks=(0.6, 0.45, 1.0, 0.9)),
            "return-silent": return_picture(1, 1, (0.0,) * 4, 128, 64),
        }

    def test_each_state_paints_its_headings_and_cursor(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                for heading in picture.headings:
                    self.assertTrue(self.lit(image, heading.box), heading.text)
                x0, y0, x1, y1 = picture.cursor
                self.assertEqual(len(self.lit(image, picture.cursor)),
                                 (x1 - x0 + 1) * (y1 - y0 + 1))

    def test_nothing_spills_out_of_its_box(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(f"fit-{name}", picture)
                boxes = [h.box for h in picture.headings] + [m.box for m in picture.meters]
                boxes += [t.box for t in picture.ticks]
                boxes.append(picture.cursor)
                inside = {(x, y) for x0, y0, x1, y1 in boxes
                          for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
                spilled = [(x, y) for x in range(128) for y in range(64)
                           if image.getpixel((x, y)) and (x, y) not in inside]
                self.assertEqual(spilled, [])

    def test_what_plays_is_solid_even_in_silence(self):
        picture = self.states()["channel-silent"]
        image = self.paint_state("silent", picture)
        x0, _, x1, y1 = picture.meters[0].box
        self.assertTrue(all(image.getpixel((x, y1 - 1)) for x in range(x0, x1 + 1)))

    def test_the_others_are_outlined_not_filled(self):
        picture = self.states()["channel-analog"]
        image = self.paint_state("outlined", picture)
        x0, y0, x1, y1 = picture.meters[4].box          # level 1.0, not playing
        middle = (x0 + x1) // 2
        self.assertTrue(image.getpixel((x0, y1)) and image.getpixel((x1, y1)))
        self.assertFalse(image.getpixel((middle, (y0 + y1) // 2)))
        x0, y0, x1, y1 = picture.meters[8].box          # A: plays, level 0.7
        self.assertTrue(image.getpixel(((x0 + x1) // 2, y1 - 2)))

    def test_the_peak_is_a_thin_mark_above_the_bar(self):
        picture = self.states()["channel-analog"]
        image = self.paint_state("peak", picture)
        meter = picture.meters[0]                       # level 0.2, peak 0.4, outlined
        x0, y0, x1, y1 = meter.box
        bar, peak = meter.pixels()
        middle = (x0 + x1) // 2
        self.assertTrue(image.getpixel((middle, y1 - peak + 1)))
        self.assertFalse(image.getpixel((middle, y1 - peak + 2)))
        self.assertFalse(image.getpixel((middle, y1 - peak)))

    def middle_of(self, bar, index):
        from display_panel import segment_rows
        top, bottom = segment_rows(bar, index)
        return (bar.box[0] + bar.box[2]) // 2, (top + bottom) // 2

    def test_the_playing_pair_is_filled_the_other_outlined(self):
        picture = self.states()["return-stem"]
        image = self.paint_state("return-fill", picture)
        sa, a = picture.meters[0], picture.meters[2]
        self.assertTrue(image.getpixel(self.middle_of(sa, 0)))
        x, y = self.middle_of(a, 0)
        self.assertFalse(image.getpixel((x, y)))
        self.assertTrue(image.getpixel((a.box[0], y)) and image.getpixel((a.box[2], y)))

    def test_segments_are_apart_and_the_peak_stands_alone(self):
        from display_panel import segment_rows
        picture = self.states()["return-stem"]
        image = self.paint_state("return-segments", picture)
        bar = picture.meters[0]                         # level 0.8, peak 1.0
        lit, peak = bar.pixels()
        x = (bar.box[0] + bar.box[2]) // 2
        top, _ = segment_rows(bar, 0)
        self.assertFalse(image.getpixel((x, top - 1)))  # the row between two segments
        self.assertTrue(image.getpixel(self.middle_of(bar, peak - 1)))
        self.assertFalse(image.getpixel(self.middle_of(bar, lit)))

    def test_in_silence_both_pairs_still_show_which_plays(self):
        picture = self.states()["return-silent"]
        image = self.paint_state("return-quiet", picture)
        for bar in picture.meters:
            x, y = self.middle_of(bar, 0)
            self.assertEqual(bool(image.getpixel((x, y))), bar.solid)
            self.assertTrue(image.getpixel((bar.box[0], y)))
            self.assertFalse(image.getpixel(self.middle_of(bar, 1)))

    def test_the_scale_marks_are_painted(self):
        picture = self.states()["return-silent"]
        image = self.paint_state("return-scale", picture)
        for tick in picture.ticks:
            self.assertTrue(self.lit(image, tick.box), tick.text)


class HowLongADrawTakes(unittest.TestCase):
    """One journal line per batch of draws, so the bus speed is measured on
    the desk instead of guessed."""

    def test_the_desk_reports_seldom(self):
        """Final review: with waves the displays draw all the time; a line
        every 20 draws was one every 0.8 s in the journal."""
        rig = Rig()
        displays = rig.displays()
        for pair in range(100):
            displays.show_cursor(0, pair % 5)
            displays.drain()
        self.assertEqual([], rig.reports)

    def test_a_line_after_every_batch(self):
        timer = DrawTimer(every=3)
        self.assertIsNone(timer.record(0.010))
        self.assertIsNone(timer.record(0.020))
        self.assertEqual(timer.record(0.030),
                         "displays: 3 draws, mean 20.0 ms, max 30.0 ms")

    def test_each_batch_starts_afresh(self):
        timer = DrawTimer(every=2)
        timer.record(0.100)
        timer.record(0.100)
        timer.record(0.004)
        self.assertEqual(timer.record(0.006),
                         "displays: 2 draws, mean 5.0 ms, max 6.0 ms")

    def test_the_displays_report_it(self):
        rig = Rig()
        ticks = iter([0.0, 0.012, 1.0, 1.020])
        displays = rig.displays(clock=lambda: next(ticks), every=2)
        displays.show_cursor(0, 0)
        displays.drain()
        displays.show_cursor(1, 0)
        displays.drain()
        self.assertEqual(rig.reports, ["displays: 2 draws, mean 16.0 ms, max 20.0 ms"])


class TheMultiplexer(unittest.TestCase):
    """One open bus, one byte per select: no new SMBus, no 1 ms sleep, no
    read-back and no journal line per draw, as TCA9548A.I2C_setup does."""

    class Bus:
        def __init__(self, log, fail=False):
            self.log, self.fail = log, fail

        def write_byte(self, address, value):
            if self.fail:
                raise OSError("nack")
            self.log.append((address, value))

        def close(self):
            self.log.append("closed")

    def test_the_bus_is_opened_once(self):
        log, opened = [], []
        mux = Multiplexer(lambda: opened.append(1) or self.Bus(log))
        mux(0x70, 2)
        mux(0x70, 6)
        self.assertEqual(1, len(opened))
        self.assertEqual(log, [(0x70, 0b100), (0x70, 0b1000000)])

    def test_a_failed_select_reopens_the_bus_next_time(self):
        log, buses = [], [self.Bus([], fail=True)]
        mux = Multiplexer(lambda: buses.pop(0) if buses else self.Bus(log))
        with self.assertRaises(OSError):
            mux(0x70, 2)
        mux(0x70, 3)
        self.assertEqual(log, [(0x70, 0b1000)])


if __name__ == "__main__":
    unittest.main()
