# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Calibrating the desk, from the desk: every pot and fader to both ends,
one at a time, shown on the displays (a3_mixer_calibration_display).

Started by holding both filter keys (HP and LP) together for three seconds
and letting go, or by `a3-mixer.py --calibrate`. Then, for every control in
turn, the display of its strip -- the FX Return's for the master section --
names it and the end to go to:

- move it there and **push any encoder** to take it;
- **turn any encoder** right to skip the step (the stored end stays; on a
  centre step: no detent), left to go one step back;
- **press either filter key** to cancel: the stored calibration stays.

Each control is asked for UP, then DOWN, then -- the EQ only -- its CENTRE
detent, so every control ends where it is safe to send: a fader down, an EQ
at 0 dB. After the last step the calibration is saved and applied.

While it runs, the desk sends Core nothing from its controls -- not a pot,
not a key -- so no half-calibrated value reaches the engine. When it ends,
done or cancelled, every control's current value goes out once, the way the
desk says everything when Core appears.

Hardware-free: the serial reader feeds it and hands it the sending, saving
and showing; the tests do the same with fakes.
"""

import time
from collections import namedtuple

from a3_mixer_calibration import FULL_SCALE, Calibration, Range
from a3_mixer_osc import CHANNEL_POTS, MASTER_POTS

UP, DOWN, CENTRE_END = "up", "down", "centre"
RUNNING, DONE, CANCELLED = "running", "done", "cancelled"

#: How long both filter keys have to be held to start a calibration: longer
#: than any hand holds both by accident.
START_HOLD_SECONDS = 3.0

#: The filter keys' indices on the panel's "fx" track (HP, LP).
FX_KEYS = ("0", "1")

#: A strip's controls, top to bottom: (truth key, title, short label).
STRIP = (
    ("channel.gain", "GAIN", "GAIN"),
    ("channel.eq.high", "EQ HIGH", "HIGH"),
    ("channel.eq.mid", "EQ MID", "MID"),
    ("channel.eq.low", "EQ LOW", "LOW"),
    ("channel.aux-send", "AUX SEND", "AUX"),
    ("channel.volume", "VOLUME", "VOL"),
)

#: The master section's controls, in the panel's order.
MASTER = (
    ("master.volume", "MASTER", "MAIN"),
    ("filter.resonance", "FILTER RES", "RES"),
    ("filter.frequency", "FILTER FREQ", "FREQ"),
    ("master.booth", "BOOTH", "BTH"),
    ("master.phones-mix", "CUE MIX", "MIX"),
    ("master.phones-volume", "PHONES", "PHN"),
    ("master.aux-return", "RETURN", "RTN"),
)

#: The controls with a centre step: the EQ, where 0 dB is meant to sit at
#: the detent. Whether the desk's EQ pots have one is not recorded; a pot
#: without simply skips the step.
CENTRED = ("channel.eq.high", "channel.eq.mid", "channel.eq.low")

#: The display that asks for the master section's controls: the FX Return's,
#: after the four channels'.
MASTER_PANEL = 4

Control = namedtuple("Control", "id panel title short centre")
Step = namedtuple("Step", "control end")

#: What the displays draw: `state`, the asking `panel` (None once ended),
#: the control's `title`, the `end` to go to, step `number` of `total`, the
#: control's raw `reading` (0..1, None if unknown) and, per panel, its
#: controls' (short label, "done" | "current" | "todo").
CalibrationView = namedtuple("CalibrationView",
                             "state panel title end number total reading marks")


def _index_of(table, key):
    return next(index for index, name in table.items() if name == key)


def _controls():
    controls = []
    for channel in range(4):
        for key, title, short in STRIP:
            controls.append(Control(f"{channel}:{_index_of(CHANNEL_POTS, key)}", channel,
                                    f"CH{channel + 1} {title}", short, key in CENTRED))
    for key, title, short in MASTER:
        controls.append(Control(f"master:{_index_of(MASTER_POTS, key)}", MASTER_PANEL,
                                title, short, False))
    return tuple(controls)


#: Every pot and fader of the desk, in the order they are asked for.
CONTROLS = _controls()


def address_of(osc, control):
    """Where control `control` ("<track>:<index>") sends its value, or None
    for a pot nothing is mapped to."""
    track, _, index = control.partition(":")
    if track == "master":
        key = MASTER_POTS.get(index)
        return osc.address(key) if key else None
    key = CHANNEL_POTS.get(index)
    if key is None or track not in ("0", "1", "2", "3"):
        return None
    return osc.channel_address(key, int(track))


def steps_of(controls):
    steps = []
    for control in controls:
        steps += [Step(control, UP), Step(control, DOWN)]
        if control.centre:
            steps.append(Step(control, CENTRE_END))
    return steps


class CalibrationRun:
    """One pass over every control. `readings` is every control's latest
    count, kept up to date through feed(): a control already at its end is
    taken as it stands."""

    def __init__(self, before, readings, controls=CONTROLS):
        self._before = before
        self._readings = dict(readings)
        self._controls = controls
        self._steps = steps_of(controls)
        self._at = 0
        self._taken = {}
        self.state = RUNNING
        self._begin_step()

    @property
    def step(self):
        return self._steps[self._at] if self.state == RUNNING else None

    def number(self):
        return self._at + 1

    def feed(self, control, counts):
        """A reading, of any control. The asked one's counts toward its end:
        the most for UP, the least for DOWN -- the hand lets go and the
        reading falls back -- and where it rests for CENTRE."""
        self._readings[control] = counts
        step = self.step
        if step is None or step.control.id != control:
            return
        if self._extreme is None or step.end == CENTRE_END:
            self._extreme = counts
        elif step.end == UP:
            self._extreme = max(self._extreme, counts)
        else:
            self._extreme = min(self._extreme, counts)

    def take(self):
        """Takes the asked end; False, and nothing taken, without a reading."""
        if self.step is None or self._extreme is None:
            return False
        self._taken[self._key()] = self._extreme
        self._advance()
        return True

    def skip(self):
        if self.step is None:
            return
        self._taken.pop(self._key(), None)
        self._advance()

    def back(self):
        if self.step is None or self._at == 0:
            return
        self._at -= 1
        self._begin_step()

    def cancel(self):
        self.state = CANCELLED

    def result(self):
        """(the new Calibration, the ids refused). A control's new Range is
        what was taken, a skipped end the stored one; a span too narrow is
        refused and the stored Range kept; a centre outside its span is
        dropped."""
        ranges, refused = self._before.ranges(), []
        for control in self._controls:
            stored = self._before.range_of(control.id)
            low = self._taken.get((control.id, DOWN), stored.low)
            high = self._taken.get((control.id, UP), stored.high)
            centre = self._taken.get((control.id, CENTRE_END)) if control.centre else None
            span = Range(low, high, centre)
            if not span.usable():
                if (control.id, DOWN) in self._taken or (control.id, UP) in self._taken:
                    refused.append(control.id)
                continue
            if span.zones()[2] is None:
                span = Range(low, high)
            ranges[control.id] = span
        return Calibration(ranges), refused

    def view(self):
        step = self.step
        if step is None:
            return CalibrationView(self.state, None, "", None, self.number(),
                                   len(self._steps), None, self._marks())
        reading = self._readings.get(step.control.id)
        return CalibrationView(self.state, step.control.panel, step.control.title,
                               step.end, self.number(), len(self._steps),
                               None if reading is None else reading / FULL_SCALE, self._marks())

    def _marks(self):
        current = self.step.control.id if self.step else None
        passed = {s.control.id for s in self._steps[:self._at]}
        pending = {s.control.id for s in self._steps[self._at:]}
        panels = {}
        for control in self._controls:
            if control.id == current:
                mark = "current"
            elif control.id in passed and control.id not in pending:
                mark = "done"
            else:
                mark = "todo"
            panels.setdefault(control.panel, []).append((control.short, mark))
        return tuple(tuple(panels.get(panel, ())) for panel in range(MASTER_PANEL + 1))

    def _key(self):
        return (self.step.control.id, self.step.end)

    def _advance(self):
        self._at += 1
        if self._at == len(self._steps):
            self.state = DONE
            return
        self._begin_step()

    def _begin_step(self):
        self._extreme = self._readings.get(self._steps[self._at].control.id)


class DeskCalibration:
    """The desk's side of it: the calibration in use, the start chord, and
    the gate. `save(calibration)` writes it, `show(view)` puts a
    CalibrationView on the displays, `resend({control id: value})` sends
    every current value once, `report(line)` logs."""

    def __init__(self, calibration, save, show, resend, report,
                 clock=time.monotonic, controls=CONTROLS):
        self.calibration = calibration
        self._save = save
        self._show = show
        self._resend = resend
        self._report = report
        self._clock = clock
        self._controls = controls
        self._readings = {}
        self._run = None
        self._fx_held = set()
        self._chord_since = None

    @property
    def active(self):
        return self._run is not None

    @property
    def step(self):
        return self._run.step if self._run else None

    def pot(self, control, counts):
        """The value to send for a reading -- None while calibrating, when
        nothing is sent."""
        self._readings[control] = counts
        if self._run is None:
            return self.calibration.value(control, counts)
        asked = self._run.step.control.id == control
        self._run.feed(control, counts)
        if asked:
            self._show(self._run.view())
        return None

    def fx_key(self, index, pressed):
        """A filter key; True if the calibration took it (nothing to send).
        Outside a calibration it still plays: both held for
        START_HOLD_SECONDS and let go start one."""
        if self._run is not None:
            if pressed:
                self._run.cancel()
                self._finish()
            return True
        if pressed:
            self._fx_held.add(index)
            if self._fx_held >= set(FX_KEYS):
                self._chord_since = self._clock()
            return False
        self._fx_held.discard(index)
        since, self._chord_since = self._chord_since, None
        if since is not None and self._clock() - since >= START_HOLD_SECONDS:
            self.start()
        return False

    def pushed(self):
        """An encoder push; True if the calibration took it."""
        if self._run is None:
            return False
        self._run.take()
        self._after_input()
        return True

    def turned(self, clicks):
        """An encoder turn; True if the calibration took it."""
        if self._run is None:
            return False
        if clicks == 0:
            return True
        if clicks > 0:
            self._run.skip()
        else:
            self._run.back()
        self._after_input()
        return True

    def start(self):
        self._run = CalibrationRun(self.calibration, self._readings, self._controls)
        self._report("calibration started -- nothing goes to Core until it ends")
        self._show(self._run.view())

    def _after_input(self):
        if self._run.state == RUNNING:
            self._show(self._run.view())
        else:
            self._finish()

    def _finish(self):
        run, self._run = self._run, None
        if run.state == DONE:
            self._apply(*run.result())
        else:
            self._report("calibration cancelled, the stored one stays")
        self._show(run.view())
        self._resend({control: self.calibration.value(control, counts)
                      for control, counts in self._readings.items()})

    def _apply(self, calibration, refused):
        self.calibration = calibration
        if refused:
            self._report("calibration refused for " + ", ".join(refused)
                         + " (not moved end to end), their stored range stays")
        try:
            self._save(calibration)
        except OSError as problem:
            self._report(f"calibration applied but not saved: {problem!r}")
            return
        self._report("calibration saved and applied")
