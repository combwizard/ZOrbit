# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Studio asks before closing with unsaved changes, and lists them by area (menus, items, appearance,
  bridge) with Save and close, Close without saving, and Keep editing.
- Settings has an "On this page" column that jumps to each section and highlights the one you are reading.
- The joke Licence screen can be hidden: Settings > Studio, or the link at the bottom of that screen.

### Fixed
- Opening a dialog closes any open dropdown, so it no longer covers the dialog.

### Removed
- The obsolete "Python for the ZBrush bridge" setting (the bridge reads launch.json instead).

## [0.2.0] - 2026-10-26

First public release.

### Added

- A radial menu for ZBrush 2026 and newer: press a hotkey (Q by default) over ZBrush, then hold and release
  over a slot, or tap and click.
- Item types: select a brush, press any ZBrush button, set a slider, toggle a switch, run several of those
  as steps, or open a submenu.
- Radial Menu Studio, a desktop editor with four screens: Menus (live ring preview, drag and drop, hotkey
  recorder, undo and redo), Library (searchable brush browser with thumbnails), Settings, and Status.
- Twelve open animations, plus settings for ring radius, slot size, dead zone, labels, colours, tap time and
  auto-close.
- A ZBrush plugin (the bridge) with a **Zplugin > Radial Menu** palette: Studio, Apply, Start App and Status.
- Picks are delivered to ZBrush by a window message to a listener inside ZBrush, with an optional fallback
  key. Picks wait for the end of a stroke.
- The app starts with ZBrush and exits when ZBrush closes.
- Per-user installer (no administrator rights) that registers the plugin folder in `ZBRUSH_PLUGIN_PATH` and
  adds a Start menu shortcut. The installer is not code-signed yet.
- Menus and settings in a plain JSON file, `%APPDATA%\RadialMenu\radial.json`, with a starter set that uses
  only brushes included with ZBrush.
- Documentation: README, user guide, third-party notices and contributing guide.

[0.2.0]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.2.0
