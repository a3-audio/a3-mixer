# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk is in front: it says hello and sends its positions the moment it
hears Core, not when its 30 s timer comes round (rig, 2026-10-14: after a
Core reboot the desk was ignored for up to 30 s, because Core only takes a
device's values after its hello).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_positions import ASK_THE_PANEL, Positions           # noqa: E402
from a3_mixer_recall import CoreArrival, DeskInFront  # noqa: E402
from a3_mixer_truth import ANNOUNCE_ADDRESS, hear           # noqa: E402


class CoreIsNewToTheDesk(unittest.TestCase):
    def test_the_first_announcement_is_news(self):
        self.assertTrue(CoreArrival().heard(now=0.0))

    def test_the_steady_beat_is_not(self):
        arrival = CoreArrival()
        arrival.heard(now=0.0)
        self.assertFalse(arrival.heard(now=2.0))
        self.assertFalse(arrival.heard(now=4.0))

    def test_a_core_back_after_silence_is_news(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0)
        self.assertTrue(arrival.heard(now=40.0))

    def test_two_missed_beats_are_not_yet_silence(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0)
        self.assertFalse(arrival.heard(now=4.9))

    def test_a_forgotten_arrival_is_news_again(self):
        arrival = CoreArrival()
        arrival.heard(now=0.0)
        arrival.forget()
        self.assertTrue(arrival.heard(now=2.0))

    def test_a_changed_boot_id_is_news_within_the_silence(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0, boot_id="one")
        self.assertTrue(arrival.heard(now=2.0, boot_id="two"))

    def test_the_same_boot_id_is_the_steady_beat(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0, boot_id="one")
        self.assertFalse(arrival.heard(now=2.0, boot_id="one"))

    def test_an_old_core_without_boot_id_keeps_the_silence_rule_only(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0)
        self.assertFalse(arrival.heard(now=2.0))
        self.assertTrue(arrival.heard(now=40.0))

    def test_a_core_that_starts_to_send_a_boot_id_is_a_new_core(self):
        arrival = CoreArrival(silence=5.0)
        arrival.heard(now=0.0)
        self.assertTrue(arrival.heard(now=2.0, boot_id="one"))


class TheDeskReactsToCore(unittest.TestCase):
    def setUp(self):
        self.log = []

    def reaction(self, send=None):
        return DeskInFront(CoreArrival(),
                           send or self.log.append,
                           lambda: self.log.append("dump"),
                           lambda text: self.log.append(("report", text)))

    def test_hello_then_positions_on_the_first_announcement(self):
        self.reaction().heard(now=0.0)
        self.assertEqual(self.log, ["hello", "dump"])

    def test_nothing_on_the_steady_beat(self):
        reaction = self.reaction()
        reaction.heard(now=0.0)
        self.log.clear()
        reaction.heard(now=2.0)
        self.assertEqual(self.log, [])

    def test_a_failed_hello_sends_no_positions_and_is_tried_next_time(self):
        calls = []

        def send(kind):
            calls.append(kind)
            if len(calls) == 1:
                raise OSError("network unreachable")

        reaction = self.reaction(send)
        reaction.heard(now=0.0)
        self.assertEqual([entry[0] for entry in self.log], ["report"])
        reaction.heard(now=2.0)
        self.assertEqual((calls, self.log[-1]), (["hello", "hello"], "dump"))


class Table(unittest.TestCase):
    def test_the_last_value_of_each_address_is_kept(self):
        positions, sent = Positions(), []
        positions.note("/a", "1")
        positions.note("/b", "2")
        positions.note("/a", "3")
        positions.send_all(lambda address, value: sent.append((address, value)),
                           lambda text: None)
        self.assertEqual(sorted(sent), [("/a", "3"), ("/b", "2")])

    def test_a_value_is_new_until_it_was_noted(self):
        # A calibrated fader resting in a dead zone reads 0.0 again and
        # again; Core needs it once.
        positions = Positions()
        self.assertTrue(positions.is_new("/a", 0.0))
        positions.note("/a", 0.0)
        self.assertFalse(positions.is_new("/a", 0.0))
        self.assertTrue(positions.is_new("/a", 0.5))
        self.assertTrue(positions.is_new("/b", 0.0))

    def test_an_empty_table_sends_nothing_and_says_so_once(self):
        positions, sent, said = Positions(), [], []
        for _ in range(3):
            positions.send_all(lambda *message: sent.append(message), said.append)
        self.assertEqual((sent, len(said)), ([], 1))
        self.assertIn("no positions known yet", said[0])

    def test_the_table_is_not_empty_any_more_after_a_note(self):
        positions, said = Positions(), []
        positions.send_all(lambda *m: None, said.append)
        positions.note("/a", "1")
        positions.send_all(lambda *m: None, said.append)
        positions.send_all(lambda *m: None, said.append)
        self.assertEqual(len(said), 1)


class AskThePanel(unittest.TestCase):
    """The script may restart while the panel keeps running, and the panel
    sends a pot only when it moves: the table stays empty. So the script asks
    the panel to send every pot once (2026-10-14)."""

    firmware = (Path(__file__).resolve().parents[2]
                / "firmware/src/main.cpp").read_text()

    def test_an_empty_table_asks_the_panel(self):
        asked = []
        Positions().send_all(lambda *m: None, lambda text: None,
                             ask_panel=lambda: asked.append(1))
        self.assertEqual(asked, [1])

    def test_a_known_table_does_not_ask(self):
        positions, asked = Positions(), []
        positions.note("/a", "1")
        positions.send_all(lambda *m: None, lambda text: None,
                           ask_panel=lambda: asked.append(1))
        self.assertEqual(asked, [])

    def test_the_question_is_a_meter_line_an_old_firmware_ignores(self):
        # The old firmware reads "VU:<slot>:<a>:<b>" to the end of the line
        # and draws only slots 0..11; any other word leaves the line's rest
        # in its buffer and shifts every later line. Slot -1 it reads whole
        # and draws nothing.
        word, slot, first, second = ASK_THE_PANEL.split(":")
        self.assertEqual(word, "VU")
        self.assertFalse(0 <= int(slot) < 12)
        int(first), int(second)

    def test_the_firmware_knows_the_question(self):
        slot = ASK_THE_PANEL.split(":")[1]
        self.assertIn(f"SEND_ALL_POTS_SLOT = {slot};", self.firmware)


def message(address, *strings):
    def padded(text):
        raw = text.encode() + b"\0"
        return raw + b"\0" * (-len(raw) % 4)
    return padded(address) + padded("," + "s" * len(strings)) + b"".join(
        padded(s) for s in strings)


class FakeSocket:
    def __init__(self, packets):
        self.packets = list(packets)

    def running(self):
        return bool(self.packets)

    def recvfrom(self, size):
        return self.packets.pop(0), ("x", 0)


class TheAnnouncementReachesTheReaction(unittest.TestCase):
    def test_hear_tells_of_every_announcement(self):
        heard = []
        sock = FakeSocket([message(ANNOUNCE_ADDRESS, "http://x", "b" * 64)] * 2)
        hear(sock, lambda boot_id: heard.append(1), sock.running)
        self.assertEqual(len(heard), 2)

    def test_hear_passes_the_boot_id_on_when_there_is_one(self):
        heard = []
        sock = FakeSocket([message(ANNOUNCE_ADDRESS, "http://x", "b" * 64, "boot1"),
                           message(ANNOUNCE_ADDRESS, "http://x", "b" * 64)])
        hear(sock, heard.append, sock.running)
        self.assertEqual(heard, ["boot1", None])

    def test_a_changed_boot_id_makes_the_desk_say_hello_again(self):
        log = []
        reaction = DeskInFront(CoreArrival(), log.append, lambda: log.append("dump"), log.append)
        reaction.heard(now=0.0, boot_id="one")
        reaction.heard(now=2.0, boot_id="one")
        reaction.heard(now=4.0, boot_id="two")
        self.assertEqual(log, ["hello", "dump", "hello", "dump"])

    def test_hear_ignores_other_traffic(self):
        heard = []
        sock = FakeSocket([message("/vu/1", "x")])
        hear(sock, lambda boot_id: heard.append(1), sock.running)
        self.assertEqual(heard, [])


class WiredIntoTheDesk(unittest.TestCase):
    source = (Path(__file__).resolve().parents[1] / "scripts/a3-mixer.py").read_text()

    def test_the_desk_uses_the_pieces(self):
        for word in ("DeskInFront(", "Positions()", "target=hear"):
            self.assertIn(word, self.source)

    def test_pots_are_noted_before_they_are_sent(self):
        self.assertIn("positions.note(", self.source)

    def test_the_reader_asks_the_panel_when_it_starts(self):
        reader = self.source.split("def serial_handler")[1]
        self.assertIn("ask_the_panel()", reader.split("while True")[0])

    def test_an_empty_table_asks_the_panel_when_core_appears(self):
        self.assertIn("ask_panel=ask_the_panel", self.source)


if __name__ == "__main__":
    unittest.main()
