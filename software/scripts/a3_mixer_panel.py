#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Welche Taste am Kanalzug was tut, und welche Lampe dazu leuchtet.

Hardwarefrei mit Absicht: `a3-mixer.py` laesst sich ohne board, neopixel und
serial nicht einmal importieren, und dann waere an diesen Tabellen nichts zu
pruefen. Derselbe Schnitt wie bei a3_mixer_recall, a3_mixer_watchdog und
display_panel.

**Die drei Tasten eines Kanalzugs teilen sich eine RGB-Lampe**, je Taste ein
Farbkanal. Das ist der Schluessel zu allem hier: eine Taste verlegen heisst,
ihre Lampe auf eine andere Farblinie zu legen, und die Linien sind nicht gleich
gut. In die rote sind die falschen Widerstaende geloetet -- sie ist zu dunkel
zum Lesen.
"""

#: Kein Kanalparameter, sondern die Tap-Taste: sie geht an den beat-analyzer,
#: dahin, wo auch A3 Motions TAP geht, und traegt keine Kanalnummer.
TAP = "tap"

#: Die Taste am Kanalzug, nach dem Index, den die Firmware meldet.
#:
#: Umgestellt am 2026-09-19. Vorher: 0 = pfl, 1 = fx, 2 = 3d (seit dem
#: 2026-09-12 ausser Betrieb, Taste blieb am Panel).
#:
#: Warum getauscht wurde: PFL sass auf der roten Linie mit den falschen
#: Widerstaenden und war zu dunkel. Eine Cue-Lampe muss man im Dunkeln lesen
#: koennen -- sie zieht deshalb auf die freie, helle blaue Linie des toten
#: 3D-Tasters. Die rote bekommt Tap, das nur blitzt und dessen Helligkeit
#: niemand liest. Nach Funktion sortiert ist das der richtige Weg herum.
#:
#: Nach dem Tastenindex geschluesselt und nicht nach Kanal: "alle vier gleich"
#: ist damit Bauart und keine Absprache.
CHANNEL_BUTTONS = {
    "0": TAP,
    "1": "fx",
    "2": "pfl",
}

#: Welche Farbe der einen Lampe des Kanalzugs eine Funktion anzuendet.
#: 0 rot, 1 gruen, 2 blau.
#:
#: Tap steht hier nicht: es sitzt auf der roten Linie, die nichts mehr
#: anzeigt. Ob die vier Tap-Tasten im Takt mitblinken sollen wie A3 Motions
#: TAP, ist offen -- das waere Arbeit an Core und am Pult und wurde nicht
#: bestellt.
LED_COLOUR = {
    "fx": 1,
    "pfl": 2,
}


#: Die Farblinie, auf der der Tap-Takt blitzt, und wie lange.
#:
#: Rot, also die Linie des Tap-Tasters selbst -- die Lampe, die blitzt, gehoert
#: zu der Taste, die man drueckt. Sie ist auch die einzige, die frei ist: seit
#: dem Umbau vom 2026-09-19 sitzt PFL auf blau und FX auf gruen, und rot (die
#: mit den falschen Widerstaenden) zeigte nichts mehr an. Zu dunkel zum Lesen
#: ist sie immer noch -- zum Blitzen reicht sie, denn ein Blitz wird nicht
#: gelesen, sondern bemerkt.
#:
#: Die Dauer liegt unter einem Beat auch bei 200 BPM (300 ms), sonst wuerde aus
#: dem Blitz ein Dauerlicht, und ueber der Wahrnehmungsschwelle im Dunkeln.
TAP_FLASH_COLOUR = 0
TAP_FLASH_SECONDS = 0.06


def channel_button(index):
    """Was die Taste mit diesem Index tut, oder None.

    None und kein KeyError: genau ein blanker dict-Zugriff hier hat am
    2026-09-12 den seriellen Leser mitten im Betrieb sterben lassen, als der
    3D-Taster aus der Tabelle genommen wurde und am Panel blieb. Das Pult war
    danach fuer jeden Poti und jede Taste taub, und systemd meldete den Dienst
    als aktiv.
    """
    return CHANNEL_BUTTONS.get(index)


def led_colour(led_type):
    """Welche Farbe der Kanallampe diese Funktion anzuendet, oder None."""
    return LED_COLOUR.get(led_type)
