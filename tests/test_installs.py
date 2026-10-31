"""installs.py: finding ZBrush installations and the year filter."""
import os

import pytest

import installs


def zbrush(root, name, python=False):
    d = root / name
    d.mkdir(parents=True)
    (d / "ZBrush.exe").write_bytes(b"")
    if python:
        (d / "python311.dll").write_bytes(b"")
    return str(d)


def no_sources(monkeypatch, registry=(), appdata=(), folders=()):
    monkeypatch.setattr(installs, "_from_registry", lambda: iter(registry))
    monkeypatch.setattr(installs, "_from_appdata", lambda: iter(appdata))
    monkeypatch.setattr(installs, "_from_folders", lambda: iter(folders))


def test_entry_reads_year_from_the_folder_name(tmp_path):
    e = installs.entry(zbrush(tmp_path, "ZBrush 2024"))
    assert e == {"name": "ZBrush 2024", "year": 2024, "path": os.path.normpath(str(tmp_path / "ZBrush 2024")),
                 "python": False, "supported": True}


def test_entry_prefers_the_hint_and_strips_quotes(tmp_path):
    d = zbrush(tmp_path, "Maxon ZBrush")
    e = installs.entry(f'  "{d}"  ', "Maxon ZBrush 2026")
    assert e["year"] == 2026 and e["name"] == "ZBrush 2026"


def test_entry_without_a_year_keeps_the_folder_name(tmp_path):
    e = installs.entry(zbrush(tmp_path, "Z"))
    assert e["year"] is None and e["name"] == "Z" and e["supported"] is True


def test_entry_none_without_zbrush_exe(tmp_path):
    (tmp_path / "ZBrush 2024").mkdir()
    assert installs.entry(str(tmp_path / "ZBrush 2024")) is None


def test_entry_python_api_follows_the_dll(tmp_path):
    assert installs.entry(zbrush(tmp_path, "ZBrush 2026", python=True))["python"] is True


@pytest.mark.parametrize("year, supported", [(2020, False), (2021, False), (2022, True), (2025, True), (2026, True)])
def test_year_filter(tmp_path, year, supported):
    assert installs.entry(zbrush(tmp_path, f"ZBrush {year}"))["supported"] is supported


def test_find_installs_keeps_unsupported_and_sorts_by_year(tmp_path, monkeypatch):
    new = zbrush(tmp_path, "ZBrush 2026", True)
    old = zbrush(tmp_path, "ZBrush 2021")
    mid = zbrush(tmp_path, "ZBrush 2024")
    no_sources(monkeypatch, folders=[(new, "ZBrush 2026"), (old, "ZBrush 2021"), (mid, "ZBrush 2024")])
    found = installs.find_installs()
    assert [(e["year"], e["supported"]) for e in found] == [(2021, False), (2024, True), (2026, True)]


def test_find_installs_merges_sources_and_prefers_a_known_year(tmp_path, monkeypatch):
    d = zbrush(tmp_path, "Z")
    other = zbrush(tmp_path, "ZBrush 2025")
    no_sources(monkeypatch, registry=[(d, "")], appdata=[(d, "Maxon ZBrush 2023"), (other, "")],
               folders=[(other, "ZBrush 2025"), (str(tmp_path / "missing"), "ZBrush 2022")])
    found = installs.find_installs()
    assert [e["year"] for e in found] == [2023, 2025]      # the same folder from two sources counts once


def test_find_installs_survives_a_failing_source(tmp_path, monkeypatch):
    d = zbrush(tmp_path, "ZBrush 2024")

    def broken():
        raise OSError("registry")
        yield
    monkeypatch.setattr(installs, "_from_registry", broken)
    monkeypatch.setattr(installs, "_from_appdata", lambda: iter([(d, "ZBrush 2024")]))
    monkeypatch.setattr(installs, "_from_folders", lambda: iter([]))
    assert [e["year"] for e in installs.find_installs()] == [2024]


def test_install_of_a_running_exe(tmp_path):
    d = zbrush(tmp_path, "ZBrush 2023")
    assert installs.install_of(os.path.join(d, "ZBrush.exe"))["year"] == 2023
    assert installs.install_of("") is None
    assert installs.install_of(str(tmp_path / "nowhere" / "ZBrush.exe")) is None


def test_install_of_takes_the_year_from_the_scan_when_the_folder_has_none(tmp_path, monkeypatch):
    d = zbrush(tmp_path, "Z")
    no_sources(monkeypatch, registry=[(d, "ZBrush 2022")])
    e = installs.install_of(os.path.join(d, "ZBrush.exe"))
    assert e["year"] == 2022 and e["supported"] is True
