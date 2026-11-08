"""The grids' own scroll bar, which a pen can drag (zorbit/studio_ui/scrollbar.js), run by tests/js/scroll_bar.js. Skipped
when node is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_grid_scroll_bar_follows_the_list_and_the_pointer():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "scroll_bar.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "scroll bar checks pass" in run.stdout
