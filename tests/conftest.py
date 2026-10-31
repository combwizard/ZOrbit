"""Shared test setup.

paths.py works out DATA_DIR and CONFIG_DIR from %APPDATA% and %LOCALAPPDATA% when it is first imported, so the
two variables are pointed at a throw-away folder here, before any zorbit module is imported. A test run never
touches the real %APPDATA%\\ZOrbit.
"""
import atexit
import json
import os
import shutil
import tempfile

import pytest

_SANDBOX = tempfile.mkdtemp(prefix="zorbit-tests-")
os.environ["APPDATA"] = os.path.join(_SANDBOX, "Roaming")
os.environ["LOCALAPPDATA"] = os.path.join(_SANDBOX, "Local")
os.environ["ZORBIT_TAGS_FILE"] = os.path.join(_SANDBOX, "Roaming", "ZOrbit", "tags.json")
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def sandboxed_paths():
    """Fails the whole run if paths.py somehow points outside the sandbox."""
    import paths
    assert os.path.commonpath([paths.CONFIG_DIR, _SANDBOX]) == _SANDBOX
    assert os.path.commonpath([paths.DATA_DIR, _SANDBOX]) == _SANDBOX
    return _SANDBOX


@pytest.fixture
def write_json(tmp_path):
    """write_json(data, name="file.json") -> path. Writes data as JSON (a str is written as it is)."""
    def write(data, name="file.json", encoding="utf-8"):
        path = tmp_path / name
        text = data if isinstance(data, str) else json.dumps(data)
        path.write_bytes(text.encode(encoding))
        return str(path)
    return write


@pytest.fixture
def radial_file(write_json):
    """radial_file(raw) -> path of a radial.json holding raw (a dict, or text)."""
    def write(raw):
        return write_json(raw, "radial.json")
    return write


@pytest.fixture
def tags_file(write_json):
    """tags_file(raw) -> path of a tags.json holding raw (a dict, or text)."""
    def write(raw):
        return write_json(raw, "tags.json")
    return write


@pytest.fixture
def usage_file(write_json):
    """usage_file(raw) -> path of a usage.json holding raw (a dict, or text)."""
    def write(raw):
        return write_json(raw, "usage.json")
    return write
