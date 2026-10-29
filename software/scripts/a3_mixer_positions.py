# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where every continuous control of the desk stands, as it was sent.

The panel's firmware sends a pot or fader only when it moves (12-count
deadband), and every pot once at its own start-up. A Core that comes up later
therefore never learns the positions the controls rest at. The desk is in
front (decided 2026-10-14): when Core appears, the desk says everything it
knows. This table is what it knows -- address to the last value sent.

Only positions belong here. Buttons, pushes and encoder turns are actions;
sending them again would press the key twice.

Nothing here sends on its own or touches serial: `send_all` is handed the
function that sends, so the rule is testable without the Pi.
"""

import threading

#: The line that asks the panel to send every pot and fader once, in its
#: normal "T:..:P:..:value" lines. It is a meter line for slot -1 on purpose:
#: the panel's firmware reads every incoming line by its first word, and an
#: older firmware that does not know this question reads a VU line to its end
#: and draws nothing for a slot outside 0..11. Any new word would leave the
#: rest of the line in that firmware's buffer and garble every line after it.
ASK_THE_PANEL = "VU:-1:0:0"

_NOTHING = object()


class Positions:
    def __init__(self):
        self._lock = threading.Lock()
        self._values = {}
        self._said_empty = False

    def note(self, address, value):
        """The desk just sent `value` to `address`."""
        with self._lock:
            self._values[address] = value
            self._said_empty = False

    def is_new(self, address, value):
        """Whether `value` differs from what `address` last sent: a
        calibrated control resting in a dead zone reads the same value
        again and again, and Core needs it once."""
        with self._lock:
            return self._values.get(address, _NOTHING) != value

    def send_all(self, send, report, ask_panel=lambda: None):
        """`send(address, value)` for every position. With none known -- the
        script restarted while the panel kept running -- `ask_panel()`, so
        the panel sends them all and each reaches Core as it arrives; and say
        so once."""
        with self._lock:
            known = list(self._values.items())
            first_empty = not known and not self._said_empty
            if first_empty:
                self._said_empty = True
        if not known:
            ask_panel()
        if first_empty:
            report("a3-mixer: no positions known yet -- asked the panel for "
                   "every one")
        for address, value in known:
            send(address, value)
