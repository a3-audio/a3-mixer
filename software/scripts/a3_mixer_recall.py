# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wann das Pult nachfragt, was gerade gilt.

Die Lampen des Pults kommen von A3 Core, und Core schickt sie, wenn sich etwas
ändert. Nach einem Start hat sich nichts geändert: die LEDs bleiben dunkel,
obwohl der Filter eines Kanals an sein kann. Gemeldet am 2026-09-18:
*„wenn schon fx an ist sollte auch die zugehörige led an sein."*

Core hat dafür `/state/recall` -- eine Frage, auf die es mit allen Lampen,
Flags und gemerkten Werten antwortet, an alle Abonnenten. Das Pult hat sie nie
gestellt.

Einmal fragen genügt nicht: Core ist die Maschine, an der das Pult hängt, und
die kann später hochkommen. Ewig fragen ist auch nichts: das wäre eine
Nachricht alle paar Sekunden für den ganzen Abend. Also fragen, bis eine
Antwort kommt, und nach `give_up_after` aufhören -- dann läuft die Anlage ohne
Core, und die Lampen sind das kleinste Problem.

Nichts hier sendet oder schläft: das Modul sagt nur, ob es Zeit ist. So ist es
prüfbar, ohne dass die Pi-Hardware (board, neopixel) vorhanden sein muss.
"""


class RecallRequest:
    """Die Frage nach dem Gesamtzustand, mit Geduld und einem Ende."""

    #: Cores eigene Adresse dafür; siehe a3_core_recall.
    ADDRESS = "/state/recall"

    DEFAULT_EVERY = 5.0
    DEFAULT_GIVE_UP_AFTER = 120.0

    def __init__(self, every=DEFAULT_EVERY,
                 give_up_after=DEFAULT_GIVE_UP_AFTER, now=0.0):
        self._every = every
        self._give_up_after = give_up_after
        self._started = now
        self._last_asked = None
        self._answered = False

    def answered(self):
        """Irgendetwas ist von Core gekommen: die Frage ist beantwortet."""
        self._answered = True

    def asked(self, now):
        """Gerade gefragt."""
        self._last_asked = now

    def due(self, now):
        """Ob jetzt (wieder) gefragt werden soll."""
        if self._answered:
            return False
        if now - self._started > self._give_up_after:
            return False
        if self._last_asked is None:
            return True
        return (now - self._last_asked) >= self._every
