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

    def send_all(self, send, report):
        """`send(address, value)` for every position. With none known, say so
        once -- the script restarted while the panel kept running, and the
        panel will not repeat what it sent."""
        with self._lock:
            known = list(self._values.items())
            first_empty = not known and not self._said_empty
            if first_empty:
                self._said_empty = True
        if first_empty:
            report("a3-mixer: no positions known yet -- move a control or "
                   "restart the panel")
        for address, value in known:
            send(address, value)
