"""The app copying the ZScript plugin's result (zscript_bridge.log keeps only the last pick) into radiald.log, and
the caps that keep the app's logs from growing without end."""
import os
import types

import pytest

import radiald


@pytest.fixture
def zlog(tmp_path):
    path = tmp_path / "zscript_bridge.log"

    def write(text):
        path.write_bytes(text.encode("mbcs"))
        return str(path)
    return path, write


# --- reading the line ----------------------------------------------------------------------------
def test_the_line_for_the_pick_is_returned_without_its_number(zlog):
    path, write = zlog
    write("#4 'Alpha 007': alpha Alpha 007: selected\n")
    before = path.read_bytes()
    write("#5 'Bumpy Skin2': alpha Bumpy Skin2: loaded from file\n")
    assert radiald._zscript_result(5, before, str(path)) == "'Bumpy Skin2': alpha Bumpy Skin2: loaded from file"


def test_an_unchanged_file_is_from_an_earlier_run(zlog):
    # Numbers start again with every run of the app: "#1" left from yesterday is not today's pick 1.
    path, write = zlog
    write("#1 'Clay': brush Clay: selected\n")
    assert radiald._zscript_result(1, path.read_bytes(), str(path)) is None


def test_another_picks_line_or_no_file_is_not_an_answer(zlog, tmp_path):
    path, write = zlog
    write("#6 'X': brush X: selected\n")
    assert radiald._zscript_result(7, b"", str(path)) is None
    assert radiald._zscript_result(1, None, str(tmp_path / "missing.log")) is None


def test_a_name_in_the_windows_code_page_reads_back(zlog):
    path, write = zlog
    write("#2 'Crème': brush Crème: selected\n")
    assert radiald._zscript_result(2, None, str(path)) == "'Crème': brush Crème: selected"


# --- the timer -----------------------------------------------------------------------------------
@pytest.fixture
def app(monkeypatch, zlog):
    path, write = zlog
    lines, timers = [], []
    monkeypatch.setattr(radiald, "ZSCRIPT_LOG", str(path))
    monkeypatch.setattr(radiald, "log", lines.append)
    monkeypatch.setattr(radiald.W, "SetTimer", lambda *a: timers.append("set"))
    monkeypatch.setattr(radiald.W, "KillTimer", lambda *a: timers.append("kill"))
    a = types.SimpleNamespace(ctrl=None, _zs_result=None, toasts=[])
    a._toast = a.toasts.append
    a._zs_result_tick = lambda final=False: radiald.App._zs_result_tick(a, final)
    a._watch_zscript_result = lambda seq, before: radiald.App._watch_zscript_result(a, seq, before)
    return a, write, lines, timers


def test_the_result_is_logged_once_it_appears(app):
    a, write, lines, timers = app
    before = radiald._read_bytes(write("#3 'Old': brush Old: selected\n"))
    a._watch_zscript_result(4, before)
    a._zs_result_tick()
    assert lines == [] and a._zs_result is not None          # nothing yet: keep looking
    write("#4 'GIO': brush GIO: selected (Edit mode is off)\n")
    a._zs_result_tick()
    assert lines == ["pick #4 result: 'GIO': brush GIO: selected (Edit mode is off)"]
    assert a._zs_result is None and timers == ["set", "kill"]


def test_no_result_in_time_is_logged_as_such(app, monkeypatch):
    a, write, lines, timers = app
    a._watch_zscript_result(8, radiald._read_bytes(write("#7 'A': brush A: selected\n")))
    a._zs_result[2] = 0                                       # the time is up
    a._zs_result_tick()
    assert len(lines) == 1 and lines[0].startswith("pick #8: the ZScript plugin wrote no result in")
    assert "macro" in lines[0] and a._zs_result is None


def test_a_new_pick_closes_the_one_still_waiting(app):
    a, write, lines, timers = app
    a._watch_zscript_result(1, radiald._read_bytes(write("#9 'Z': x\n")))
    a._watch_zscript_result(2, radiald._read_bytes(write("#9 'Z': x\n")))
    assert lines == ["pick #1: the ZScript plugin wrote no result (a macro ends its script before it can; "
                     "otherwise the bridge key did not reach Apply)"]
    assert a._zs_result[0] == 2


# --- log sizes -----------------------------------------------------------------------------------
def test_the_app_log_is_cut_back_to_its_last_half(monkeypatch, tmp_path):
    log = tmp_path / "radiald.log"
    log.write_bytes(b"a" * 900 + b"b" * 300)
    monkeypatch.setattr(radiald, "LOG_FILE", str(log))
    radiald._trim_log(max_bytes=1000)
    assert log.read_bytes() == b"a" * 200 + b"b" * 300
    radiald._trim_log(max_bytes=1000)                          # under the cap: left alone
    assert os.path.getsize(log) == 500


# --- what the user is told ------------------------------------------------------------------------
@pytest.mark.parametrize("line, toast", [
    ("#4 'Alpha 012': alpha Alpha 012: NOT loaded in ZBrush and no file known", "Alpha 012 could not be found in ZBrush"),
    ("#4 'ZModeler': brush ZModeler: NOT loaded in ZBrush and no file known", "ZModeler could not be found in ZBrush"),
    ("#4 'Off': brush Off: NOT loaded in ZBrush and no file known (Edit mode is off)",
     "Off could not be found in ZBrush"),
    ("#4 'Mat': material Mat: NOT loaded in ZBrush and no file known", "Mat could not be found in ZBrush"),
    ("#4 'Tex': texture Tex: NOT loaded in ZBrush and no file known", "Tex could not be found in ZBrush"),
    ("#4 'Edit': press Tool:Nope: no such interface item", "Tool:Nope is not a ZBrush button"),
    ("#4 'Bob's': alpha Bob's: NOT loaded in ZBrush and no file known", "Bob's could not be found in ZBrush"),
])
def test_a_pick_that_could_not_load_says_so(app, line, toast):
    a, write, lines, _ = app
    a._watch_zscript_result(4, None)
    write(line + "\n")
    a._zs_result_tick()
    assert a.toasts == [toast]
    assert lines == ["pick #4 result: " + line[len("#4 "):]]


def test_only_the_first_problem_of_several_steps_is_shown(app):
    a, write, _, _ = app
    a._watch_zscript_result(4, None)
    write("#4 'Two': alpha A: selected; alpha B: NOT loaded in ZBrush and no file known; "
          "press X:Y: no such interface item\n")
    a._zs_result_tick()
    assert a.toasts == ["B could not be found in ZBrush"]


@pytest.mark.parametrize("result", ["brush GIO: selected (Edit mode is off)", "alpha A: loaded from file",
                                    "set X:Y = 1: ok", "nothing to do"])
def test_a_pick_that_worked_shows_nothing(app, result):
    a, write, _, _ = app
    a._watch_zscript_result(4, None)
    write(f"#4 'Fine': {result}\n")
    a._zs_result_tick()
    assert a.toasts == []


def test_no_result_shows_nothing(app):
    a, _, _, _ = app
    a._watch_zscript_result(4, None)
    a._zs_result_tick(final=True)
    assert a.toasts == []
