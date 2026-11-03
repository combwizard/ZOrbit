"""The tag filter's Any / All rule (zorbit/studio_ui/tagfilter.js), run by tests/js/tag_filter.js. Skipped when node is
not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_tag_filter_matches_any_or_all_of_the_chosen_tags():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "tag_filter.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "tag filter checks pass" in run.stdout
