# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The calibration on the five displays, painted on a real 128x64 1-bit
image (rule: a page test must paint). A3_SNAPSHOTS=<dir> saves each state
as a PNG."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_calibration import Calibration  # noqa: E402
from a3_mixer_calibration_display import (CalibrationPicture,  # noqa: E402
                                          calibration_picture)
from a3_mixer_calibration_run import (CONTROLS, CalibrationRun,  # noqa: E402
                                      DeskCalibration)
from a3_mixer_displays import Displays, paint  # noqa: E402
from display_panel import PANELS, Picture  # noqa: E402


def run_at(control_id, end_index=0, readings=None):
    """A run asking for `control_id`'s `end_index`-th step."""
    run = CalibrationRun(Calibration(), readings or {c.id: 512 for c in CONTROLS})
    while run.step.control.id != control_id:
        run.take()
    for _ in range(end_index):
        run.take()
    return run


def ended(cancel):
    run = run_at("0:1")
    if cancel:
        run.cancel()
    else:
        while run.step is not None:
            run.take()
    return run.view()


def lit(image, box):
    x0, y0, x1, y1 = box
    return sum(1 for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
               if image.getpixel((x, y)))


def area(box):
    x0, y0, x1, y1 = box
    return (x1 - x0 + 1) * (y1 - y0 + 1)


class Painting(unittest.TestCase):
    def paint_state(self, name, view, panel):
        from PIL import Image
        picture = calibration_picture(view, panel, 128, 64)
        image = Image.new("1", (128, 64))
        paint(image, picture)
        folder = os.environ.get("A3_SNAPSHOTS")
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)
            image.resize((512, 256)).save(Path(folder) / f"calibration-{name}.png")
        return picture, image

    def test_every_state_paints(self):
        states = {
            "ch1-volume-up-asking": (run_at("0:5").view(), 0),
            "ch1-volume-down-asking": (run_at("0:5", 1).view(), 0),
            "ch1-eq-high-centre-asking": (run_at("0:2", 2).view(), 0),
            "ch2-waiting-while-ch1-asks": (run_at("0:5").view(), 1),
            "fx-return-waiting-while-ch1-asks": (run_at("0:5").view(), 4),
            "master-booth-asking-on-fx-return": (run_at("master:3").view(), 4),
            "ch1-done-while-master-asks": (run_at("master:3").view(), 0),
            "done": (ended(cancel=False), 0),
            "cancelled": (ended(cancel=True), 2),
        }
        for name, (view, panel) in states.items():
            picture, image = self.paint_state(name, view, panel)
            self.assertIsInstance(picture, CalibrationPicture, name)
            self.assertGreater(lit(image, (0, 0, 127, 63)), 0, name)

    def test_the_asking_panel_names_the_control(self):
        picture, _ = self.paint_state("x", run_at("0:5").view(), 0)
        self.assertEqual(picture.texts[0].text, "CH1 VOLUME")
        self.assertIn("UP", [t.text for t in picture.texts])

    def test_the_others_say_where_to_look(self):
        picture, _ = self.paint_state("x", run_at("0:5").view(), 2)
        self.assertIn("SEE CH1", [t.text for t in picture.texts])
        picture, _ = self.paint_state("x", run_at("master:0").view(), 0)
        self.assertIn("SEE FX RETURN", [t.text for t in picture.texts])

    def test_up_points_up_and_down_points_down(self):
        _, up = self.paint_state("x", run_at("0:5").view(), 0)
        picture, down = self.paint_state("x", run_at("0:5", 1).view(), 0)
        x0, y0, x1, y1 = picture.arrow.box
        top_row, bottom_row = (x0, y0 + 1, x1, y0 + 1), (x0, y1 - 1, x1, y1 - 1)
        self.assertLess(lit(up, top_row), lit(up, bottom_row))
        self.assertGreater(lit(down, top_row), lit(down, bottom_row))

    def test_the_reading_bar_follows_the_control(self):
        readings = {c.id: 0 for c in CONTROLS}
        low = run_at("0:5", readings=readings)
        picture, image_low = self.paint_state("x", low.view(), 0)
        low.feed("0:5", 1023)
        _, image_high = self.paint_state("ch1-volume-up-at-the-top", low.view(), 0)
        box = picture.reading[0]
        self.assertLess(lit(image_low, box), lit(image_high, box))
        self.assertEqual(lit(image_high, box), area(box))

    def test_a_done_control_is_a_filled_field(self):
        picture, image = self.paint_state("x", run_at("master:3").view(), 0)
        for field in picture.fields:
            self.assertEqual(field.mark, "done")
            self.assertGreater(lit(image, field.box), area(field.box) // 2)

    def test_a_waiting_control_is_letters_only(self):
        picture, image = self.paint_state("x", run_at("0:1").view(), 1)
        for field in picture.fields:
            self.assertEqual(field.mark, "todo")
            self.assertLess(lit(image, field.box), area(field.box) // 2)

    def test_the_asked_control_is_outlined(self):
        picture, image = self.paint_state("x", run_at("0:2").view(), 0)
        current = next(f for f in picture.fields if f.mark == "current")
        x0, y0, x1, _ = current.box
        self.assertEqual(lit(image, (x0, y0, x1, y0)), x1 - x0 + 1)


class Rig:
    def __init__(self):
        self.later = []
        self.drawn = []

    def device(self, panel):
        return type("Device", (), {"persist": False, "width": 128, "height": 64})()

    def displays(self):
        return Displays(lambda *a: None, self.device,
                        lambda device, picture: self.drawn.append(picture),
                        lambda line: None,
                        later=lambda seconds, then: self.later.append(then))


class OnTheDisplays(unittest.TestCase):
    def test_a_running_calibration_takes_every_panel(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_calibration(run_at("0:5").view())
        displays.drain()
        self.assertEqual(len(rig.drawn), len(PANELS))
        self.assertTrue(all(isinstance(p, CalibrationPicture) for p in rig.drawn))

    def test_after_the_end_the_desk_comes_back(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_calibration(ended(cancel=False))
        displays.drain()
        self.assertEqual(len(rig.later), 1)
        rig.drawn.clear()
        rig.later[0]()
        displays.drain()
        self.assertEqual(len(rig.drawn), len(PANELS))
        self.assertTrue(all(isinstance(p, Picture) for p in rig.drawn))

    def test_a_new_calibration_is_not_ended_by_the_last_ones_timer(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_calibration(ended(cancel=True))
        displays.show_calibration(run_at("0:5").view())
        rig.later[0]()
        rig.drawn.clear()
        displays.drain()
        self.assertTrue(all(isinstance(p, CalibrationPicture) for p in rig.drawn))

    def test_meters_do_not_redraw_a_calibration(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_calibration(run_at("0:5").view())
        displays.drain()
        rig.drawn.clear()
        displays.note_peak(1, 0.9)
        displays.step_meters()
        displays.drain()
        self.assertEqual(rig.drawn, [])

    def test_the_desk_and_the_displays_speak_the_same_view(self):
        rig = Rig()
        displays = rig.displays()
        desk = DeskCalibration(Calibration(), lambda c: None, displays.show_calibration,
                               lambda values: None, lambda line: None)
        desk.start()
        displays.drain()
        self.assertEqual(rig.drawn[0].texts[0].text, "CH1 GAIN")


if __name__ == "__main__":
    unittest.main()
