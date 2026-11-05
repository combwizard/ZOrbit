"""Which cards of a long grid get built (zorbit/studio_ui/gridwindow.js), run by tests/js/grid_window.js. Skipped when node
is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_grid_builds_the_cards_near_the_view():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "grid_window.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "grid window checks pass" in run.stdout
