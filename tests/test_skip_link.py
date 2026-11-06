"""The Skip to content link shows only after a Tab press (zorbit/studio_ui/skiplink.js), run by tests/js/skip_link.js. Skipped
when node is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_only_a_tab_press_shows_the_skip_link():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "skip_link.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "skip link checks pass" in run.stdout
