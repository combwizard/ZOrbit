"""ZOrbit: single entry point (also the PyInstaller entry).

  ZOrbit.exe                     background app: hotkeys, ring, hand-off to ZBrush, tray icon
  ZOrbit.exe --exit-with-zbrush  same, quitting when ZBrush closes (how the ZBrush bridge starts it)
  ZOrbit.exe --studio            ZOrbit Studio: menu editor, brush library, settings
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


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("--zscript-copy", "--zscript-remove"):
        import zscript_bridge             # elevated helper: touches nothing but those files
        return zscript_bridge.elevated_main(args)
    paths.write_launch_file()
    if "--studio" in args:
        import studio
        return studio.main()
    import radiald
    return radiald.main(args)


if __name__ == "__main__":
    sys.exit(main())
