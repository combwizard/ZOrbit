"""Empty slots and Keep slots in place (zorbit/studio_ui/slots.js), run by tests/js/slots.js. Skipped when node is not
installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_slot_helpers_place_clear_swap_and_resize_the_item_list():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "slots.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "slot checks pass" in run.stdout
