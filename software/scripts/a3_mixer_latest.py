# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Meters: the newest wins, and the desk's only (a3-audio/a3-mixer#6).

Some 650 datagrams a second reach the desk: the beat-analyzer's meter
bundles and StemDeck's single meters. The desk shows 28 of 66 meters, yet
python-osc parsed and dispatched every one; its thread ran at 88 % of the
Pi, the socket's queue stayed full and stem, cursor and lamp messages from
Core waited behind it. So, as Core does with positions (a3_core_latest,
2026-10-02), the desk takes everything waiting, unpacks bundles, drops the
meters it does not show, keeps per shown meter only the newest value, and
hands every other message on once, in the order it came.

Only meters are merged: a level is worth nothing once a newer one has
arrived. Everything else -- a stem mask, a cursor, a lamp -- is a step that
counts and keeps its place.

The OSC is read by hand, only as far as the address -- and a kept meter's
floats, which go to the meter handler directly: python-osc still parses and
dispatches everything else, and this module needs no library to import
(system python has none). A bundle's timetag is not kept; the
senders bundle for "now".
"""

import select
import socket
import struct
import traceback

BUNDLE_HEAD = b"#bundle\0"
BUNDLE_HEADER_SIZE = len(BUNDLE_HEAD) + 8  # + the timetag


class Damaged(ValueError):
    """A datagram that is not OSC as far as this module reads it."""


def messages_in(data):
    """The messages a datagram carries, bundles unpacked, in order."""
    if not data.startswith(BUNDLE_HEAD):
        return [data]
    found = []
    at = BUNDLE_HEADER_SIZE
    while at < len(data):
        if at + 4 > len(data):
            raise Damaged("bundle element without its size")
        (size,) = struct.unpack_from(">i", data, at)
        element = data[at + 4:at + 4 + size]
        if size <= 0 or len(element) != size:
            raise Damaged("bundle element shorter than its size")
        found += messages_in(element)
        at += 4 + size
    return found


def address_of(message):
    """A message's address: the OSC string it starts with."""
    end = message.find(b"\0")
    if not message.startswith(b"/") or end < 0:
        raise Damaged("no OSC address")
    return message[:end].decode("ascii", "replace")


def _meter_key(message, osc):
    """("drop", None) for a meter the desk does not show, ("meter", address)
    for one it shows, (None, None) for every other message."""
    number = osc.vu_number(address_of(message))
    if number is None:
        return None, None
    if not osc.shows_meter(number):
        return "drop", None
    return "meter", address_of(message)


def coalesce(packets, osc):
    """`packets` as they arrived, (data, client), as single messages: shown
    meters only the newest per address, at its place; unshown meters gone;
    everything else as it came. A datagram that does not read is passed on
    whole -- the dispatcher deals with it, as it did before."""
    return [(message, client) for message, client, _ in _kept(packets, osc)]


def _kept(packets, osc):
    """coalesce(), each with whether it is a shown meter."""
    unpacked = []
    for data, client in packets:
        try:
            for message in messages_in(data):
                unpacked.append((message, client, *_meter_key(message, osc)))
        except Damaged:
            unpacked.append((data, client, None, None))
    last = {key: i for i, (_, _, kind, key) in enumerate(unpacked) if kind == "meter"}
    return [(message, client, kind == "meter")
            for i, (message, client, kind, key) in enumerate(unpacked)
            if kind is None or (kind == "meter" and last[key] == i)]


def _padded_end(at):
    return at + 4 - at % 4


def floats_of(message):
    """(address, *floats) of a message whose arguments are all floats, as
    python-osc would hand them to a handler; None for any other message."""
    address_end = message.find(b"\0")
    tags_at = _padded_end(address_end)
    tags_end = message.find(b"\0", tags_at)
    tags = message[tags_at:tags_end]
    if address_end < 0 or tags_end < 0 or not tags.startswith(b",") \
            or tags.strip(b"f") != b",":
        return None
    count = len(tags) - 1
    values_at = _padded_end(tags_end)
    if len(message) != values_at + 4 * count:
        return None
    return (message[:address_end].decode("ascii", "replace"),
            *struct.unpack_from(f">{count}f", message, values_at))


def drain(sock, limit):
    """Up to `limit` waiting datagrams as (data, client), without waiting."""
    packets = []
    while len(packets) < limit:
        try:
            packets.append(sock.recvfrom(65536, socket.MSG_DONTWAIT))
        except BlockingIOError:
            break
    return packets


def serve(sock, handle, osc, limit, report, running, on_meter=None):
    """The desk's OSC loop: wait for the socket, take what waits, hand on
    what coalesce keeps. A kept meter of plain floats goes to `on_meter`
    (address, *floats) if given -- python-osc 1.9.3 runs a regex per mapping
    for every message, and the meters are most of them -- everything else
    to `handle` (data, client). A handler that raises is reported and the
    loop goes on, as serve_forever's did: one bad message must not stop the
    desk."""
    while running():
        select.select([sock], [], [])
        for data, client, is_meter in _kept(drain(sock, limit), osc):
            try:
                _hand_on(data, client, is_meter, handle, on_meter)
            except Exception:  # noqa: BLE001 -- reported, never fatal
                report(traceback.format_exc())


def _hand_on(data, client, is_meter, handle, on_meter):
    meter = floats_of(data) if is_meter and on_meter else None
    if meter is None:
        handle(data, client)
    else:
        on_meter(*meter)
