"""ZOrbit.exe --selftest: does this build have everything it needs to start?

Imports the libraries and the app's own modules, then looks for the files that the build bundles. It prints one
line per check and exits with 1 if any of them fails. It opens no window and starts no hotkeys, so it works in
the CI runner. The same checks run from source (python zorbit\\main.py --selftest).

It catches what --check cannot: a module or DLL that PyInstaller left out, or a UI file that did not get
bundled. Those only show when the feature is first used.
"""
import glob
import importlib
import os

import paths

LIBRARIES = ("webview", "clr")
MODULES = ("radiald", "ring", "popout", "studio", "webapi", "assets", "brushes", "zbp", "config", "tags", "usage",
           "expand", "installs", "onboarding", "zscript_bridge", "winframe", "webview2", "profiles",
           "changelog", "theme", "zbrush_colors")


def _import(name: str) -> str | None:
    """None when the import works, otherwise what went wrong. pythonnet raises more than ImportError."""
    try:
        importlib.import_module(name)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _files() -> list[tuple[str, str]]:
    return [
        ("ui/index.html", os.path.join(paths.UI_DIR, "index.html")),
        ("ui/app.js", os.path.join(paths.UI_DIR, "app.js")),
        ("ui/look.js", os.path.join(paths.UI_DIR, "look.js")),
        ("ui/mode.js", os.path.join(paths.UI_DIR, "mode.js")),
        ("ui/look-screen.js", os.path.join(paths.UI_DIR, "look-screen.js")),
        ("ui/tagfilter.js", os.path.join(paths.UI_DIR, "tagfilter.js")),
        ("ui/slots.js", os.path.join(paths.UI_DIR, "slots.js")),
        ("ui/styles.css", os.path.join(paths.UI_DIR, "styles.css")),
        ("ui/popout.html", os.path.join(paths.UI_DIR, "popout.html")),
        ("default menus", paths.DEFAULT_MENUS),
        ("CHANGELOG.md", paths.CHANGELOG),
        ("icon", paths.ICON),
        ("browser icon", paths.BROWSER_ICON),
    ]


def _webview2_loader() -> str | None:
    """The WebView2 loader DLL that pywebview ships, or None. It sits in webview\\lib\\runtimes\\<arch>\\native."""
    try:
        import webview
    except Exception:
        return None
    folder = os.path.dirname(os.path.abspath(webview.__file__))
    for pattern in ("lib/**/WebView2Loader.dll", "lib/**/*WebView2*.dll"):
        hits = sorted(glob.glob(os.path.join(folder, pattern), recursive=True))
        if hits:
            return hits[0]
    return None


def run() -> int:
    failed = 0

    def report(label: str, problem: str | None, detail: str = "") -> None:
        nonlocal failed
        if problem:
            failed += 1
            print(f"FAIL  {label}: {problem}")
        else:
            print(f"ok    {label}" + (f" ({detail})" if detail else ""))

    for name in LIBRARIES + MODULES:
        report(f"import {name}", _import(name))

    for label, path in _files():
        report(label, None if os.path.isfile(path) else f"missing: {path}")

    bridge = None
    try:
        import zscript_bridge
        bridge = zscript_bridge.bundled()
    except Exception as exc:
        report("zscript bridge", f"{type(exc).__name__}: {exc}")
    else:
        report("zscript bridge", None if bridge else f"not bundled (looked in {paths.ZSCRIPT_DIR})")

    try:
        import changelog
        sections = len(changelog.sections(changelog.read()))
    except Exception as exc:
        report("changelog sections", f"{type(exc).__name__}: {exc}")
    else:
        report("changelog sections", None if sections else "no ## [version] section in CHANGELOG.md",
               f"{sections} found")

    loader = _webview2_loader()
    report("webview2 loader dll", None if loader else "WebView2Loader.dll not found in the webview package")

    print(f"selftest: {'FAILED, ' + str(failed) + ' check(s)' if failed else 'all checks passed'}"
          f" (ZOrbit {paths.VERSION}{', frozen' if paths.FROZEN else ', source'})")
    return 1 if failed else 0
