"""--selftest: the checks that run on the built exe also pass from source, and fail when something is missing."""
import pytest

pytest.importorskip("webview", reason="pywebview is not installed")
pytest.importorskip("clr", reason="pythonnet is not installed")

import paths  # noqa: E402
import selftest  # noqa: E402


def test_selftest_passes_from_source(capsys):
    code = selftest.run()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "FAIL" not in out
    assert "import webview" in out and "webview2 loader dll" in out


def test_selftest_fails_on_a_missing_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(paths, "ICON", str(tmp_path / "no-such-icon.ico"))
    assert selftest.run() == 1
    out = capsys.readouterr().out
    assert "FAIL  icon: missing" in out
    assert "FAILED, 1 check(s)" in out


def test_selftest_fails_on_a_missing_module(monkeypatch, capsys):
    monkeypatch.setattr(selftest, "MODULES", selftest.MODULES + ("zorbit_no_such_module",))
    assert selftest.run() == 1
    assert "FAIL  import zorbit_no_such_module" in capsys.readouterr().out
