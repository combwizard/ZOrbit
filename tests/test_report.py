"""Copy report on Studio's Status screen: the name and folders it hides, what it leaves alone, and the logs it takes."""
import json
import os
import time

import pytest

import report

LOCAL = r"C:\Users\you\AppData\Local"
HOME = r"C:\Users\you"


@pytest.fixture
def clean():
    return report.redactor(LOCAL, HOME, ["you", "brush"])


# --- the name and folders -------------------------------------------------------------------------
@pytest.mark.parametrize("text, want", [
    (r"C:\Users\you\AppData\Local\ZOrbit\radiald.log", r"%LOCALAPPDATA%\ZOrbit\radiald.log"),
    (r"C:\Users\you\Documents\x.ztl", r"%USERPROFILE%\Documents\x.ztl"),
    (r"C:\Users\you", "%USERPROFILE%"),
    ("c:/users/YOU/Documents/x", "%USERPROFILE%/Documents/x"),
    (r"open failed: 'C:\\Users\\you\\AppData\\Local\\x'", r"open failed: '%LOCALAPPDATA%\\x'"),
    (r"D:\Art\brush\scene.zpr", r"D:\Art\<user>\scene.zpr"),
    (r"D:\Art\BRUSH\scene.zpr", r"D:\Art\<user>\scene.zpr"),
    (r"D:\Art\brush", r"D:\Art\<user>"),
])
def test_the_name_in_a_path_is_hidden(clean, text, want):
    assert clean(text) == want


def test_the_name_in_a_quoted_command_line_is_hidden(clean):
    line = r'''started app pid 7: "C:\Users\you\app\ZOrbit.exe" --profile "brush" --who brush'''
    assert clean(line) == r'''started app pid 7: "%USERPROFILE%\app\ZOrbit.exe" --profile "<user>" --who <user>'''


@pytest.mark.parametrize("text", [
    "brush Clay: selected",
    "pick #3 'brush' -> listener 500 (posted=True)",
    "press Tool:brush:Thing: ok",
    "Brush:Clay",
    "the paintbrush and the brushes",
])
def test_a_name_that_is_also_an_ordinary_word_stays(clean, text):
    assert clean(text) == text


@pytest.mark.parametrize("text", [r"D:\Art\brushy\x", r"D:\Art\brush.old\x", r"D:\Art\brush-2\x", r"D:\brushes\x"])
def test_a_longer_folder_name_is_not_taken_for_the_name(clean, text):
    assert clean(text) == text


def test_a_longer_folder_name_is_not_taken_for_the_home_folder():
    clean = report.redactor(None, r"D:\Home\you", [])
    for text in (r"D:\Home\youth\x", r"D:\Home\you.old\x", r"D:\Home\you-2\x"):
        assert clean(text) == text


def test_only_a_line_that_runs_something_counts_as_a_command_line(clean):
    text = "brush Clay: selected\nrun C:\\x\\ZOrbit.exe --who brush\nbrush Rock: selected"
    assert clean(text) == "brush Clay: selected\nrun C:\\x\\ZOrbit.exe --who <user>\nbrush Rock: selected"


def test_a_program_named_like_the_user_keeps_its_name():
    clean = report.redactor(None, r"D:\Home\zbrush", ["zbrush"])
    assert clean(r"process is zbrush.exe") == "process is zbrush.exe"


def test_the_longest_folder_goes_first_whichever_way_they_are_given():
    clean = report.redactor(LOCAL, HOME, [])
    assert clean(r"C:\Users\you\AppData\Local\x C:\Users\you\y") == r"%LOCALAPPDATA%\x %USERPROFILE%\y"
    clean = report.redactor(r"D:\L", r"D:\L\brush", [])
    assert clean(r"D:\L\brush\y D:\L\x") == r"%USERPROFILE%\y %LOCALAPPDATA%\x"


# The short names on the right are ones Windows gave these folder names (GetShortPathNameW).
@pytest.mark.parametrize("name, short", [("brushmaster", "BRUSHM~1"), ("John Smith", "JOHNSM~1"), ("Crème", "CRME~1"),
                                         ("Łukasz Nowak", "UKASZN~1"), ("john.smith", "JOHN~1.SMI")])
def test_the_short_form_of_a_name_is_hidden(name, short):
    clean = report.redactor(None, None, [name])
    assert clean(f"ShellExecute: C:\\Users\\{short}\\AppData\\x") == r"ShellExecute: C:\Users\<user>\AppData\x"
    assert clean(f"C:\\Users\\{short}") == r"C:\Users\<user>"


def test_the_short_name_windows_keeps_is_found_and_hidden(tmp_path):
    folder = tmp_path / "John Smith with a long name"
    folder.mkdir()
    short = report.short_name(folder)
    if not short:
        pytest.skip("this volume keeps no 8.3 names")
    assert "~" in short and report.redactor(None, None, [short])(f"D:\\{short}\\x") == r"D:\<user>\x"
    assert report.short_name(tmp_path / "missing") == ""


def test_a_name_with_no_ascii_only_has_the_short_name_windows_gives_it():
    clean = report.redactor(None, None, ["Дмитрий", "5F3A~1"])
    assert clean(r"D:\Home\Дмитрий\x D:\Home\5F3A~1\y") == r"D:\Home\<user>\x D:\Home\<user>\y"


def test_a_path_at_the_end_of_a_sentence_is_still_hidden(clean):
    assert clean("no access to C:\\Users\\you.") == "no access to %USERPROFILE%."
    assert clean("no access to D:\\Art\\brush.") == "no access to D:\\Art\\<user>."


def test_a_name_in_a_file_url_or_an_escaped_form_is_hidden():
    clean = report.redactor(None, None, report.user_names(env={"USERNAME": "John Smith"}, home=""))
    assert clean("file:///C:/Users/John%20Smith/x") == "file:///C:/Users/<user>/x"
    clean = report.redactor(None, None, report.user_names(env={"USERNAME": "Zoë"}, home=""))
    assert clean(r"D:\Zo\xeb\x D:\Zo\u00eb\y") == r"D:\<user>\x D:\<user>\y"


def test_a_name_with_regex_characters_is_taken_literally():
    clean = report.redactor(None, r"D:\Home\a+b (x)", ["a+b (x)"])
    assert clean(r"D:\Home\a+b (x)\y D:\a+b (x)\z D:\aab x\z") == r"%USERPROFILE%\y D:\<user>\z D:\aab x\z"


def test_the_names_cover_a_renamed_account_and_a_name_outside_ascii():
    names = report.user_names(env={"USERNAME": "Crème"}, home=r"D:\Home\old")
    assert {"Crème", "old", json.dumps("Crème")[1:-1]} <= set(names)
    clean = report.redactor(None, None, names)
    assert clean(r"D:\Crème\x D:\Cr\u00e8me\y D:\old\z") == r"D:\<user>\x D:\<user>\y D:\<user>\z"


def test_a_missing_folder_or_empty_name_changes_nothing():
    assert report.user_names(env={}, home="") == []
    assert report.redactor(None, None, [])(r"D:\Home\x") == r"D:\Home\x"


def test_the_whole_report_is_cleaned(clean):
    out = report.build([("Install", r"D:\Art\brush\ZBrush")], [("log", [r"C:\Users\you\x"])], clean)
    assert "brush" not in out
    assert "D:\\Art\\<user>\\ZBrush" in out and "%USERPROFILE%\\x" in out


# --- the logs -------------------------------------------------------------------------------------
def test_a_log_is_cut_to_the_current_session():
    lines = [f"old {i}" for i in range(50)] + ["ZOrbit starting (pid 1)"] + [f"new {i}" for i in range(40)]
    assert report.this_session(lines, report.SESSION_MARKS["radiald.log"]) == lines[50:]


def test_a_short_session_keeps_the_lines_before_it():
    lines = [f"old {i}" for i in range(50)] + ["ZOrbit starting (pid 1)", "new"]
    assert report.this_session(lines, report.SESSION_MARKS["radiald.log"]) == lines[-report.MIN_LINES:]


def test_a_log_without_a_mark_is_left_whole():
    assert report.this_session(["a", "b"], None) == ["a", "b"]
    assert report.this_session(["a", "b"], "nothing like this") == ["a", "b"]


def test_the_caps_keep_the_newest_lines():
    assert report.trim([str(i) for i in range(500)]) == [str(i) for i in range(400, 500)]
    kept = report.trim(["x" * 900] * 50)
    assert sum(len(l) + 1 for l in kept) <= report.LOG_CHARS
    assert report.trim(["y" * 5000]) == ["y" * report.LINE_CHARS]


def test_every_log_at_its_cap_still_fits_an_issue(tmp_path):
    for name in report.log_names(True, True, 0):
        (tmp_path / name).write_text("\n".join(["z" * 900] * 200), encoding="utf-8")
    os.utime(tmp_path / "app_stderr.log")
    sections = report.log_sections(str(tmp_path), True, True, lambda t: t)
    assert len(report.build([("a", "b")] * 20, sections, lambda t: t)) < 65536


@pytest.mark.parametrize("modern, legacy, has, lacks", [
    (True, False, ["bridge.log"], ["zscript_bridge.log", "zscript_hotkey.log", "zscript_launch.log"]),
    (False, True, ["zscript_bridge.log", "zscript_hotkey.log", "zscript_launch.log"], ["bridge.log"]),
    (True, True, ["bridge.log", "zscript_bridge.log"], []),
    (False, False, ["bridge.log", "zscript_bridge.log"], []),
])
def test_the_logs_fit_the_setup(modern, legacy, has, lacks):
    names = report.log_names(modern, legacy)
    assert names[0] == "radiald.log" and "popout.log" in names and "studio.log" in names
    assert all(n in names for n in has) and not any(n in names for n in lacks)


def test_app_stderr_only_when_it_is_recent():
    assert "app_stderr.log" in report.log_names(True, False, 60)
    assert "app_stderr.log" not in report.log_names(True, False, report.STDERR_RECENT_S + 1)
    assert "app_stderr.log" not in report.log_names(True, False, None)


def test_old_app_stderr_stays_out_by_its_file_time(tmp_path):
    p = tmp_path / "app_stderr.log"
    p.write_text("boom")
    os.utime(p, (time.time() - 2 * report.STDERR_RECENT_S,) * 2)
    assert "app_stderr.log" not in [h for h, _ in report.log_sections(str(tmp_path), True, False, lambda t: t)]
    os.utime(p)
    assert "app_stderr.log" in [h for h, _ in report.log_sections(str(tmp_path), True, False, lambda t: t)]


def test_a_zscript_log_in_the_ansi_code_page_has_its_name_hidden(tmp_path):
    (tmp_path / "zscript_launch.log").write_bytes(r"ShellExecute: D:\Crème\ZOrbit.exe".encode("mbcs"))
    clean = report.redactor(None, None, ["Crème"])
    got = dict(report.log_sections(str(tmp_path), False, True, clean))["zscript_launch.log"]
    assert got == [r"ShellExecute: D:\<user>\ZOrbit.exe"]


def test_a_cut_cannot_leave_the_start_of_a_name_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "LINE_CHARS", 20)
    (tmp_path / "radiald.log").write_text("D:\\aaaaaaaaaaaaaa\\brushmaster\\x\n", encoding="utf-8")
    clean = report.redactor(None, None, ["brushmaster"])
    got = dict(report.log_sections(str(tmp_path), True, False, clean))["radiald.log"]
    assert got == ["D:\\aaaaaaaaaaaaaa\\<u"]


def test_a_log_with_nothing_to_show_says_so(tmp_path):
    (tmp_path / "radiald.log").write_text("")
    got = dict(report.log_sections(str(tmp_path), True, False, lambda t: t))
    assert got["radiald.log"] == ["(empty)"] and got["bridge.log"] == ["(no such file)"]


def test_a_cut_at_the_read_limit_drops_the_half_line(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "TAIL_BYTES", 10)
    p = tmp_path / "x.log"
    p.write_bytes("Crème one\ntwo\nthree\n".encode("utf-8"))
    assert report.read_log(str(p)) == ["three"]
    assert report.read_log(str(tmp_path / "missing.log")) is None


# --- the rest -------------------------------------------------------------------------------------
INSTALLS = [{"name": "ZBrush 2023", "path": r"C:\Program Files\Pixologic\ZBrush 2023", "python": False},
            {"name": "ZBrush 2026", "path": r"C:\Program Files\Maxon\ZBrush 2026", "python": True}]


def test_each_zbrush_says_whether_it_runs_and_as_what():
    procs = [{"pid": 9, "path": r"c:\program files\maxon\zbrush 2026", "admin": "no"}]
    assert report.zbrush_lines(INSTALLS, procs) == [
        r"ZBrush 2023 (2022 to 2025): C:\Program Files\Pixologic\ZBrush 2023: not running",
        r"ZBrush 2026 (2026 and newer): C:\Program Files\Maxon\ZBrush 2026: running as pid 9, administrator: no"]


def test_a_zbrush_that_cannot_be_placed_is_still_listed():
    assert report.zbrush_lines([], [{"pid": 4, "path": None, "admin": "yes"}]) == [
        "A ZBrush outside the list: pid 4, administrator: yes"]
    assert report.zbrush_lines([], []) == ["none found"]


def test_the_bug_form_link_fills_in_the_versions():
    url = report.bug_url("0.18.1", "2026", "Windows 11 (build 26200)")
    assert url == ("https://github.com/combwizard/zorbit/issues/new?template=bug_report.yml&zorbit=0.18.1&zbrush=2026"
                   "&windows=Windows+11+%28build+26200%29")
    assert "zbrush=" not in report.bug_url("0.18.1", None, "")


def test_the_library_folders_are_listed_per_kind():
    rows = {"brush": [{"path": r"D:\Lib\Brushes", "exists": True, "count": 330, "hidden": 2, "error": None},
                      {"path": r"D:\Lib\More", "exists": True, "count": 0, "hidden": 0, "error": None}],
            "alpha": [{"path": r"D:\Gone", "exists": False, "count": None, "hidden": None, "error": None}],
            "material": [{"path": r"E:\Unplugged", "exists": True, "count": None, "hidden": None,
                          "error": "drive not ready"}],
            "texture": [{"path": r"D:\Tex", "exists": True, "count": None, "hidden": None, "error": None}]}
    assert report.library_folder_lines(rows) == [
        r"Brushes: D:\Lib\Brushes: found, 330 files, 2 hidden",
        r"Brushes: D:\Lib\More: found, 0 files",
        r"Alphas: D:\Gone: missing",
        r"Materials: E:\Unplugged: could not be read: drive not ready",
        r"Textures: D:\Tex: found"]


def test_no_library_folders_say_none_added():
    none = {k: [] for k in ("brush", "alpha", "material", "texture")}
    assert report.library_folder_lines(none) == [
        "Brushes: none added", "Alphas: none added", "Materials: none added", "Textures: none added"]
    assert report.library_folder_lines({}) == report.library_folder_lines(none)
