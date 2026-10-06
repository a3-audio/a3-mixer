# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's OSC thread must not drown (a3-audio/a3-mixer#6).

Some 650 datagrams a second arrive, most of them meters the desk does not
show; python-osc parsed and dispatched every one, the thread ran at 88 % and
stem, cursor and lamp messages waited behind the queue. The desk now takes
everything waiting, keeps per /vu address only the newest of the meters it
shows, drops the others, and hands the rest on in arrival order.
"""

import socket
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import a3_mixer_osc  # noqa: E402
from a3_mixer_latest import coalesce, drain, serve  # noqa: E402
from test_osc_truth import made_up, real_truth_path  # noqa: E402

SHOWN_IN_THE_REAL_TRUTH = set(range(11, 19)) | {35, 36} | set(range(41, 59))


def _padded(raw):
    return raw + b"\0" * (4 - len(raw) % 4)


def message(address, *floats):
    """An OSC message of floats, without python-osc (not in system python)."""
    tags = "," + "f" * len(floats)
    return (_padded(address.encode()) + _padded(tags.encode())
            + b"".join(struct.pack(">f", value) for value in floats))


def bundle(*contents):
    """An OSC bundle, timetag 'immediately', of messages or bundles."""
    return (b"#bundle\0" + struct.pack(">Q", 1)
            + b"".join(struct.pack(">i", len(c)) + c for c in contents))


def kept(packets, osc):
    return [data for data, _ in coalesce([(p, None) for p in packets], osc)]


class TheDeskShowsTheseMeters(unittest.TestCase):
    def test_the_real_truth_shows_exactly_the_desks_meters(self):
        osc = a3_mixer_osc.load(real_truth_path())
        meters = len(osc._data["vu_meters"])
        shown = {n for n in range(0, meters + 2) if osc.shows_meter(n)}
        self.assertEqual(shown, SHOWN_IN_THE_REAL_TRUTH)

    def test_shown_means_found_by_name(self):
        osc = made_up(vu_meters=["free", "stem_a1", "main_sub", "aux_R",
                                 "stem_aux_L", "in1_pre"] + list(a3_mixer_osc.INPUT_METERS))
        self.assertEqual([osc.shows_meter(n) for n in range(1, 8)],
                         [False, True, True, True, True, False, True])

    def test_a_mono_input_is_shown_while_there_are_no_stereo_ones(self):
        self.assertTrue(made_up(vu_meters=["in1_pre"]).shows_meter(1))


class OnlyTheNewestShownMeter(unittest.TestCase):
    def setUp(self):
        self.osc = a3_mixer_osc.load(real_truth_path())

    def test_two_of_one_shown_meter_and_one_unshown_leave_the_newest(self):
        old, unshown, new = (message("/vu/51", 0.1, 0.1),
                             message("/vu/60", 0.5, 0.5),
                             message("/vu/51", 0.2, 0.2))
        self.assertEqual(kept([old, unshown, new], self.osc), [new])

    def test_other_messages_keep_their_order_and_are_never_merged(self):
        mask = message("/channel/1/stem", 3.0)
        cursor = message("/channel/1/stem/cursor", 2.0)
        cursor_again = message("/channel/1/stem/cursor", 4.0)
        vu = message("/vu/41", 0.3, 0.3)
        self.assertEqual(
            kept([mask, message("/vu/41", 0.1, 0.1), cursor, vu, cursor_again], self.osc),
            [mask, cursor, vu, cursor_again])

    def test_bundles_are_unpacked_nested_ones_too(self):
        beat = message("/beat", 1.0)
        shown = message("/vu/11", 0.4, 0.4)
        packets = [bundle(message("/vu/11", 0.1, 0.1), message("/vu/1", 0.1, 0.1)),
                   bundle(beat, bundle(shown, message("/vu/66", 0.0, 0.0)))]
        self.assertEqual(kept(packets, self.osc), [beat, shown])

    def test_a_damaged_datagram_is_passed_on_for_the_dispatcher(self):
        damaged = b"/vu/51"
        self.assertEqual(kept([damaged], self.osc), [damaged])

    def test_the_sender_travels_with_its_message(self):
        packets = [(message("/beat", 1.0), ("10.0.0.1", 1)),
                   (bundle(message("/vu/51", 0.1, 0.1)), ("10.0.0.2", 2))]
        self.assertEqual([client for _, client in coalesce(packets, self.osc)],
                         [("10.0.0.1", 1), ("10.0.0.2", 2)])


class TheDeskTakesWhatWaits(unittest.TestCase):
    def setUp(self):
        self.osc = a3_mixer_osc.load(real_truth_path())
        self.inbox, self.sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(self.inbox.close)
        self.addCleanup(self.sender.close)

    def queue(self, packets):
        for packet in packets:
            self.sender.send(packet)

    def test_drain_takes_everything_waiting_without_waiting(self):
        self.queue([message("/beat", 1.0)] * 3)
        self.assertEqual(len(drain(self.inbox, 100)), 3)
        self.assertEqual(drain(self.inbox, 100), [])

    def test_drain_stops_at_its_limit(self):
        self.queue([message("/beat", 1.0)] * 5)
        self.assertEqual(len(drain(self.inbox, 2)), 2)

    def serve_once(self, handle, report=lambda text: None, on_meter=None):
        passes = iter([True, False])
        serve(self.inbox, handle, self.osc, 1000, report, lambda: next(passes),
              on_meter=on_meter)

    def test_one_pass_dispatches_each_other_message_once(self):
        others = [message(f"/channel/{n}/stem", float(n)) for n in range(1, 5)]
        meters = [message("/vu/51", 0.1 * n, 0.1) for n in range(1, 21)]
        self.queue(meters[:10] + others + meters[10:] + [bundle(*meters[:5])])
        seen = []
        self.serve_once(lambda data, client: seen.append(data))
        self.assertEqual(seen, others + [meters[4]])

    def test_a_handler_that_raises_is_reported_and_the_rest_dispatched(self):
        self.queue([message("/beat", 1.0), message("/tap", 1.0)])
        seen, reports = [], []

        def handle(data, client):
            seen.append(data)
            if len(seen) == 1:
                raise ValueError("bad packet")

        self.serve_once(handle, reports.append)
        self.assertEqual(len(seen), 2)
        self.assertIn("bad packet", reports[0])


class AShownMeterSkipsTheDispatcher(unittest.TestCase):
    """python-osc 1.9.3 builds and runs a regex per mapping for every
    message; a kept meter of plain floats goes to the meter handler
    directly, with the arguments python-osc would have given it."""

    def setUp(self):
        self.osc = a3_mixer_osc.load(real_truth_path())
        self.inbox, self.sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(self.inbox.close)
        self.addCleanup(self.sender.close)

    def serve_once(self, packets):
        for packet in packets:
            self.sender.send(packet)
        handled, meters = [], []
        passes = iter([True, False])
        serve(self.inbox, lambda data, client: handled.append(data), self.osc,
              1000, lambda text: None, lambda: next(passes),
              on_meter=lambda address, *args: meters.append((address, *args)))
        return handled, meters

    def test_a_meter_of_floats_goes_to_the_meter_handler(self):
        handled, meters = self.serve_once([message("/vu/51", 0.5, 0.25),
                                           message("/beat", 1.0)])
        self.assertEqual(meters, [("/vu/51", 0.5, 0.25)])
        self.assertEqual(handled, [message("/beat", 1.0)])

    def test_a_meter_of_anything_else_goes_through_the_dispatcher(self):
        odd = _padded(b"/vu/51") + _padded(b",s") + _padded(b"loud")
        self.assertEqual(self.serve_once([odd]), ([odd], []))


class TheDeskServesThroughIt(unittest.TestCase):
    """a3-mixer.py needs the Pi to import, so its wiring is read."""

    def test_the_server_is_not_served_forever(self):
        source = (Path(__file__).resolve().parents[1] / "scripts/a3-mixer.py").read_text()
        code = "".join(line for line in source.splitlines(True)
                       if not line.lstrip().startswith("#"))
        self.assertFalse("serve_forever()" in code, "a3-mixer.py serves forever")
        self.assertIn("serve(server.socket", code)
        self.assertIn("on_meter=vu_handler", code)


if __name__ == "__main__":
    unittest.main()
