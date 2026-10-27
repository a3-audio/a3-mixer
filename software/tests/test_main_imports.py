# SPDX-FileCopyrightText: 2026 Raphael Eismann
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every name a3-mixer.py imports from its sibling modules exists there.

a3-mixer.py is a script (a dash in its name), so no test imports it; on
2026-10-26 it asked a3_mixer_displays for a name that lived only in
display_panel, and the mixer crash-looped on the rig."""

import ast
import importlib
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "a3-mixer-set-display"))


class MainScriptImports(unittest.TestCase):
    def test_every_sibling_name_exists(self):
        tree = ast.parse((SCRIPTS / "a3-mixer.py").read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("a3_mixer_"):
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                self.assertTrue(hasattr(module, alias.name), f"{node.module}.{alias.name}")


if __name__ == "__main__":
    unittest.main()
