"""What Simple mode hides (zorbit/studio_ui/mode.js): item types, ring settings and problem targets that are Full only,
run by tests/js/mode_gating.js. Skipped when node is not installed."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_simple_mode_hides_what_the_docs_say_and_problem_links_switch_to_full_when_they_must():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "mode_gating.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "mode gating checks pass" in run.stdout


@pytest.mark.parametrize("page", ["index.html", "popout.html"])
def test_every_page_that_loads_app_js_loads_mode_js_first(page):
    """app.js reads window.ZMode when it loads, so both Studio and the browser window must load mode.js before it."""
    with open(os.path.join(ROOT, "zorbit", "studio_ui", page), encoding="utf-8") as f:
        html = f.read()
    assert "app.js" in html
    assert 0 < html.index('src="mode.js"') < html.index('src="app.js"')
