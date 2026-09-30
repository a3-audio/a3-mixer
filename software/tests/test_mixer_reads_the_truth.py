# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""No OSC address, IP or port is written into the desk's scripts.

They come from the one truth (a3_mixer_osc). A literal left behind is a
second truth, and the desk's Core address -- a literal until 2026-09-30 --
was wrong on three branches at once.
"""

import ast
import re
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FILES = ("a3-mixer.py", "a3_mixer_panel.py", "a3_mixer_recall.py")

OUR_WORDS = re.compile(r"^/(channel|master|fx|filter|vu|beat|tap|clockmode|state)\b")
IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
#: The ports the truth gives the desk and the machines it talks to.
PORTS = {9000, 7771, 7772, 7775}


def constants(path):
    tree = ast.parse(path.read_text())
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and id(node) not in docstrings:
            yield node


class NoLiteralLeft(unittest.TestCase):
    def test_no_osc_address(self):
        for name in FILES:
            for node in constants(SCRIPTS / name):
                if isinstance(node.value, str):
                    self.assertIsNone(OUR_WORDS.match(node.value),
                                      f"{name}:{node.lineno} {node.value!r}")

    def test_no_ip(self):
        for name in FILES:
            for node in constants(SCRIPTS / name):
                if isinstance(node.value, str) and node.value != "0.0.0.0":
                    self.assertIsNone(IPV4.search(node.value),
                                      f"{name}:{node.lineno} {node.value!r}")

    def test_no_port(self):
        for name in FILES:
            for node in constants(SCRIPTS / name):
                if isinstance(node.value, int) and not isinstance(node.value, bool):
                    self.assertNotIn(node.value, PORTS,
                                     f"{name}:{node.lineno} {node.value!r}")


if __name__ == "__main__":
    unittest.main()
