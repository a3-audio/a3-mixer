#!/usr/bin/python

# SPDX-FileCopyrightText: 2024 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

# -*- coding: utf-8 -*-

"""Beschriftet die fünf OLED-Displays des Pults, einmal beim Start.

Welche Displays es gibt, steht in display_panel.PANELS; hier steht nur, wie man
eines wirklich anspricht. Der Schnitt ist der Grund, warum an der Tabelle etwas
zu prüfen ist: dieses Modul lässt sich ohne die Pi-Hardware nicht importieren,
jenes schon.

Vorher waren es sechs fast gleiche Funktionen für fünf Displays. Der Dienst war
vom 2026-09-10 bis zum 2026-09-18 tot, weil die sechste ein Display ansprach,
das es nicht gibt -- auf Multiplexer-Kanal 7, mit `i2c(port=0, ...)` (den Bus 0
hat das Pult gar nicht) und einem Zeichnen auf `device_dev_5` aus der
Nachbarfunktion. Ein einziges stummes Display hat damit die anderen vier mit
dunkel gelassen, und `systemctl` sagte nur "failed".
"""

import sys

import TCA9548A
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont

from display_panel import PANELS, draw_panels

oled_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)


def show(panel):
    """Schaltet den Multiplexer auf das Display und schreibt sein Wort hin."""
    TCA9548A.I2C_setup(0x70, panel.channel)

    serial = i2c(port=panel.port, address=panel.address)
    device = ssd1306(serial, rotate=panel.rotate)

    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white", fill="black")
        draw.text((15, 5), panel.label, font=oled_font, fill="white")


def report(message):
    print(message, file=sys.stderr)


if __name__ == '__main__':
    failed = draw_panels(PANELS, show, report)

    # Ein stummes Display ist eine Meldung, kein Grund zu sterben -- genau das
    # hat den Dienst acht Tage lang unten gehalten. Sind aber *alle* stumm, ist
    # nicht ein Display kaputt, sondern der Bus oder der Multiplexer, und dann
    # soll systemd es auch sagen.
    if len(failed) == len(PANELS):
        report("no display answered at all -- check the i2c bus and the TCA9548A")
        sys.exit(1)

    sys.exit(0)
