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
    """The slot the cursor's arrow points at: a meter, or the channel's
    toggle after the meters -- the one under the arrow's middle."""
    slots = [m.box for m in picture.meters]
    if getattr(picture, "toggle", None) is not None:
        slots.append(picture.toggle.box)
    middle = (picture.cursor[0] + picture.cursor[2]) // 2
    return next(index for index, (x0, _, x1, _) in enumerate(slots) if x0 <= middle <= x1)


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
        displays.show_cursor(0, 1)
        displays.show_return(1, (True,) * 8)
        displays.show_cursor(0, 2)
        displays.drain()
        self.assertEqual(2, len(rig.drawn))   # each panel once, with its latest
        self.assertEqual(cursor_of(rig.drawn[0][1]), 2)

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
        displays.show_cursor(0, 0)
        displays.drain()
        _, picture = rig.drawn[0]                       # Deck 1, first in the table
        self.assertEqual([h.text for h in picture.headings], ["D1", "D2"])
        self.assertTrue(all(m.box[3] < 32 for m in picture.meters))

    def test_the_return_shows_stem_and_analog(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_return(0, (True,) * 8)
        displays.show_return_mode(1)
        displays.drain()
        _, picture = rig.drawn[-1]
        self.assertEqual([h.text for h in picture.headings], ["STEM", "ANALOG"])
        active = picture.active                         # mode 1 = STEM, the left meter
        self.assertEqual((active[0], active[2]),
                         (picture.meters[0].box[0] - 1, picture.meters[0].box[2] + 1))
        self.assertEqual(cursor_of(picture), 1)         # cursor 0 = analog, the right meter


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

    def step(self):
        """One step a tenth of a second after the last, as on the desk."""
        from display_panel import METER_STEPS_PER_SECOND
        self.now += 1.0 / METER_STEPS_PER_SECOND
        self.displays.step_meters()
        self.displays.drain()

    def fall(self, seconds):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_FLOOR_DB
        return METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB * seconds

    def clips(self, label):
        """The meters' clip states as the panel would be drawn now."""
        from display_panel import PANELS
        panel = next(p for p in PANELS if p.label == label)
        return [m.clip for m in self.displays._picture_for(panel)(128, 64).meters]

    def test_an_over_lights_the_stems_clip(self):
        self.displays.note_peak(3, 0.5)
        self.displays.note_peak(3, 2.0)                 # held: the loudest of the step
        self.displays.note_peak(3, 0.5)
        self.step()
        self.assertEqual(self.clips("Deck 1"), [False, False, True] + [False] * 5)

    def test_full_scale_lights_no_clip(self):
        self.displays.note_peak(3, 1.0)
        self.step()
        self.assertEqual(self.clips("Deck 1"), [False] * 8)

    def test_the_clip_holds_a_second_then_goes_out(self):
        self.displays.note_peak(3, 2.0)
        self.step()
        lit = []
        for _ in range(10):
            self.displays.note_peak(3, 0.5)
            self.step()
            lit.append(self.clips("Deck 1")[2])
        self.assertEqual(lit, [True] * 9 + [False])

    def test_the_clip_going_out_is_one_redraw(self):
        """The level rests at 0.5; only the clip changes, and every channel
        panel is drawn once for it."""
        self.displays.note_peak(3, 2.0)
        self.step()
        for _ in range(40):                             # long enough to rest at 0.5
            self.displays.note_peak(3, 0.5)
            self.rig.drawn.clear()
            self.step()
            if self.clips("Deck 1")[2] is False:
                break
        self.assertEqual(4, len(self.rig.drawn))
        self.rig.drawn.clear()
        self.displays.note_peak(3, 0.5)
        self.step()
        self.assertEqual([], self.rig.drawn)

    def test_an_over_on_the_analog_return_lights_analog(self):
        self.displays.note_aux(1, 1.4)
        self.step()
        self.assertEqual(self.clips("Aux Return"), [False, True])

    def test_an_over_on_the_aux_bus_lights_stem(self):
        self.displays.note_stem_aux(0, 1.4)
        self.step()
        self.assertEqual(self.clips("Aux Return"), [True, False])

    def test_without_the_bus_an_over_on_a_returned_stem_lights_stem(self):
        self.displays.show_return(1, (False, True) + (False,) * 6)
        self.displays.note_peak(1, 3.0)                 # not on the return
        self.step()
        self.assertEqual(self.clips("Aux Return"), [False, False])
        self.displays.note_peak(2, 3.0)
        self.step()
        self.assertEqual(self.clips("Aux Return"), [True, False])

    def test_a_meter_that_stopped_clips_no_more(self):
        self.displays.note_peak(3, 2.0)
        self.now = 5.0
        self.step()
        self.assertEqual(self.clips("Deck 1")[2], False)

    def test_a_channel_meters_every_stem_and_nothing_else(self):
        """The channel's analog input meter is gone (2026-10-04)."""
        self.displays.note_peak(3, 1.0)
        self.step()
        self.assertEqual(self.levels("Deck 2"), [0, 0, 1.0, 0, 0, 0, 0, 0])
        self.assertFalse(hasattr(self.displays, "note_analog"))

    def test_analog_is_the_louder_side_of_the_analog_return(self):
        self.displays.note_aux(0, 10 ** (-24 / 20))
        self.displays.note_aux(1, 10 ** (-12 / 20))
        self.step()
        _, analog = self.levels("Aux Return")
        self.assertAlmostEqual(analog, 0.75)

    def test_without_the_bus_meters_stem_is_the_loudest_stem_on_the_return(self):
        """The truth before stem_aux_L/R: STEM falls back to the loudest
        stem playing on the return."""
        self.displays.show_return(1, (False, True, False, True) + (False,) * 4)
        self.displays.note_peak(1, 1.0)                 # not on the return
        self.displays.note_peak(2, 10 ** (-24 / 20))
        self.step()
        stem, _ = self.levels("Aux Return")
        self.assertAlmostEqual(stem, 0.5)

    def test_with_the_bus_meters_stem_is_the_louder_side_of_the_aux_bus(self):
        self.displays.show_return(1, (True,) * 8)
        self.displays.note_peak(1, 1.0)                 # on the return, but the bus rules
        self.displays.note_stem_aux(0, 10 ** (-24 / 20))
        self.displays.note_stem_aux(1, 10 ** (-12 / 20))
        self.step()
        stem, _ = self.levels("Aux Return")
        self.assertAlmostEqual(stem, 0.75)

    def test_a_bus_that_was_heard_stays_the_source_in_silence(self):
        """Once the truth has the bus meters, a quiet bus is a quiet STEM --
        not the stems again."""
        self.displays.show_return(1, (True,) * 8)
        self.displays.note_stem_aux(0, 0.0)
        self.displays.note_peak(1, 1.0)
        self.step()
        self.assertEqual(self.levels("Aux Return")[0], 0.0)

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
        self.displays.note_peak(8, 1.0)
        self.now = 5.0
        self.step()
        self.assertEqual(self.levels("Deck 1")[7], 0.0)

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
        self.displays.note_peak(8, 1.0)
        self.step()
        self.rig.drawn.clear()
        self.displays.show_cursor(0, 2)
        self.displays.drain()
        _, picture = self.rig.drawn[0]
        self.assertEqual(cursor_of(picture), 2)
        self.assertEqual(picture.meters[7].level, 1.0)


class WhatPlaysWhere(unittest.TestCase):
    """What plays on a channel, and its cursor, show on its own display."""

    def setUp(self):
        self.rig = Rig()
        self.displays = self.rig.displays()
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def toggle_of(self, index):
        from display_panel import panel_for_channel
        return self.displays._picture_for(panel_for_channel(index))(128, 64).toggle

    def test_a_stem_on_the_channel_turns_its_toggle_on(self):
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertTrue(self.rig.drawn[0][1].toggle.on)
        self.assertFalse(self.toggle_of(1).on)

    def test_no_stem_turns_it_off(self):
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_channel(2, 0)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertFalse(self.rig.drawn[0][1].toggle.on)

    def active_of(self, picture):
        """The meter under the active bracket, or None."""
        if picture.active is None:
            return None
        return next(index for index, meter in enumerate(picture.meters)
                    if meter.box[0] - 1 == picture.active[0])

    def test_the_playing_stem_carries_the_bracket(self):
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.assertEqual(self.active_of(self.rig.drawn[0][1]), 2)

    def test_another_stem_moves_the_bracket(self):
        """Since 2026-10-04 the display shows which stem plays: another
        one is a redraw with the bracket over it."""
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_channel(2, stem(5))
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertEqual(self.active_of(self.rig.drawn[0][1]), 4)
        self.assertTrue(self.rig.drawn[0][1].toggle.on)

    def test_a_second_stem_above_the_playing_one_draws_nothing(self):
        """The lowest stem is the one that plays: a stem added above it
        moves no pixel and posts nothing."""
        self.displays.show_channel(2, stem(5))
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_channel(2, stem(5) | stem(6))
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)

    def test_no_stem_takes_the_bracket_away(self):
        self.displays.show_channel(2, stem(3))
        self.displays.drain()
        self.rig.drawn.clear()
        self.displays.show_channel(2, 0)
        self.displays.drain()
        self.assertIsNone(self.rig.drawn[0][1].active)

    def test_silence_again_draws_nothing(self):
        self.displays.show_channel(2, 0)
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)

    def test_a_cursor_redraws_its_own_display(self):
        self.displays.show_cursor(1, 6)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertEqual(cursor_of(self.rig.drawn[0][1]), 6)

    def test_the_cursor_starts_on_the_toggle(self):
        from display_panel import panel_for_channel
        picture = self.displays._picture_for(panel_for_channel(0))(128, 64)
        self.assertEqual(cursor_of(picture), 8)

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
            image.resize((512, 256)).save(Path(folder) / f"desk-{name}.png")
        return image

    def lit(self, image, box):
        return [(x, y) for x in range(box[0], box[2] + 1)
                for y in range(box[1], box[3] + 1) if image.getpixel((x, y))]

    def ring(self, box, inset):
        """The pixels of the rectangle `inset` pixels inside `box`."""
        x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
        return ({(x, y) for x in range(x0, x1 + 1) for y in (y0, y1)}
                | {(x, y) for y in range(y0, y1 + 1) for x in (x0, x1)})

    def all_lit(self, image, pixels):
        return all(image.getpixel(pixel) for pixel in pixels)

    def none_lit(self, image, pixels):
        return not any(image.getpixel(pixel) for pixel in pixels)

    def states(self):
        from display_panel import ANALOG_MODE, STEM_MODE, channel_picture, return_picture
        music = (0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 0.0, 0.6)
        full = (1.0,) * 8
        over = (0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 1.0, 0.6)
        held = (0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 0.62, 0.6)
        clip_5 = (False,) * 4 + (True,) + (False,) * 3
        clip_7 = (False,) * 6 + (True, False)
        return {
            "channel-music-cursor-on-a-stem-toggle-on": channel_picture(2, music, stem(6),
                                                                        128, 64),
            "channel-cursor-on-the-playing-stem": channel_picture(5, music, stem(6), 128, 64),
            "channel-cursor-on-toggle-on": channel_picture(8, music, stem(1), 128, 64),
            "channel-cursor-on-toggle-off": channel_picture(8, music, 0, 128, 64),
            "channel-silent-cursor-on-stem-1": channel_picture(0, (0.0,) * 8, 0, 128, 64),
            "channel-cursor-on-a-full-meter": channel_picture(4, music, 0, 128, 64),
            "channel-playing-stem-4-beside-the-divider": channel_picture(2, music, stem(4),
                                                                         128, 64),
            "channel-playing-stem-8-beside-the-toggle": channel_picture(2, music, stem(8),
                                                                        128, 64),
            "channel-playing-stem-1-at-the-edge": channel_picture(0, full, stem(1), 128, 64),
            "return-stem-mode-cursor-on-stem": return_picture(STEM_MODE, STEM_MODE,
                                                              (0.8, 0.3), 128, 64),
            "return-stem-mode-cursor-on-analog": return_picture(ANALOG_MODE, STEM_MODE,
                                                                (0.8, 0.3), 128, 64),
            "return-analog-mode-cursor-on-stem": return_picture(STEM_MODE, ANALOG_MODE,
                                                                (0.4, 0.9), 128, 64),
            "return-analog-mode-cursor-on-analog": return_picture(ANALOG_MODE, ANALOG_MODE,
                                                                  (0.2, 0.7), 128, 64),
            "return-silent-cursor-on-analog": return_picture(ANALOG_MODE, STEM_MODE,
                                                             (0.0, 0.0), 128, 64),
            "channel-clip-on-the-playing-stem": channel_picture(2, over, stem(5), 128, 64,
                                                                clips=clip_5),
            "channel-cursor-on-a-clipping-stem": channel_picture(6, held, stem(5), 128, 64,
                                                                 clips=clip_7),
            "return-stem-clipping-in-stem-mode": return_picture(STEM_MODE, STEM_MODE,
                                                                (1.0, 0.4), 128, 64,
                                                                clips=(True, False)),
            "return-analog-clip-held": return_picture(STEM_MODE, ANALOG_MODE,
                                                      (0.3, 0.6), 128, 64,
                                                      clips=(False, True)),
        }

    def test_each_state_paints_its_headings(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                for heading in picture.headings:
                    self.assertTrue(self.lit(image, heading.box), heading.text)

    def test_nothing_spills_out_of_its_box(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                boxes = [h.box for h in picture.headings] + [m.box for m in picture.meters]
                boxes += list(picture.dividers)
                boxes.append(picture.cursor)
                if picture.active is not None:
                    boxes.append(picture.active)
                if picture.toggle is not None:
                    boxes.append(picture.toggle.box)
                inside = {(x, y) for x0, y0, x1, y1 in boxes
                          for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
                spilled = [(x, y) for x in range(128) for y in range(64)
                           if image.getpixel((x, y)) and (x, y) not in inside]
                self.assertEqual(spilled, [])

    def test_the_dividers_are_painted_full_length(self):
        picture = self.states()["channel-silent-cursor-on-stem-1"]
        image = self.paint_state("channel-silent-cursor-on-stem-1", picture)
        for x0, y0, x1, y1 in picture.dividers:
            self.assertTrue(all(image.getpixel((x0, y)) for y in range(y0, y1 + 1)))

    def test_every_meter_is_a_plain_filled_bar_selected_or_not(self):
        """Nothing but the arrow marks the selection (maintainer,
        2026-10-04): the meter under it is drawn like every other."""
        for name in ("channel-music-cursor-on-a-stem-toggle-on",
                     "channel-cursor-on-a-full-meter"):
            with self.subTest(name):
                picture = self.states()[name]
                image = self.paint_state(name, picture)
                for meter in picture.meters:
                    x0, y0, x1, y1 = meter.box
                    bar = meter.pixels()
                    filled = [(x, y) for x in range(x0, x1 + 1)
                              for y in range(y1 - bar + 1, y1 + 1)]
                    above = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 - bar + 1)]
                    self.assertTrue(self.all_lit(image, filled), meter)
                    self.assertTrue(self.none_lit(image, above), meter)

    def test_a_selected_silent_meter_paints_nothing(self):
        for name, index in (("channel-silent-cursor-on-stem-1", 0),
                            ("return-silent-cursor-on-analog", 1)):
            with self.subTest(name):
                picture = self.states()[name]
                image = self.paint_state(name, picture)
                self.assertEqual(self.lit(image, picture.meters[index].box), [])

    def arrow_rows(self, image, box):
        """How many pixels each row of the arrow's box lights, top down."""
        x0, y0, x1, y1 = box
        return [sum(1 for x in range(x0, x1 + 1) if image.getpixel((x, y)))
                for y in range(y0, y1 + 1)]

    def test_the_arrow_is_a_solid_triangle_pointing_down(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                rows = self.arrow_rows(image, picture.cursor)
                self.assertGreater(rows[0], rows[-1])
                self.assertGreater(rows[-1], 0)
                self.assertEqual(rows, sorted(rows, reverse=True))
                # Solid: each row one run of light pixels, centred.
                x0, y0, x1, y1 = picture.cursor
                for y, count in zip(range(y0, y1 + 1), rows):
                    lit = [x for x in range(x0, x1 + 1) if image.getpixel((x, y))]
                    self.assertEqual(lit, list(range(lit[0], lit[0] + count)))
                    self.assertLessEqual(abs((lit[0] - x0) - (x1 - lit[-1])), 1)

    def test_the_arrow_spans_its_box(self):
        picture = self.states()["channel-silent-cursor-on-stem-1"]
        image = self.paint_state("channel-silent-cursor-on-stem-1", picture)
        x0, y0, x1, y1 = picture.cursor
        self.assertEqual(self.arrow_rows(image, picture.cursor)[0], x1 - x0 + 1)

    def field(self, toggle):
        from a3_mixer_displays import TOGGLE_INSET
        x0, y0, x1, y1 = toggle.box
        return (x0 + TOGGLE_INSET, y0 + TOGGLE_INSET, x1 - TOGGLE_INSET, y1 - TOGGLE_INSET)

    def field_middle(self, toggle):
        """A column of the toggle's field beside its letters: the field's
        own colour."""
        x0, y0, x1, y1 = self.field(toggle)
        return [(x0 + 1, y) for y in range(y0 + 1, y1)]

    def inside(self, toggle):
        x0, y0, x1, y1 = self.field(toggle)
        return (x0 + 1, y0 + 1, x1 - 1, y1 - 1)

    def test_the_toggle_on_is_a_filled_box_with_dark_letters(self):
        picture = self.states()["channel-music-cursor-on-a-stem-toggle-on"]
        image = self.paint_state("channel-music-cursor-on-a-stem-toggle-on", picture)
        toggle = picture.toggle
        self.assertTrue(self.none_lit(image, self.ring(toggle.box, 0)))
        self.assertTrue(self.all_lit(image, self.ring(self.field(toggle), 0)))
        self.assertTrue(self.all_lit(image, self.field_middle(toggle)))
        inside = self.inside(toggle)
        self.assertLess(len(self.lit(image, inside)),
                        (inside[2] - inside[0] + 1) * (inside[3] - inside[1] + 1))

    def test_the_toggle_off_is_an_outline_with_light_letters(self):
        picture = self.states()["channel-silent-cursor-on-stem-1"]
        image = self.paint_state("channel-silent-cursor-on-stem-1", picture)
        toggle = picture.toggle
        self.assertTrue(self.none_lit(image, self.ring(toggle.box, 0)))
        self.assertTrue(self.all_lit(image, self.ring(self.field(toggle), 0)))
        self.assertTrue(self.none_lit(image, self.field_middle(toggle)))
        self.assertTrue(self.lit(image, self.inside(toggle)))

    def test_the_toggle_looks_the_same_selected_or_not(self):
        from display_panel import channel_picture
        music = (0.2, 0.9, 0.0, 0.5, 1.0, 0.3, 0.0, 0.6)
        for on in (True, False):
            with self.subTest(on=on):
                selected = channel_picture(8, music, stem(1) if on else 0, 128, 64)
                elsewhere = channel_picture(3, music, stem(1) if on else 0, 128, 64)
                one = self.paint_state(f"toggle-{on}-selected", selected)
                two = self.paint_state(f"toggle-{on}-elsewhere", elsewhere)
                box = selected.toggle.box
                self.assertEqual(self.lit(one, box), self.lit(two, box))

    def test_every_heading_is_plain(self):
        """Light letters on dark, mostly dark: the bracket marks the
        playing mode, no heading is inverted any more."""
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                for heading in picture.headings:
                    x0, y0, x1, y1 = heading.box
                    lit = len(self.lit(image, heading.box))
                    self.assertLess(lit, (x1 - x0 + 1) * (y1 - y0 + 1) / 2, heading.text)

    def bracket_pixels(self, box):
        """The bracket's own pixels: the top row of `box` and its two
        side columns."""
        x0, y0, x1, y1 = box
        return ({(x, y0) for x in range(x0, x1 + 1)}
                | {(x, y) for x in (x0, x1) for y in range(y0, y1 + 1)})

    def with_brackets(self):
        return {name: picture for name, picture in self.states().items()
                if picture.active is not None}

    def test_the_bracket_is_a_top_line_and_two_legs(self):
        """Painted with and without it, the picture differs in exactly
        the bracket's top line and legs: lit across, lit down, its inside
        left to the meter, and nothing beyond its box."""
        self.assertEqual(len(self.with_brackets()), 15)
        for name, picture in self.with_brackets().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                bare = self.paint_state(name + "-bare", picture._replace(active=None))
                changed = {(x, y) for x in range(128) for y in range(64)
                           if image.getpixel((x, y)) != bare.getpixel((x, y))}
                self.assertEqual(changed, self.bracket_pixels(picture.active))

    def test_the_bracket_leaves_the_meter_whole(self):
        for name, picture in self.with_brackets().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                bare = self.paint_state(name + "-bare", picture._replace(active=None))
                for meter in picture.meters:
                    self.assertEqual(self.lit(image, meter.box), self.lit(bare, meter.box))

    def bar_pixels(self, meter):
        x0, y0, x1, y1 = meter.box
        bar = meter.pixels()
        return [(x, y) for x in range(x0, x1 + 1) for y in range(y1 - bar + 1, y1 + 1)]

    def test_a_clip_hatches_its_bar_and_nothing_else(self):
        """Clipping, a meter's bar is drawn hatched -- diagonal dark lines
        through it --, so it reads as clip at a full bar under the bracket
        and beneath the arrow alike; painted without the clip, the picture
        differs only inside that bar."""
        clipping = {name: picture for name, picture in self.states().items()
                    if any(m.clip for m in picture.meters)}
        self.assertEqual(len(clipping), 4)
        for name, picture in clipping.items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                clean = picture._replace(meters=tuple(m._replace(clip=False)
                                                      for m in picture.meters))
                bare = self.paint_state(name + "-clean", clean)
                changed = {(x, y) for x in range(128) for y in range(64)
                           if image.getpixel((x, y)) != bare.getpixel((x, y))}
                hatched = {pixel for m in picture.meters if m.clip
                           for pixel in self.bar_pixels(m)}
                self.assertTrue(changed)
                self.assertLessEqual(changed, hatched)
                for meter in picture.meters:
                    if not meter.clip:
                        continue
                    bar = self.bar_pixels(meter)
                    dark = [pixel for pixel in bar if not image.getpixel(pixel)]
                    # Mostly lit, still a bar; dark in every row and column.
                    self.assertGreater(len(dark), len(bar) / 5, meter)
                    self.assertLess(len(dark), len(bar) / 2, meter)
                    self.assertEqual({y for _, y in dark}, {y for _, y in bar})
                    self.assertEqual({x for x, _ in dark}, {x for x, _ in bar})

    def test_without_a_clip_every_bar_is_solid(self):
        for name, picture in self.states().items():
            with self.subTest(name):
                image = self.paint_state(name, picture)
                for meter in picture.meters:
                    if not meter.clip:
                        self.assertTrue(self.all_lit(image, self.bar_pixels(meter)), meter)

    def test_the_hatch_stands_still_as_the_bar_falls(self):
        """The lines are fixed to the panel: a falling bar uncovers no
        crawling pattern, the rows that stay look as they did."""
        from display_panel import channel_picture
        clip = (True,) + (False,) * 7
        high = channel_picture(8, (0.9,) + (0.0,) * 7, 0, 128, 64, clips=clip)
        low = channel_picture(8, (0.6,) + (0.0,) * 7, 0, 128, 64, clips=clip)
        one, two = self.paint_state("hatch-high", high), self.paint_state("hatch-low", low)
        for pixel in self.bar_pixels(low.meters[0]):
            self.assertEqual(one.getpixel(pixel), two.getpixel(pixel))

    def test_the_return_shows_nothing_between_its_meters(self):
        """No AUX title any more: between STEM's and ANALOG's columns the
        meters' band stays dark, but for the bracket's leg a column beside
        the active meter."""
        for name in ("return-stem-mode-cursor-on-stem", "return-analog-mode-cursor-on-analog"):
            with self.subTest(name):
                picture = self.states()[name]
                image = self.paint_state(name, picture)
                left, right = picture.meters
                between = (left.box[2] + 2, left.box[1], right.box[0] - 2, left.box[3])
                self.assertEqual(self.lit(image, between), [])


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
