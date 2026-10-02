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
        displays.show_menu(0, 1, 0)
        displays.drain()
        displays.show_menu(0, 1, 1)
        displays.drain()
        self.assertEqual(1, len(rig.built))
        self.assertEqual(2, len(rig.drawn))

    def test_the_device_persists_past_exit(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_menu(0, 1, 0)
        displays.drain()
        self.assertTrue(rig.built[0][1].persist)

    def test_the_multiplexer_is_selected_before_every_draw(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_menu(0, 1, 0)
        displays.drain()
        displays.show_menu(0, 1, 1)
        displays.drain()
        displays.show_return(1, (True,) * 8)   # what plays where: all five redraw
        displays.drain()
        self.assertEqual([2, 2], rig.selected[:2])
        self.assertEqual(7, len(rig.selected))
        self.assertIn(6, rig.selected[2:])

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
            displays.show_menu(0, 1, pair - 1)
        displays.drain()
        self.assertEqual(1, len(rig.drawn))
        self.assertEqual([i.inverted for i in rig.drawn[0][1].items].index(True), 4)

    def test_each_panel_keeps_its_own_latest(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, stem(1))
        displays.show_return(2, (True,) * 8)
        displays.show_channel(0, stem(2))
        displays.drain()
        self.assertEqual(5, len(rig.drawn))   # every panel once, each with its latest

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
    def test_the_menu_is_sized_to_the_device(self):
        rig = Rig()
        rig.make_device = lambda panel: type(
            "Device", (), {"persist": False, "width": 128, "height": 32})()
        displays = rig.displays()
        displays.show_channel(0, stem(1))
        displays.drain()
        device, picture = rig.drawn[0]                 # Deck 1, first in the table
        self.assertTrue(all(i.box[3] < 16 for i in picture.items))
        self.assertEqual([i.marked for i in picture.items], [True, False, False])  # D1 plays
        self.assertTrue(all(16 <= top <= bottom < 32 for _, top, bottom in picture.wave))

    def test_the_return_shows_its_mode_and_cursor(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_return(0, (True,) * 8)
        displays.show_return_mode(1)
        displays.drain()
        device, picture = rig.drawn[-1]
        self.assertEqual([i.text for i in picture.items], ["STEM", "ANALOG"])
        self.assertEqual([i.inverted for i in picture.items], [False, True])
        self.assertEqual([i.marked for i in picture.items], [True, False])
        self.assertEqual(picture.wave, [])
        self.assertEqual(len(picture.bars), 10)


class AfterAFailure(unittest.TestCase):
    def test_a_failed_draw_drops_the_device_and_the_next_rebuilds(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_menu(0, 1, 0)
        displays.drain()
        rig.fail_draw = True
        displays.show_menu(0, 1, 1)
        displays.drain()
        rig.fail_draw = False
        displays.show_menu(0, 1, 2)
        displays.drain()
        self.assertEqual(2, len(rig.built))
        framed = [i.inverted for i in rig.drawn[-1][1].items]
        self.assertEqual(framed.index(True), 3)   # stem 3 drawn after the rebuild

    def test_a_failure_never_raises_and_is_reported_once(self):
        rig = Rig()
        displays = rig.displays()
        rig.fail_draw = True
        displays.show_menu(1, 1, 0)
        displays.drain()
        displays.show_menu(1, 1, 1)
        displays.drain()
        self.assertEqual(1, len(rig.reports))


class TryingAgain(unittest.TestCase):
    """A failed draw is tried again a little later with the panel's latest
    picture -- not left until the panel next changes."""

    def test_a_failed_draw_is_tried_again_later(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_menu(0, 1, 2)
        displays.drain()
        self.assertEqual(1, len(scheduled))
        rig.fail_draw = False
        scheduled[0][1]()
        displays.drain()
        self.assertEqual([i.inverted for i in rig.drawn[-1][1].items].index(True), 3)

    def test_the_retry_draws_what_was_posted_since(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_menu(0, 1, 2)
        displays.drain()
        rig.fail_draw = False
        displays.show_menu(0, 1, 4)
        displays.drain()
        scheduled[0][1]()
        displays.drain()
        self.assertEqual([i.inverted for i in rig.drawn[-1][1].items].index(True), 5)

    def test_a_good_draw_schedules_nothing(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        displays.show_menu(0, 1, 2)
        displays.drain()
        self.assertEqual([], scheduled)


class Waves(unittest.TestCase):
    """The waveform (spec desk-stem-grid): meters are noted on the OSC
    thread, a step on the displays' own clock moves every wave and posts
    every panel; what a turn posts is drawn with the latest wave."""

    def setUp(self):
        self.now = 0.0
        self.rig = Rig()
        self.displays = self.rig.displays(clock=lambda: self.now)
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def last_on(self, label):
        device = next(d for name, d in self.rig.built if name == label)
        return [picture for d, picture in self.rig.drawn if d is device][-1]

    def newest(self, label):
        """The newest column's height as the panel would be drawn now --
        a silent wave is not redrawn, so the last drawing may be older."""
        from display_panel import PANELS
        panel = next(p for p in PANELS if p.label == label)
        x, top, bottom = self.displays._picture_for(panel)(128, 64).wave[-1]
        return bottom - top

    def step(self):
        self.displays.step_waves()
        self.displays.drain()

    def loud_everywhere(self):
        """A meter on every panel's source: four analog inputs, and stem 1
        on the return."""
        self.displays.show_return(1, (True,) + (False,) * 7)
        self.displays.drain()
        self.rig.drawn.clear()
        for index in range(4):
            self.displays.note_analog(index, 1.0)
        self.displays.note_peak(1, 1.0)

    def test_a_step_redraws_every_display_whose_wave_moved(self):
        self.loud_everywhere()
        self.step()
        self.assertEqual(5, len(self.rig.drawn))

    def test_a_silent_wave_is_not_redrawn(self):
        """Final review: in silence every step repainted all five for
        nothing; an unchanged wave posts nothing."""
        self.step()
        self.assertEqual([], self.rig.drawn)

    def test_the_wave_holds_the_peak_between_steps(self):
        """Final review: StemDeck sends a 40 ms peak 25 times a second; a
        step every 200 ms must show the loudest of them, not the last."""
        self.displays.note_peak(1, 1.0)
        self.displays.note_peak(1, 0.001)
        self.displays.show_channel(0, stem(1))
        self.step()
        self.assertGreater(self.newest("Deck 1"), 20)
        self.displays.note_peak(1, 0.001)
        self.step()
        self.assertLess(self.newest("Deck 1"), 4)

    def test_a_turn_during_a_wave_step_goes_first(self):
        """A step redraws every moving wave (~150 ms on the desk); a turn
        arriving meanwhile is drawn next, not after the batch."""
        self.loud_everywhere()
        order = []
        labels = {id(device): name for name, device in self.rig.built}
        draw = self.rig.draw

        def draw_and_turn(device, picture):
            draw(device, picture)
            order.append(labels[id(device)])
            if len(order) == 1:
                self.displays.show_menu(3, 1, 4)   # Deck 4, last of the decks

        self.displays._draw_fields = draw_and_turn
        self.step()
        self.assertEqual(order, ["Deck 1", "Deck 4", "Deck 2", "Deck 3", "Aux Return"])
        self.assertTrue(self.last_on("Deck 4").items[5].inverted)

    def test_noting_a_peak_draws_nothing(self):
        self.displays.note_peak(1, 1.0)
        self.displays.note_analog(0, 1.0)
        self.assertEqual([], self.rig.drawn)

    def test_a_channel_follows_the_stem_it_plays(self):
        self.displays.show_channel(0, stem(3))
        self.displays.note_peak(3, 1.0)
        self.displays.note_peak(4, 0.0)
        self.displays.note_analog(0, 0.0)
        self.step()
        self.assertGreater(self.newest("Deck 1"), 20)

    def test_an_analog_channel_follows_its_own_meter(self):
        self.displays.note_peak(1, 1.0)
        self.displays.note_analog(1, 1.0)
        self.step()
        self.assertGreater(self.newest("Deck 2"), 20)
        self.assertLess(self.newest("Deck 1"), 2)

    def return_bars(self):
        from display_panel import return_panel
        return self.displays._picture_for(return_panel())(128, 64).bars

    def test_the_return_meters_every_stem_and_its_analog_input(self):
        """Spec desk-stem-grid-2: no wave on the return; nine meters."""
        self.displays.note_peak(2, 1.0)
        self.displays.note_aux(0, 1.0)
        self.step()
        bars = self.return_bars()
        self.assertIsNone(bars[0])
        self.assertIsNotNone(bars[1])
        self.assertIsNotNone(bars[8])
        self.assertIsNone(bars[9])

    def test_a_stale_aux_meter_is_an_empty_bar(self):
        self.displays.note_aux(1, 1.0)
        self.now = 5.0
        self.step()
        self.assertIsNone(self.return_bars()[9])

    def test_meters_that_did_not_move_do_not_redraw_the_return(self):
        self.step()
        self.assertNotIn("Aux Return", [n for n, d in self.rig.built
                                        for dd, _ in self.rig.drawn if dd is d])

    def test_without_meters_every_wave_is_flat(self):
        for _ in range(3):
            self.step()
        self.assertTrue(all(bottom - top <= 1 for _, picture in self.rig.drawn
                            for _, top, bottom in picture.wave))

    def test_a_meter_that_stopped_is_silence(self):
        self.displays.note_analog(0, 1.0)
        self.now = 5.0
        self.step()
        self.assertLess(self.newest("Deck 1"), 2)

    def test_the_clock_steps_at_the_rate(self):
        from display_panel import WAVE_STEPS_PER_SECOND
        self.loud_everywhere()
        self.displays.tick()
        self.displays.drain()
        self.assertEqual(5, len(self.rig.drawn))
        self.rig.drawn.clear()
        self.now = 0.5 / WAVE_STEPS_PER_SECOND
        self.displays.tick()
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)
        self.now = 1.0 / WAVE_STEPS_PER_SECOND
        for index in range(4):
            self.displays.note_analog(index, 0.5)
        self.displays.note_peak(1, 0.5)
        self.displays.tick()
        self.displays.drain()
        self.assertEqual(5, len(self.rig.drawn))

    def test_a_turn_keeps_the_wave(self):
        self.displays.note_analog(0, 1.0)
        self.step()
        self.rig.drawn.clear()
        self.displays.show_menu(0, 1, 1)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertTrue(self.rig.drawn[0][1].items[2].inverted)
        self.assertGreater(self.newest("Deck 1"), 20)


class WhatPlaysWhere(unittest.TestCase):
    """A stem's place shows on every display; a selection only on its own."""

    def setUp(self):
        self.rig = Rig()
        self.displays = self.rig.displays()
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def test_a_stem_change_redraws_every_display(self):
        self.displays.show_channel(0, stem(3))
        self.displays.drain()
        self.assertEqual(5, len(self.rig.drawn))

    def test_a_selection_redraws_its_own_display(self):
        self.displays.show_menu(1, 1, 3)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertTrue(self.rig.drawn[0][1].items[4].inverted)

    def test_there_is_no_cue_on_the_display_any_more(self):
        self.assertFalse(hasattr(self.displays, "show_cue"))


class Painting(unittest.TestCase):
    """The painter on a real 128x64 1-bit image (rule: a page test must
    paint). A3_SNAPSHOTS=<dir> saves each state as a PNG."""

    def paint_state(self, name, picture):
        from PIL import Image
        image = Image.new("1", (128, 64))
        paint(image, picture)
        folder = __import__("os").environ.get("A3_SNAPSHOTS")
        if folder:
            image.resize((512, 256)).save(Path(folder) / f"desk-stem-grid-{name}.png")
        return image

    def channel(self, index, menu, places, level):
        from display_panel import Wave, menu_items, wave_box
        wave = Wave(128)
        for step in range(20):
            wave.step(level * (step % 5) / 4)
        return Picture(menu_items(index, menu, places, 128, 64), wave.columns(wave_box(128, 64)))

    def the_return(self, mode, cursor, stems, aux):
        from display_panel import return_bars, return_items
        return Picture(return_items(mode, cursor, 128, 64), [], None,
                       return_bars(stems, aux, 128, 64))

    def lit(self, image, box):
        return any(image.getpixel((x, y)) for x in range(box[0], box[2] + 1)
                   for y in range(box[1], box[3] + 1))

    def test_each_state_paints(self):
        places = [1, None, 3, None, 0, None, None, None]   # pair 5 (D2 stem 1) on channel 1
        states = {
            "channel-top": self.channel(0, (0, 0), places, 1.0),
            "channel-deck": self.channel(0, (2, 1), places, 0.7),
            "channel-deck-crossed": self.channel(1, (1, 2), places, 0.4),
            "return-stem": self.the_return(1, 1, [0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 0.0, 0.6], (0.7, 0.5)),
            "return-analog": self.the_return(0, 1, [0.0] * 8, (0.8, 0.8)),
        }
        for name, picture in states.items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                self.assertTrue(self.lit(image, (0, 0, 127, 31)), "the menu painted")
                for item in picture.items:
                    x0, y0, x1, y1 = item.box
                    if item.inverted:
                        self.assertEqual(image.getpixel((x0, y0)), 255)
                        self.assertEqual(image.getpixel((x1, y1)), 255)
                    else:
                        self.assertTrue(self.lit(image, item.box), item.text)
                for x, top, bottom in picture.wave:
                    self.assertTrue(image.getpixel((x, top)) and image.getpixel((x, bottom)))
                for bar in picture.bars or []:
                    if bar:
                        self.assertEqual(image.getpixel((bar[0], bar[3])), 255)

    def test_nothing_spills_out_of_its_box(self):
        """Seen in the snapshots: ANALOG ran past the panel's edge, and the
        back arrow was a box the font did not have."""
        for name, picture in {
                "deck": self.channel(0, (1, 4), [3] + [None] * 7, 0.0),
                "return": self.the_return(0, 1, [0.0] * 8, (0.0, 0.0))}.items():
            with self.subTest(name):
                image = self.paint_state(f"fit-{name}", picture)
                inside = set()
                for item in picture.items:
                    x0, y0, x1, y1 = item.box
                    bottom = y1 + 2 if item.marked else y1      # the mark sits under its box
                    inside |= {(x, y) for x in range(x0, x1 + 1) for y in range(y0, bottom + 1)}
                spilled = [(x, y) for x in range(128) for y in range(32)
                           if image.getpixel((x, y)) and (x, y) not in inside]
                self.assertEqual(spilled, [])
                for item in picture.items:
                    if item.inverted or item.crossed:
                        continue
                    x0, y0, x1, y1 = item.box
                    edges = [(x, y) for x in (x0, x1) for y in range(y0, y1)
                             if image.getpixel((x, y))]
                    self.assertEqual(edges, [], item.text)

    def test_back_is_a_glyph_the_font_has(self):
        from display_panel import BACK_ENTRY
        from PIL import Image, ImageDraw
        from a3_mixer_displays import _font
        image = Image.new("1", (40, 20))
        ImageDraw.Draw(image).text((2, 2), BACK_ENTRY, fill="white", font=_font(14))
        tofu = Image.new("1", (40, 20))
        ImageDraw.Draw(tofu).text((2, 2), "\uffff", fill="white", font=_font(14))
        self.assertNotEqual(list(image.getdata()), list(tofu.getdata()))

    def test_the_mark_shows_under_the_cursor_too(self):
        """Final review: after a push the cursor stands on what plays, and a
        black underline inside the white box read as 'nothing loaded'."""
        picture = self.channel(0, (0, 0), [0] + [None] * 7, 0.0)   # D1 plays, cursor on D1
        image = self.paint_state("marked-under-cursor", picture)
        x0, y0, x1, y1 = picture.items[0].box
        self.assertTrue(picture.items[0].inverted and picture.items[0].marked)
        self.assertTrue(self.lit(image, (x0, y1 + 1, x1, min(31, y1 + 3))))

    def test_marked_is_underlined(self):
        picture = self.channel(0, (0, 2), [None] * 8, 0.0)   # A plays, cursor on A
        unmarked = self.channel(0, (0, 2), [0] + [None] * 7, 0.0)
        image, other = self.paint_state("marked", picture), self.paint_state("unmarked", unmarked)
        x0, y0, x1, y1 = picture.items[0].box                 # D1: marked in `unmarked` only
        self.assertFalse(self.lit(image, (x0, y1 + 1, x1, min(31, y1 + 3))))
        self.assertTrue(self.lit(other, (x0, y1 + 1, x1, min(31, y1 + 3))))

    def test_a_crossed_stem_carries_a_line_and_its_channel(self):
        picture = self.channel(0, (1, 4), [3] + [None] * 7, 0.0)   # stem 1 plays on channel 4
        image = self.paint_state("crossed", picture)
        crossed, plain = picture.items[1], picture.items[2]
        self.assertTrue(crossed.crossed and not plain.crossed)
        corner = lambda b: (b[0], b[3] - 2, b[0] + 2, b[3])
        self.assertTrue(self.lit(image, corner(crossed.box)))
        self.assertFalse(self.lit(image, corner(plain.box)))

    def test_the_upper_half_is_painted_once_per_state(self):
        from a3_mixer_displays import upper_half
        items = self.channel(0, (0, 1), [None] * 8, 0.0).items
        self.assertIs(upper_half(tuple(items), 128, 64), upper_half(tuple(items), 128, 64))

    def test_a_strip_paints_what_its_columns_paint(self):
        """The fast path (desk-stem-grid-2): the wave's picture is pasted,
        and looks exactly like the 128 lines it replaces."""
        from PIL import Image
        from display_panel import WaveStrip, wave_box
        strip = WaveStrip(128, 32)
        for level in (0.2, 0.9, 0.0, 0.6, 1.0):
            strip.shift(level)
        columns = strip.columns(wave_box(128, 64))
        pasted, drawn = Image.new("1", (128, 64)), Image.new("1", (128, 64))
        paint(pasted, Picture([], columns, strip.image))
        paint(drawn, Picture([], columns))
        self.assertEqual(list(pasted.getdata()), list(drawn.getdata()))


class HowLongADrawTakes(unittest.TestCase):
    """One journal line per batch of draws, so the bus speed is measured on
    the desk instead of guessed."""

    def test_the_desk_reports_seldom(self):
        """Final review: with waves the displays draw all the time; a line
        every 20 draws was one every 0.8 s in the journal."""
        rig = Rig()
        displays = rig.displays()
        for pair in range(100):
            displays.show_menu(0, 1, pair % 5)
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
        displays.show_menu(0, 1, 0)
        displays.drain()
        displays.show_menu(1, 1, 0)
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
