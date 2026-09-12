# SPDX-FileCopyrightText: 2024 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
import math
import time
import argparse
import serial  # pySerial https://pyserial.readthedocs.io/
import numpy as np

import board
import neopixel

from multiprocessing import Process

from pythonosc.udp_client import SimpleUDPClient
from pythonosc import osc_server
from pythonosc import dispatcher

from typing import List, Any

pixel_pin = board.D12
num_pixels = 14
num_channel = 4

ORDER = neopixel.GRB

pixels = neopixel.NeoPixel(
    pixel_pin, num_pixels, brightness=1, auto_write=False, pixel_order=ORDER
)

button_leds = [[0, 0, 0] for i in range(num_channel)]
button_leds_master = [0, 0, 0]

fx_state = np.zeros(10)

# OSC-Clients
#
# One host, two ports: A3 Core and the beat-analyzer run on the same machine,
# so there is one address to change here rather than two that can drift apart.
#
# **This line has been wrong more often than it has been right.** The two
# branches that met in this merge carried 192.168.43.50 and 192.168.43.58, the
# running copy on the desk carried a third, and none of them was reachable:
# Core has been on 192.168.8.10 since the rig moved subnets. An address in
# source is an address that goes stale between two gigs, and nothing reports
# it -- OSC over UDP has no way of saying that nobody was listening.
#
# A3 Core learned this first and took --mixer as an argument. This wants the
# same and does not have it yet.
CORE_HOST = '192.168.8.10'
osc_core = SimpleUDPClient(CORE_HOST, 9000)

# The beat clock, addressed directly. A tap is timing, and timing does not
# want a relay in the middle -- A3 Motion's TAP key sends straight at the
# analyzer for the same reason, bypassing even its own message queue.
osc_beatclock = SimpleUDPClient(CORE_HOST, 7775)

# OSC-Server
osc_vu_receive_port = 7772

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

# channel strips 1-4
analog_pots_per_channel_to_osc_param = {
    "0": "fx-send",
    "1": "gain",
    "2": "eq/high",
    "3": "eq/mid",
    "4": "eq/low",
    "5": "volume",
}

# The channel strip's keys. There were three: "2" was the 3D switch.
#
# **The key is still on the panel.** It is out of service in software, which
# is a guard rather than a tidy-up: A3 Core's `3d` became the continuous blend
# on 2026-09-12, so a momentary key putting the string "1" into it would drive
# that blend to the stop for as long as a finger held it down, and drop it to
# zero on release. Restoring this line restores that.
#
# Core's own boolean for the key (`/channel/n/4d`) went the same day, so there
# is not even an address to point it at without building one. What the key
# should do instead is open -- see
# issues/a3-core-der-3d-taster-des-mixers-faehrt-die-blende.md.
button_per_channel_to_osc_param = {
    "0": "pfl",
    "1": "fx",
}

button_fx_to_mode_name = {
    "0": "high_pass",
    "1": "low_pass",
}

# master section pots mapping
master_pots_to_osc_message = {
    "0": "/master/volume",
    "2": "/fx/frequency",
    "1": "/fx/resonance",
    "3": "/master/booth",
    "4": "/master/phones_mix",
    "5": "/master/phones_volume",
    "6": "/master/return",
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
    words = address.split("/")
    vu = words[2]

    peak = osc_arguments[0]
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
    # led_mode is the colour channel of the button's pixel: 0 red (pfl),
    # 1 green (fx), 2 blue (3d).
    #
    # The blue one is wired to a lamp that nothing lights any more: A3 Core
    # stopped sending /channel/n/led/3d when the flag behind it went, and
    # led_handler_channel below no longer has a branch for it either. The
    # colour channel stays named because the pixel has three and the key it
    # belongs to is still on the panel -- see button_per_channel_to_osc_param.
    #
    # pfl used to have a branch of its own here, inverted -- `0 if led_on else
    # 255`. A3 Core inverted it as well, on the way out, and the two cancelled:
    # the desk was right and the wire carried the opposite of what its name
    # said. That cost nothing while the desk was the only thing listening.
    #
    # Since 2026-09-12 every device is told the lamps, because a lamp is meant
    # to show the status. So both inversions came out on the same day and this
    # is one branch: `/channel/n/led/pfl` now means "this lamp is lit", and
    # what reaches the pixel is unchanged.
    button_leds[channel][led_mode] = 255 if led_on else 0
    pixels[channel] = button_leds[channel]
    pixels.show()

def led_handler_channel(address: str,
                        *osc_arguments: List[Any]) -> None:
#    print(f'led_handler_channel: {address}')

    words = address.split("/")
    channel = words[2]
    led_type = words[4]
    led_on = int(osc_arguments[0])
    led_mode = 0
#    print(f'toggling {led_type} led for channel {channel}: {led_on}')

    if led_type == "pfl":
        led_mode = 0
        send_button_leds_data(int(channel), led_on, led_mode)
    elif led_type == "fx":
        led_mode = 1
        send_button_leds_data(int(channel), led_on, led_mode)

def led_handler_fx(address: str,
                   *osc_arguments: List[Any]) -> None:
#    print(f'led_handler_fx: {address}')

    led_fx_mode = osc_arguments[0]

    if led_fx_mode not in ["high_pass", "low_pass"]:
        return

    high_pass = led_fx_mode == "high_pass"

    button_leds_master[1] = 0 if high_pass else 255
    button_leds_master[2] = 255 if high_pass else 0
    pixels[num_channel] = button_leds_master
    pixels.show()
    print("button_leds_master")
    #print(button_leds_master)

def tap_handler(address: str,
               *osc_arguments: List[Any]) -> None:
    words = address.split("/")
    tap = words[1]

    value = osc_arguments[0]

    message = "TAP:" + str(value)
    sendData(message)
    print(message)

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

#        print(f'value: {value}')

        # Buttons
        if mode == "B":
            # the 4 channel strips
            channel_names = map(str, range(5))
            if track in channel_names:
                osc_core.send_message("/channel/" + track + "/" +
                                      button_per_channel_to_osc_param[index], value)
            elif track == "fx" and value == "1":
                osc_core.send_message("/fx/mode", button_fx_to_mode_name[index])

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
            osc_beatclock.send_message("/tap", 1)

        
        # Potis
        if mode == "P":
            # the 4 channel strips
            channel_names = map(str, range(4))
            if track in channel_names:
                if index in analog_pots_per_channel_to_osc_param:
                    osc_core.send_message("/channel/" + track + "/" +
                                            analog_pots_per_channel_to_osc_param[index], value)

            # pots in the master section
            elif track == "master":
                if index in master_pots_to_osc_message:
                    osc_core.send_message(master_pots_to_osc_message[index], value)


if __name__ == '__main__':

    proc1 = Process(target=serial_handler)
    proc1.start()

    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="0.0.0.0", help="The ip to listen on for VU meter messages")
    parser.add_argument("--port", type=int,
                        default=osc_vu_receive_port, help="The port to listen on for VU meter messages")
    args = parser.parse_args()

    dispatcher = dispatcher.Dispatcher()
    dispatcher.map("/vu/*", vu_handler)
    dispatcher.map("/channel/*/led/*", led_handler_channel)
    dispatcher.map("/fx/led", led_handler_fx)
    #dispatcher.map("/clock", tap_handler)

    server = osc_server.BlockingOSCUDPServer((args.ip, args.port), dispatcher)
#    print("Serving on {}".format(server.server_address))
    server.serve_forever()

