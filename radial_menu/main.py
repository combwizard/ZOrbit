"""Radial Menu for ZBrush: single entry point (also the PyInstaller entry).

  RadialMenu.exe                     background app: hotkeys, ring, hand-off to ZBrush, tray icon
  RadialMenu.exe --exit-with-zbrush  same, quitting when ZBrush closes (how the ZBrush bridge starts it)
  RadialMenu.exe --studio            Radial Menu Studio: menu editor, brush library, settings
  RadialMenu.exe --check             validate the menus file and print it

From source: python radial_menu/main.py [same arguments]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    paths.write_launch_file()
    if "--studio" in args:
        import studio
        return studio.main()
    import radiald
    return radiald.main(args)


if __name__ == "__main__":
    sys.exit(main())
