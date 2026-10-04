# SPDX-FileCopyrightText: 2024 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sys
import math
import time
import argparse
import serial  # pySerial https://pyserial.readthedocs.io/
import numpy as np

import board
import neopixel

import socket
import threading
from multiprocessing import Process

from pythonosc.udp_client import SimpleUDPClient
from pythonosc import osc_server
from pythonosc import dispatcher

from typing import List, Any

from a3_mixer_recall import HelloEvery, RecallRequest, StateAsker
from a3_mixer_panel import (TAP, TAP_FLASH_COLOUR, TAP_FLASH_SECONDS,
                            channel_button, led_colour)
from a3_mixer_encoders import (Clicks, PushHoldOff, encoder_message,
                                parse_int, push_message)
from a3_mixer_displays import (channel_announcement, cursor_announcement,
                               mode_announcement, open_displays, return_announcement)
from a3_mixer_watchdog import watch_child
from a3_mixer_truth import (ANNOUNCE_PORT, cache_path, follows_core, keep,
                            wait_for_truth)
from a3_mixer_osc import (CHANNEL_KEYS, CHANNEL_POTS, LAMPS, MASTER_POTS,
                          MixerOsc, TruthMissing, load as load_osc_truth)

pixel_pin = board.D12
num_pixels = 14
num_channel = 4

ORDER = neopixel.GRB

pixels = neopixel.NeoPixel(
    pixel_pin, num_pixels, brightness=1, auto_write=False, pixel_order=ORDER
)

button_leds = [[0, 0, 0] for i in range(num_channel)]

# Seit der Takt die Tap-Lampen blitzen laesst, schreiben zwei Threads auf die
# Pixelkette: der OSC-Server (Lampen, FX) und der Timer, der den Blitz wieder
# ausmacht.
_pixels_lock = threading.Lock()
button_leds_master = [0, 0, 0]

fx_state = np.zeros(10)

# Was gerade gilt, beim Start einmal erfragt. Die Lampen kommen von A3 Core,
# und Core schickt sie, wenn sich etwas ändert -- nach einem Start hat sich
# nichts geändert, also blieben die LEDs dunkel, obwohl der Filter eines Kanals
# an sein konnte. Siehe a3_mixer_recall.
recall = RecallRequest()
clicks = Clicks()
pushes = PushHoldOff()
hello = HelloEvery()

# OSC -- every address, port and IP out of the one truth, a3-core's
# a3-osc.json, a copy of which the deploy puts beside this script. See
# a3_mixer_osc.
#
# Core's address was a literal here until 2026-09-30, and it was wrong more
# often than it was right: two branches carried 192.168.43.50 and .58, the
# desk a third, and none was reachable after the rig moved subnets. OSC over
# UDP has no way of saying that nobody was listening.
#
# The truth comes from Core (spec truth-from-core, step 2): the desk starts on
# what Core last served (a3_mixer_truth), and listens for Core's /core/here.
# Without a truth, or with a word missing from it, it does not exit any more
# -- systemd only started it into the same exit, a restart loop seen more than
# once. It waits for Core's truth, stores it, and restarts once on it.
announce_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
announce_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
announce_socket.bind(("", ANNOUNCE_PORT))


def say(text):
    print(f"a3-mixer: {text}", file=sys.stderr, flush=True)


def usable(body):
    """Core's truth is only worth a restart if it has every word the desk
    uses -- otherwise the restart would come straight back here."""
    try:
        lacking = MixerOsc(json.loads(body)).missing()
    except (ValueError, KeyError, TypeError, AttributeError) as problem:
        return f"not a truth: {problem!r}"
    return "Core's truth lacks " + ", ".join(lacking) if lacking else None


try:
    osc = load_osc_truth()
    lacking = osc.missing()
except TruthMissing as missing:
    osc, lacking = None, [str(missing)]
if lacking:
    say("the truth lacks " + ", ".join(lacking) + " -- waiting for Core's")
    wait_for_truth(announce_socket, cache_path(), say,
                   own=osc.digest if osc else None, usable=usable)
    say("Core's truth stored, restarting on it")
    os._exit(1)

# $A3_OSC_TRUTH wins at every start, so following Core would only restart the
# desk into the same file forever: with it set, the desk says so and stays.
if follows_core(os.environ):
    threading.Thread(
        target=keep, daemon=True, name="truth keeper",
        args=(announce_socket, osc.digest, cache_path(),
              lambda: (say("Core announced another truth, restarting on it"), os._exit(1)),
              say, lambda: True),
    ).start()
else:
    say("A3_OSC_TRUTH is set: not following Core's truth")

osc_core = SimpleUDPClient(*osc.core())

# The beat clock, addressed directly. A tap is timing, and timing does not
# want a relay in the middle -- A3 Motion's TAP key sends straight at the
# analyzer for the same reason, bypassing even its own message queue.
osc_beatclock = SimpleUDPClient(*osc.beatclock())

# OSC-Server
osc_vu_receive_port = osc.listen_port()

vu_channel_to_led_count = {
    0 : 8,
    1 : 8,
    2 : 8,
    3 : 8,
    4 : 32,
    5 : 32,
    6 : 32,
    7 : 32,
    8 : 32,
    9 : 32,
    10 : 32,
    11 : 32,
}

# The pots' and keys' addresses are a3_mixer_osc's tables (CHANNEL_POTS,
# CHANNEL_KEYS, MASTER_POTS), as the truth's keys.

# The channel strip's keys live in a3_mixer_panel, where a test can reach them
# -- this module needs board, neopixel and serial to import at all.
#
# Rearranged on 2026-09-19: the 3D key, out of service since 2026-09-12 but
# still on the panel, carries PFL now, and PFL's old key carries the tap. The
# reason is the one lamp the three keys share: PFL sat on its red line, into
# which the wrong resistors are soldered, and a cue lamp has to be readable in
# the dark. The blue line of the dead 3D key is free and bright.
#
# What the 3D key must NOT do again: A3 Core's `3d` became the continuous blend
# on 2026-09-12, so a momentary key putting the string "1" into it would drive
# that blend to the stop for as long as a finger held it down, and drop it to
# zero on release. It carries pfl now, which is a flag and takes exactly that.

button_fx_to_mode_name = {
    "0": "high_pass",
    "1": "low_pass",
}

# time_last_receive = 0

def db_value_to_index(value: float, num_leds: int):
    index = int(np.interp(value, [-60, 0], [0, num_leds]))
    if index == num_leds:
        index = num_leds - 1
    return index

def send_vu_data(vu: str, peak_db: float, rms_db: float):
    num_leds = vu_channel_to_led_count[int(vu)]
    peak_index = db_value_to_index(peak_db, num_leds)
    rms_index = db_value_to_index(rms_db, num_leds)

#    print("peak: " + str(peak_db) + " " + str(peak_index))
#    print("rms: " + str(rms_db) + " " + str(rms_index))

    sendData("VU:" + vu + ":" + str(peak_index) + ":" + str(rms_index))

def vu_handler(address: str,
               *osc_arguments: List[Any]) -> None:
    # The meter's number is the channel map's; the firmware's slot is looked
    # up by what the meter measures (a3_mixer_osc.VU_SLOTS).
    number = osc.vu_number(address)
    if number is None:
        return
    # A stem meter has no LED: its peak feeds the displays' meters, noted
    # here and drawn on the displays' own clock.
    pair = osc.stem_pair(number)
    if pair is not None:
        displays.note_peak(pair, osc_arguments[0])
        return
    # The analog return's meter: the return display's A, no LED.
    side = osc.aux_side(number)
    if side is not None:
        displays.note_aux(side, osc_arguments[0])
        return
    # StemDeck's aux bus: the return display's SA, no LED. Only a truth that
    # names stem_aux_L/R sends it; without, the displays fall back.
    side = osc.stem_aux_side(number)
    if side is not None:
        displays.note_stem_aux(side, osc_arguments[0])
        return
    slot = osc.vu_slot(number)
    if slot is None:
        return
    vu = str(slot)

    peak = osc_arguments[0]
    # The four inputs are the channels' A meters too.
    if slot < num_channel:
        displays.note_analog(slot, peak)
    rms = osc_arguments[1]

    # clamp to above 0 to avoid numerical error
    if peak == 0.0:
        peak = sys.float_info.epsilon
    if rms == 0.0:
        rms = sys.float_info.epsilon

    peak_db = 20 * math.log(peak, 10)
    rms_db  = 20 * math.log(rms, 10)

    send_vu_data(vu, peak_db, rms_db)

def send_button_leds_data(channel: int, led_on, led_mode):
    # led_mode is the colour channel of the strip's one pixel: 0 red, 1 green,
    # 2 blue. Which function lights which colour is a3_mixer_panel.LED_COLOUR,
    # and since 2026-09-19 that is fx green and pfl *blue*.
    #
    # Red is the line with the wrong resistors soldered into it, which is the
    # whole reason pfl moved off it. Nothing lights red now: its key carries
    # the tap, and a tap has no state to show. Whether the four tap keys
    # should blink along with the beat the way A3 Motion's TAP does is open --
    # it would take work at Core and here, and was not asked for.
    #
    # pfl used to have a branch of its own here, inverted -- `0 if led_on else
    # 255`. A3 Core inverted it as well, on the way out, and the two cancelled:
    # the desk was right and the wire carried the opposite of what its name
    # said. That cost nothing while the desk was the only thing listening.
    #
    # Since 2026-09-12 every device is told the lamps, because a lamp is meant
    # to show the status. So both inversions came out on the same day and this
    # is one branch: the lamp's address now means "this lamp is lit", and
    # what reaches the pixel is unchanged.
    with _pixels_lock:
        button_leds[channel][led_mode] = 255 if led_on else 0
        pixels[channel] = button_leds[channel]
        pixels.show()

def led_handler_channel(address: str,
                        *osc_arguments: List[Any]) -> None:
#    print(f'led_handler_channel: {address}')

    found = osc.match(address)
    if found is None or found[0] not in LAMPS:
        return
    channel = found[1]["ch"] - 1
    led_type = LAMPS[found[0]]
    led_on = int(osc_arguments[0])
#    print(f'toggling {led_type} led for channel {channel}: {led_on}')

    # Von Core gehört: die Frage nach dem Gesamtzustand ist beantwortet.
    recall.answered()

    colour = led_colour(led_type)
    if colour is not None:
        send_button_leds_data(channel, led_on, colour)

def led_handler_fx(address: str,
                   *osc_arguments: List[Any]) -> None:
#    print(f'led_handler_fx: {address}')

    recall.answered()

    led_fx_mode = osc_arguments[0]

    if led_fx_mode not in ["high_pass", "low_pass"]:
        return

    high_pass = led_fx_mode == "high_pass"

    with _pixels_lock:
        button_leds_master[1] = 0 if high_pass else 255
        button_leds_master[2] = 255 if high_pass else 0
        pixels[num_channel] = button_leds_master
        pixels.show()
    print("button_leds_master")
    #print(button_leds_master)

def _set_tap_lamps(on: bool) -> None:
    with _pixels_lock:
        for channel in range(num_channel):
            button_leds[channel][TAP_FLASH_COLOUR] = 255 if on else 0
            pixels[channel] = button_leds[channel]
        pixels.show()

def beat_handler(address: str,
                 *osc_arguments: List[Any]) -> None:
    """Der Takt blitzt auf den vier Tap-Tastern.

    Alle vier gleich, weil alle vier dieselbe Taste sind: sie senden denselben
    /tap, und eine Lampe, die nur auf einem Kanalzug blinkt, sagt etwas
    Falsches darueber, welcher davon gemeint ist.

    Auf der roten Linie, also der des Tap-Tasters selbst -- siehe
    a3_mixer_panel.TAP_FLASH_COLOUR. Die anderen beiden tragen PFL und FX und
    duerfen von einem Blitz nicht ueberschrieben werden.

    Der Takt kam hier bis zum 2026-09-21 nie an: der beat-analyzer schickte
    ihn an Port 7775, und das Pult lauscht auf 7772. Die 7775 ist der Port,
    auf dem der Analyzer selbst lauscht.
    """
    _set_tap_lamps(True)
    threading.Timer(TAP_FLASH_SECONDS, _set_tap_lamps, args=(False,)).start()

# Serial communication
#ser = serial.Serial('/dev/ttyACM0', 115200)
ser = serial.Serial('/dev/ttyACM0', 4608000)
ser.flush()

def sendData(data): # send Serial data
    data += "\r\n"
    ser.write(data.encode())

def serial_handler(): # dispatch from serial stream and send to osc

    while True:
        line = ser.readline().decode('utf-8').rstrip()

        # global time_last_receive
        # current_time_ns = time.clock_gettime_ns(time.CLOCK_REALTIME)
        # delta_time_ms = (current_time_ns - time_last_receive)/1e6
        # if delta_time_ms < 10:
        #     continue
        # print(f'time delta: {delta_time_ms}')
        # time_last_receive = current_time_ns

        print(line)

        words = line.split(":")

        track = words[1]
        mode = words[2]
        index = words[3]
        value = words[4]

        # The five encoders: positions in, stem words out (a3_mixer_encoders).
        # Only numeric tracks -- the encoders are 0..4.
        # A damaged field parses to None and is skipped, never raised: an
        # exception here ends the serial reader. The edges are the
        # firmware's -- it prints EB on every change of a switch it reads
        # raw, so a bouncing contact is taken apart here (PushHoldOff).
        if mode == "ENC" and track.isdigit():
            position = parse_int(value)
            if position is not None:
                msg = encoder_message(osc, int(track),
                                      clicks.feed(int(track), position))
                if msg:
                    osc_core.send_message(*msg)
        if mode == "EB" and track.isdigit():
            pressed = pushes.feed(int(track), value == "1")
            msg = push_message(osc, int(track), pressed)
            if msg:
                osc_core.send_message(*msg)

        # Buttons
        #
        # A key with no address is ignored, exactly as an unmapped pot is
        # below. It used to be a bare dict lookup, and that is how taking the
        # 3D key out of the table on 2026-09-12 stopped the whole desk: the
        # key is still on the panel, pressing it raised KeyError: '2' inside
        # serial_handler, and that process died. The OSC server in the parent
        # kept running, so systemd still called the service active -- a desk
        # that had gone deaf to every pot and every button looked healthy.
        # Measured: the last serial line before the traceback was T:0:B:2:1.
        if mode == "B":
            # the 4 channel strips
            channel_names = map(str, range(5))
            if track in channel_names:
                function = channel_button(index)

                if function == TAP:
                    # Press only, and the same int the tap key sends -- see
                    # the TAP branch below, which this deliberately mirrors
                    # rather than reimplements.
                    if value == "1":
                        osc_beatclock.send_message(osc.address("tap"), 1)
                elif function in CHANNEL_KEYS:
                    osc_core.send_message(
                        osc.channel_address(CHANNEL_KEYS[function], int(track)),
                        value)
            elif track == "fx" and value == "1":
                if index in button_fx_to_mode_name:
                    osc_core.send_message(osc.address("filter.mode"),
                                          button_fx_to_mode_name[index])

        # The tap key. Press only -- a tap is the moment the finger goes
        # down, and sending the release as well would tap twice per press and
        # halve the tempo.
        #
        # It used to go to A3 Core, on an address Core never subscribed to:
        # the handler was there, its dispatcher.map line was commented out,
        # and so was the rtmidi import it needed. Nobody noticed, because the
        # key kept sending and UDP has no way of saying that nobody listened.
        # Both ends are gone now and this goes where A3 Motion's TAP goes.
        #
        # int 1, not the string off the serial line: the analyzer reads
        # /tap [i] as the beat within the bar and only understands i or f.
        if mode == "TAP" and value == "1":
            osc_beatclock.send_message(osc.address("tap"), 1)

        
        # Potis
        if mode == "P":
            # the 4 channel strips
            channel_names = map(str, range(4))
            if track in channel_names:
                if index in CHANNEL_POTS:
                    osc_core.send_message(
                        osc.channel_address(CHANNEL_POTS[index], int(track)),
                        value)

            # pots in the master section
            elif track == "master":
                if index in MASTER_POTS:
                    osc_core.send_message(osc.address(MASTER_POTS[index]), value)


if __name__ == '__main__':

    proc1 = Process(target=serial_handler)
    proc1.start()

    # Stirbt der serielle Leser, geht dieser Prozess mit.
    #
    # Sonst bleibt das Pult halb lebendig: der OSC-Server hier lebt weiter,
    # also meldet systemd den Unit als `active`, die LEDs und die VU-Meter
    # kommen weiter an -- und kein Poti und keine Taste erreichen Core mehr.
    # Am 2026-09-12 war das zwanzig Minuten lang so, und gesagt hat es nichts.
    #
    # os._exit statt sys.exit: das hier ist ein Thread, und sys.exit beendet
    # nur ihn. Aufgeräumt werden muss nichts -- der Unit hat Restart=on-failure
    # und kommt sauber neu hoch.
    def stop_because_the_child_died(reason):
        print(reason, file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)

    threading.Thread(
        target=watch_child,
        args=(proc1.is_alive, stop_because_the_child_died, time.sleep),
        kwargs={"name": "serial reader"},
        daemon=True,
    ).start()

    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="0.0.0.0", help="The ip to listen on for VU meter messages")
    parser.add_argument("--port", type=int,
                        default=osc_vu_receive_port, help="The port to listen on for VU meter messages")
    args = parser.parse_args()

    dispatcher = dispatcher.Dispatcher()
    dispatcher.map(osc.subscription("vu"), vu_handler)
    for lamp in LAMPS:
        dispatcher.map(osc.subscription(lamp), led_handler_channel)
    dispatcher.map(osc.subscription("filter.led"), led_handler_fx)
    dispatcher.map(osc.subscription("beat"), beat_handler)

    # The displays show what Core announces; until it does, a dash. A failing
    # display is reported inside Displays and never reaches this server.
    displays = open_displays()
    displays.blank_all()

    # A damaged announcement is ignored: nothing may raise into the server.
    def stem_handler_channel(address, *args):
        found = osc.match(address)
        mask = channel_announcement(args)
        if found and mask is not None and 1 <= found[1]["ch"] <= num_channel:
            displays.show_channel(found[1]["ch"] - 1, mask)

    def stem_handler_return(address, *args):
        announced = return_announcement(args)
        if announced:
            displays.show_return(*announced)

    # Where a channel's selector cursor stands, and the return's mode: each
    # on its own display. A damaged value is ignored.
    def stem_handler_cursor(address, *args):
        found = osc.match(address)
        cursor = cursor_announcement(args)
        if found and cursor is not None and 1 <= found[1]["ch"] <= num_channel:
            displays.show_cursor(found[1]["ch"] - 1, cursor)

    def stem_handler_mode(address, *args):
        mode = mode_announcement(args)
        if mode is not None:
            displays.show_return_mode(mode)

    dispatcher.map(osc.subscription("channel.stem"), stem_handler_channel)
    dispatcher.map(osc.subscription("aux-return.stem"), stem_handler_return)
    dispatcher.map(osc.subscription("channel.stem.cursor"), stem_handler_cursor)
    dispatcher.map(osc.subscription("aux-return.stem.mode"), stem_handler_mode)


    # Nach dem Gesamtzustand fragen, bis er kommt: Core kann später hochkommen
    # als das Pult, und die Lampen sind bis dahin dunkel.
    # Which truth the desk speaks, every 30 s for as long as it runs: a Core
    # restarted at any hour hears it again (a3_mixer_recall). A send that
    # fails -- the desk up before its network -- is tried again, not fatal.
    def send_to_core(kind):
        if kind == "hello":
            osc_core.send_message(*osc.hello())
        else:
            osc_core.send_message(osc.address("state.recall"), 1)

    asker = StateAsker(hello, recall, send_to_core,
                       lambda line: print(line, file=sys.stderr, flush=True))

    def ask_for_the_state():
        while True:
            asker.ask(time.monotonic())
            time.sleep(1.0)

    threading.Thread(target=ask_for_the_state, daemon=True).start()

    server = osc_server.BlockingOSCUDPServer((args.ip, args.port), dispatcher)
#    print("Serving on {}".format(server.server_address))
    server.serve_forever()

