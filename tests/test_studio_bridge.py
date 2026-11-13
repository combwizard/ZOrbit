"""The "Show ZBrush's state on the ring" switch on Studio's ZBrush bridge card (zorbit/studio_ui/app.js and mode.js), run by
tests/js/studio_bridge.js. The loader's message for a bad value, which the JavaScript turns into words, is pinned in
tests/test_config.py. Skipped when node is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_show_state_switch_reads_and_writes_the_key_and_its_messages_read_well():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "studio_bridge.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=120, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "studio bridge checks pass" in run.stdout
