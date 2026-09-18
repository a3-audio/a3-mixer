#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Der Eltern-Prozess ist nur so gesund wie sein Kind.

`a3-mixer.py` startet den seriellen Leser als eigenen Prozess und behält den
OSC-Server bei sich. Stirbt das Kind, lebt der Eltern-Prozess weiter -- also
bleibt der Unit `active`, das Kind steht als `<defunct>` da, und das Pult
empfängt weiter (LEDs, VU) und sendet nichts mehr. Am 2026-09-12 war es
zwanzig Minuten so, und nichts hat es gesagt.

Halb lebendig ist schlimmer als tot: ein Pult, dessen Lampen leuchten und
dessen VU-Meter zappeln, sieht im Set aus wie ein Pult, das läuft. Man sucht
den Fehler dann bei Core oder am Kabel.

Hardwarefrei, damit die Regel prüfbar ist -- `a3-mixer.py` lässt sich ohne
`board` und `neopixel` nicht einmal importieren.
"""


def watch_child(is_alive, on_death, sleep, every=1.0, name="child process"):
    """Wartet, bis `is_alive()` falsch wird, und meldet es genau einmal.

    Blockiert, gehört also in einen Daemon-Thread. `on_death` bekommt einen
    Satz und ist die Stelle, an der der Aufrufer sich beendet -- hier steht
    bewusst kein `sys.exit`: was beim Tod des Kindes zu geschehen hat, ist
    eine Frage des Dienstes, nicht dieser Schleife, und ein Modul, das den
    Prozess beendet, lässt sich nicht testen.

    Gemeldet wird einmal, nicht in der Schleife: ein Watchdog, der sekündlich
    dasselbe sagt, füllt das Journal und sagt nichts Neues.

    Nebenwirkung, und keine unwichtige: `multiprocessing.Process.is_alive()`
    holt ein beendetes Kind ab. Ohne diese Abfrage bleibt es als `<defunct>`
    stehen, so wie am 2026-09-12.
    """
    while is_alive():
        sleep(every)

    on_death("the %s is gone -- this process is only half alive and stops now"
             % name)
