# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Studio checks GitHub for a newer release when it opens and shows it at the top, next to the current
  version with an orange dot; clicking it opens that release's page. Settings > Studio > Check for updates
  turns this off, and no request is made while it is off.
- The version at the top of Studio links to its release notes.

## [0.5.1] - 2026-10-27

### Fixed
- A new or changed menu hotkey works as soon as the menus are saved. Before, the app only re-read the menus
  when a ring opened, so a new hotkey did nothing until one of the old hotkeys had been pressed.
- In a ring with one to three slots, a slot no longer answers to every direction. Each slot covers at most a
  quarter of the circle, so with one slot, moving or flicking away from it picks nothing.

## [0.5.0] - 2026-10-27

### Added
- Flick to pick: moving the cursor out past a slot picks it at once, without releasing the hotkey or clicking.
  On by default; `ring.flick` or Settings > Behaviour > Flick to pick.
- Submenus open as soon as the cursor reaches their slot, centred on that slot. While the hotkey is still held
  they stay in hold-and-release mode, so releasing over an item or flicking past it picks it, and releasing
  in the middle keeps the submenu open for a click. On by default; `ring.hover_submenus` or Settings >
  Behaviour > Open submenus on hover.

## [0.4.0] - 2026-10-27

### Added
- Support for ZBrush 2022 to 2025. They have no Python API, so they get a ZScript plugin with the same
  Zplugin > Radial Menu palette. It has no listener, so picks there always go through the bridge key.
- Studio's Settings has an Older ZBrush section that lists the 2022 to 2025 versions it finds, with Install,
  Update and Remove for each and a way to add a ZBrush folder it missed. It asks for administrator rights only
  for a ZBrush under Program Files. A badge on Settings shows when an installed plugin needs updating.
- In ZBrush 2022 to 2025 brushes load from that version's own files, and the brush library also works on a
  computer that only has one of those versions.
- `studio.log`, and the app's start lines in `radiald.log`, record which program started them and how long
  starting took.

### Changed
- The ZBrush 2026 plugin also clears the copy of each pick meant for the ZScript plugin (`request.txt`).

## [0.3.0] - 2026-10-26

### Added
- Studio asks before closing with unsaved changes, and lists them by area (menus, items, appearance,
  bridge) with Save and close, Close without saving, and Keep editing.
- Each menu and submenu can have its own open animation (`"animation"` on the menu, or Open animation in its
  menu settings in Studio). Menus without one use the animation from Settings.
- Studio remembers its window size, position and maximised state between sessions. If that screen is gone,
  the window opens centred on the nearest one.
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

[0.5.1]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.5.1
[0.5.0]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.5.0
[0.4.0]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.4.0
[0.3.0]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.3.0
[0.2.0]: https://github.com/combwizard/zbrush-radial-menu/releases/tag/v0.2.0
