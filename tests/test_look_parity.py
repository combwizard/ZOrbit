"""Studio's look resolver (zorbit/studio_ui/look.js) against looks.py: tests/js/look_parity.js runs it over the cases in
tests/fixtures/look_cases.json (values, origins and the loader's messages for the ring, a menu and one slot). Skipped
when node is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_javascript_resolver_gives_what_looks_py_gives():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "look_parity.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "look cases match" in run.stdout


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_javascript_resolver_edits_a_config_the_way_studio_needs():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "look_edit.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "look editing checks pass" in run.stdout
