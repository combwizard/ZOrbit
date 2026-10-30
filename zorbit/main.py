"""ZOrbit: single entry point (also the PyInstaller entry).

  ZOrbit.exe                     background app: hotkeys, ring, hand-off to ZBrush, tray icon
  ZOrbit.exe --exit-with-zbrush  same, quitting when ZBrush closes (how the ZBrush bridge starts it)
  ZOrbit.exe --studio            ZOrbit Studio: menu editor, brush library, settings
  ZOrbit.exe --popout [--managed] [--show] [--tag KEY] [--kind KIND] [--zbrush-hwnd N]
                                     the browser (the app starts it; --managed: quits with the app unless its
                                     window is up, --show: open at once, --tag: filtered to a tag, --kind: on
                                     the brush, alpha, material or texture tab)
  ZOrbit.exe --check             validate the menus file and print it
  ZOrbit.exe --zscript-copy|--zscript-remove <stage> <dest>
                                     internal: the Studio runs this as administrator to put the ZScript
                                     bridge into (or take it out of) a ZBrush 2022-2025 under Program Files

From source: python zorbit/main.py [same arguments]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402


def unblock_bundle() -> None:
    """Remove the Mark of the Web that Windows copies onto every file unzipped from the downloaded portable zip.
    .NET Framework refuses a marked Python.Runtime.dll, so pythonnet (and with it the Studio and the brush
    browser) fails at startup with "Failed to resolve Python.Runtime.Loader.Initialize"."""
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return
    for dirpath, _, filenames in os.walk(sys._MEIPASS):
        for name in filenames:
            if name.lower().endswith(".dll"):
                try:
                    os.remove(os.path.join(dirpath, name) + ":Zone.Identifier")
                except OSError:           # not marked, or a folder we cannot write to
                    pass


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("--zscript-copy", "--zscript-remove"):
        import zscript_bridge             # elevated helper: touches nothing but those files
        return zscript_bridge.elevated_main(args)
    unblock_bundle()
    paths.write_launch_file()
    if "--studio" in args:
        import studio
        return studio.main()
    if "--popout" in args:
        import popout
        return popout.main(args)
    import radiald
    return radiald.main(args)


if __name__ == "__main__":
    sys.exit(main())
