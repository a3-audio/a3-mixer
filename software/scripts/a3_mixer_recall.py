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

    DEFAULT_EVERY = 5.0
    DEFAULT_GIVE_UP_AFTER = 120.0

    def __init__(self, every=DEFAULT_EVERY,
                 give_up_after=DEFAULT_GIVE_UP_AFTER, now=None):
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
        """Ob jetzt (wieder) gefragt werden soll. Without a start given, the
        patience starts at the first look: the desk's clock counts from boot,
        not from the service's start."""
        if self._started is None:
            self._started = now
        if self._answered:
            return False
        if now - self._started > self._give_up_after:
            return False
        if self._last_asked is None:
            return True
        return (now - self._last_asked) >= self._every


class HelloEvery:
    """When the desk next says which truth it speaks (/device/hello).

    Every `every` seconds, for as long as the desk runs -- not only with the
    state question above, which stops once Core answers. A Core restarted
    after that forgot the hello and never heard it again (2026-10-01).
    """

    DEFAULT_EVERY = 30.0

    def __init__(self, every=DEFAULT_EVERY):
        self._every = every
        self._last = None

    def said(self, now):
        """Just said hello."""
        self._last = now

    def due(self, now):
        """Whether it is time to say it (again)."""
        return self._last is None or now - self._last >= self._every


class StateAsker:
    """One pass of the desk's asking: the hello when due, the recall when
    due. `send(kind)` sends "hello" or "recall". A send that fails -- the
    desk up before its network, 2026-10-02 -- is said once per outage and
    tried again on the next pass; it never ends the asking."""

    def __init__(self, hello, recall, send, report):
        self._hello, self._recall = hello, recall
        self._send, self._report = send, report
        self._failing = False

    def ask(self, now):
        try:
            if self._hello.due(now):
                self._send("hello")
                self._hello.said(now)
            if self._recall.due(now):
                self._send("recall")
                self._recall.asked(now)
        except OSError as error:
            if not self._failing:
                self._report("a3-mixer: cannot reach Core yet, trying again: %s" % error)
            self._failing = True
            return
        self._failing = False


class CoreArrival:
    """Whether an announcement (/core/here) means Core is new to the desk:
    the first one, or the first after `silence` seconds without any. Core
    announces every 2 s, so 5 s is two missed beats. The announcement carries
    only the truth's address and fingerprint, no instance: a Core restarted
    faster than `silence` cannot be told from the old one here."""

    DEFAULT_SILENCE = 5.0

    def __init__(self, silence=DEFAULT_SILENCE):
        self._silence = silence
        self._last = None

    def heard(self, now):
        news = self._last is None or now - self._last > self._silence
        self._last = now
        return news

    def forget(self):
        """The reaction failed: the next announcement is news again."""
        self._last = None


class DeskInFront:
    """The desk is in front: when Core turns up, hello at once, then every
    position. `send(kind)` sends "hello"; `dump()` sends the positions. A
    hello that cannot be sent is said and tried again on the next
    announcement; positions are not sent behind a hello that did not go."""

    def __init__(self, arrival, send, dump, report):
        self._arrival = arrival
        self._send, self._dump, self._report = send, dump, report

    def heard(self, now):
        if not self._arrival.heard(now):
            return
        try:
            self._send("hello")
        except OSError as error:
            self._arrival.forget()
            self._report("a3-mixer: cannot say hello to Core yet: %s" % error)
            return
        self._dump()
