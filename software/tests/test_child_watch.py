# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Der Eltern-Prozess ist nur so gesund wie sein Kind.

Gefunden am 2026-09-12 um 23:55: das Pult war für jeden Poti und jede Taste
taub, und `systemctl is-active` sagte `active`. Der serielle Leser --
`multiprocessing.Process`, das Kind -- war um 23:29:53 an einem KeyError
gestorben. Der Eltern-Prozess mit dem OSC-Server lebte weiter, also blieb der
Unit aktiv, das Kind stand als `<defunct>` da, und das Pult *empfing* weiter
(LEDs, VU) und *sendete* nichts mehr.

Das ist die unangenehmste Sorte Ausfall: halb lebendig. Die Lampen leuchten,
die VU-Meter zappeln, kein Regler tut etwas -- im Set sucht man den Fehler bei
Core oder am Kabel, nicht am Pult, das ja offensichtlich läuft.

Der KeyError selbst ist längst behoben (b21b614). Hier steht die Klasse
darunter: stirbt das Kind, muss der Eltern-Prozess mitgehen, damit systemd
etwas zu tun bekommt.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_watchdog import watch_child


class AHealthyChild(unittest.TestCase):
    def test_the_parent_keeps_waiting_while_the_child_lives(self):
        readings = [True, True, True, False]
        slept = []

        died = []
        watch_child(lambda: readings.pop(0), died.append, slept.append)

        self.assertEqual(1, len(died))
        self.assertEqual(3, len(slept), "einmal je lebendiger Runde")


class ADeadChild(unittest.TestCase):
    def test_the_death_is_noticed_on_the_first_look(self):
        died = []
        watch_child(lambda: False, died.append, lambda _: None)
        self.assertEqual(1, len(died))

    def test_the_reason_says_which_child(self):
        died = []
        watch_child(lambda: False, died.append, lambda _: None,
                    name="serial reader")
        self.assertIn("serial reader", died[0])

    # Einmal, nicht in der Schleife: ein Watchdog, der sekündlich dasselbe
    # meldet, füllt das Journal und sagt nichts Neues.
    def test_it_gives_up_rather_than_reporting_forever(self):
        died = []
        slept = []
        watch_child(lambda: False, died.append, slept.append)
        self.assertEqual(1, len(died))
        self.assertEqual(0, len(slept))


class TheInterval(unittest.TestCase):
    def test_the_wait_is_handed_to_sleep(self):
        readings = [True, False]
        slept = []
        watch_child(lambda: readings.pop(0), lambda _: None, slept.append,
                    every=2.5)
        self.assertEqual([2.5], slept)


if __name__ == "__main__":
    unittest.main()
