# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Fan-out submenus. Give a menu `"fan": true`, or switch on **Fan out when opened from another menu** in the
  menu settings in Studio, and it opens as a fan when you reach it from another ring. Its items spread out in
  an arc beyond the submenu's slot, with dashed lines to each one, and the ring you came from stays visible.
  Release over an item, click it or flick past it to pick it. A fan item can be a fan submenu too, up to three
  deep. Moving out of a fan closes it. Near a screen edge, or when a fan would lead back to a menu that is
  already open, it opens as a normal ring instead. A menu's hotkey still opens a ring. A slot that fans out
  has a fan badge, and one that opens a ring keeps the arrow.
- Studio shows an open fan in the ring preview when you hover or select the submenu's slot.
- Tags for brushes. A tag is a label with a colour, and a brush can carry several; the first is its colour cue.
  Select brushes in the Library (or in the brush list on the Menus screen), press **Tag...** or right-click, and
  tick tags in the picker or type a new one. The Library filters by tag chips (a brush shows when it has any
  chosen tag) and by **Untagged**, and cards show up to three colour dots. **Manage tags...** (also
  **Settings > Tags**) renames, recolours from eight presets or any `#rrggbb`, merges a rename that clashes
  with another tag, and deletes with a count of the brushes and ring items affected. Tags save as you go, not
  with Save and Undo, in `%APPDATA%\ZOrbit\tags.json`; new installs start with Blocking and Detailing.
- Tag slots. `{"tag": "blocking"}` opens a fan of every installed brush with that tag, most used first, up to 12
  with a **More...** slot that opens the brush browser on that tag. A tag with no installed brushes, or that no
  longer exists, is a faint slot and a problem is listed for a missing one. Menu ids starting with `tag:` are
  reserved.
- Browser slots. `{"browser": ""}` opens the brush browser; a tag key opens it on that tag.
- Tag colours on the ring. `ring.tag_colors` (`none`, `tint`, `glow` or `both`, default `tint`; Settings > Tag
  colours) shows a brush's first tag on its slot as a coloured rim and tinted disc, a soft halo, or both. The
  hover border, spoke and label take the colour, and a tag slot and its fan always use the tag's colour.
- The brush browser: a window with your brushes, search, folders, tag chips and thumbnails. It is a normal
  window with a taskbar button that you can move, resize, maximise and snap, and it stays open until you close
  it. `browser.hotkey` (Alt+B on new installs; Settings > Brush browser) opens it, brings it to the front, or,
  when it is already in front, hands the keyboard back to ZBrush. It also opens from a Browser slot, the tray
  menu, a button in Studio's Library and Settings, and a Start menu shortcut, and it does not need ZBrush: it
  stays open when ZBrush and the app quit. Type to search, arrows to move, Enter or a double-click to pick, Esc
  to clear and then give ZBrush the keyboard back, and a Keep on top button (on by default). A pick reaches
  ZBrush through the app like a ring pick and counts towards auto slots; in ZBrush 2022 to 2025 it is dropped
  if ZBrush has not got the focus back within 2 seconds. The app starts it hidden in the background when the
  config has a browser hotkey or a Browser slot. Its placement is kept in `popout.json` and its log is
  `popout.log`.
- Tag warnings in the problems panel: a tag or browser filter that does not exist, an unknown `tag_colors`, a
  browser hotkey that a menu already uses (the menu wins) or cannot be read.
- Drag a brush from the brush browser window onto a menu, the ring or the item list in Studio. It is added like a
  drag from the Library, with the same undo step. A drag carries the one brush you pick up, even in a multi-selection.

### Changed
- Studio's ring preview takes drops between slots. While you drag a brush or an item over the ring, a bar marks the gap it will land in and the stage says between which two slots; you can also drag a slot on the ring to reorder it, or onto another menu in the list. While you drag an item, a **Delete** target appears in the corner of the preview: drop it there to remove the item (Undo brings it back).
- In the Library and the brush list on the Menus screen, Ctrl-click and Shift-click now select several brushes,
  and Enter or the add button adds all of them. A plain click still selects one.
- The starter menus ship with `"browser": {"hotkey": "Alt+B"}` and a **Browser** slot in **Tools**. An
  existing `radial.json` is not touched: add the `browser` section or set the hotkey in Settings.
- A tag fan's order can shift after you pick, because the most used brushes come first.

### Fixed

- ZBrush 2026: a brush that ZBrush had not loaded yet, picked from the ring or the brush browser, is now selected
  as well as loaded. Before, it only became the current brush on a second pick.


## [0.7.1] - 2026-10-27

### Changed
- The project is now called ZOrbit (it was Radial Menu for ZBrush). The app, Studio, installer, `ZOrbit.exe`
  and the ZBrush palette (**Zplugin > ZOrbit**) are renamed. The GitHub repository is now
  `combwizard/zorbit`; links to the old name redirect.
- The installer upgrades an existing Radial Menu install. It moves it to `%LOCALAPPDATA%\Programs\ZOrbit` and
  removes the old folder, its Start menu shortcut and its ZBrush plugin path entry.
- Menus and settings are copied from `%APPDATA%\RadialMenu` to `%APPDATA%\ZOrbit` on first start, and learned
  auto slots (`usage.json`) from `%LOCALAPPDATA%\RadialMenu`. The old folders are left in place. You can
  delete them.
- ZBrush 2026: the palette moved, so an F9 you bound by hand to Zplugin > Radial Menu > Apply has to be bound
  again on Zplugin > ZOrbit > Apply: Ctrl+Alt+click it, press F9, then Preferences > Hotkeys > Store.
- ZBrush 2022 to 2025: Studio shows the old plugin as "Update available". Update replaces it with the ZOrbit
  plugin, and Remove removes both. The ZOrbit plugin binds F9 itself when Apply has no hotkey.

## [0.7.0] - 2026-10-27

### Added
- Studio opens on a recovery screen when `radial.json` cannot be read: it shows the error with its line and column
  and offers Open folder, Restore backup and Start from defaults (the unreadable file is kept as
  `radial.json.broken`).
- Studio notices when `radial.json` changed on disk after it was loaded and asks whether to overwrite or reload,
  instead of silently replacing a hand edit.
- Studio asks before saving a config that no ring can open from (no menus, or no menu with a hotkey).
- The problems pill opens a panel instead of a bar that pushed the page down: every problem is now in plain
  words, every entry jumps to the menu, item or Settings card to fix, and the menu and item rows concerned
  carry an amber marker.
- Studio reopens on the screen you left and keeps each screen's scroll position while it is open. Clicking the
  screen you are already on no longer rebuilds it.
- Undo and Redo buttons next to Revert. Undo and redo put the selection back where it was, and the Undo on a
  "Removed" or "Deleted" toast undoes that change only, never a later one.
- Clicking a menu or item row keeps keyboard focus on it, so Delete, F2, Enter and Alt+Up/Down work straight
  after a click, and you can delete several items in a row with the Delete key.
- Switching an item's kind no longer carries a brush name into a button path (or the reverse), and when a
  switch drops a target, value, label, icon or steps it says so in a toast with Undo. "Required" hints only
  appear once you have touched the field.
- A Set item's value must be a number; Studio says so under the field and the app reports it as a problem
  instead of sending text to ZBrush.
- The ring preview no longer selects a slot when you click or drop on the empty side of a ring with one to
  three slots, matching the app's quarter-circle cap on a slot.
- Items can be dragged onto another menu in the list to move them there (hold Ctrl to copy). Dropping an
  item on a ring slot now lands on that slot in both directions.
- A submenu item's target is a list of your menus with an Open button, and opening a submenu (double-click,
  Open it, or the button) shows a Back chip that returns to the parent menu and its item.
- Picking an open animation in a menu's settings plays it straight away.
- The menu Id field validates as you type and says why a value is refused; it also warns that renaming
  resets that menu's learned auto slots.
- Brush names are matched ignoring case and spaces in the item inspector and the Library's "used" badges, as
  the guide says. The brush picker closes after Enter.
- The inspector's third tab is called Library (it clashed with the default "Brushes" menu), and row tooltips
  list the keyboard shortcuts.
- Library: a Rescan button picks up brushes saved since Studio opened; when nothing is found the screen says
  whether ZBrush was found and which folders were searched; clicking a brush selects it and shows an "Add to
  <menu>" button, with a hint under the search box; adding a brush that the menu already has asks first; the
  new item scrolls into view and flashes.
- Library search matches brush names only (searching "zbrush" no longer matches every brush), and a search
  with no results inside a folder offers to search all folders.
- Settings: the Colours card has its own live ring preview; number boxes keep the current value when you
  clear them and say when a typed value was kept within range; hex fields accept `#fff`; the animation,
  labels and bridge choice cards are one Tab stop with arrow keys; the "On this page" list stays visible
  down to the smallest window; a preference that could not be saved says so and flips back; "Check for
  updates" shows what the last check found.
- Settings > Older ZBrush: Install and Remove disable the whole row and say "approve the prompt" while the
  administrator prompt is open, which may now stay open for five minutes instead of being reported as a
  failure after one; a declined prompt says so; one install or removal runs at a time; a folder you added
  by hand can be forgotten, and adding one that is already listed says so; the card is one line when no
  ZBrush 2022 to 2025 exists; the F9 note follows the bridge key as you change it.
- The elevated copy of the ZBrush 2022 to 2025 plugin no longer trusts the files staged in the user's data
  folder: it checks that the destination is a ZBrush `ZStartup\ZPlugs64` folder and builds the plugin,
  its config and its shortcuts from this installation's own files. The data folder written into the config
  is the user's own even when the prompt was answered with another administrator account.
- Status: Start app sits on the app card, waits until the app is up (or says it did not start and shows
  the last log lines), and is disabled with the reason while ZBrush is not running; the log shows 40 lines
  with dates on lines from other days, highlights "failed" and "error" lines but not routine picks, and
  has Copy log and an "Updated N s ago" stamp; the Bridge listener card says "Not needed (key bridge)" for
  key-bridge and ZBrush 2022 to 2025 setups instead of a red "Not found"; a dot on the Status rail button
  shows when the app is down while ZBrush runs, and the save toast says so instead of promising the app
  picked the change up. "Open app folder" is now "Open config folder" (where radial.json lives).
- The Status check no longer hangs Studio if the process list is slow, reads only the end of large logs,
  and recognises an app running as administrator.
- Toasts have a close button, pause while you hover or focus them, and no longer stack copies of the same
  message; errors are red and stay until closed. Orange buttons and badges use dark text, muted hints are
  brighter and the smallest labels are larger, all for readable contrast.
- Keyboard and screen readers: the brush and path pickers are proper comboboxes, menus opened from a button
  return focus to it, the hotkey field says what it is for and its current value, the Status log is a log
  region, and a "Skip to content" link is the first Tab stop. The maximise button says Restore when the
  window is maximised, the path of the menus file at the top can be selected and copied, and the ring
  preview no longer flashes a broken image before the first picture arrives.
- Brush thumbnails are sharp at the largest card size, a failed thumbnail batch is retried instead of
  showing initials for the rest of the session, and thumbnails start loading just before they scroll into
  view. Folder groups collapse again when you click the open one.

### Changed
- The Settings screen is called Settings everywhere (it was "Appearance & Behaviour" on the page itself), and
  the ring preview on the Menus screen gives up height to the item list on short windows.
- Save does nothing when there is nothing to save, and `radial.json.bak` is only replaced when the previous file
  was readable and differs, so saving twice cannot overwrite a good backup with a bad one.
- A `radial.json` with a byte-order mark (left by some editors) is accepted by the app and by Studio.
- Closing Studio always asks the page whether anything is unsaved, instead of trusting a flag that could lag
  behind an edit.
- ZBrush 2022 to 2025: the plugin binds F9 to Zplugin > Radial Menu > Apply itself, so the default bridge key
  works without Ctrl+Alt+click and Preferences > Hotkeys > Store. A key you bound and stored yourself keeps
  working. Settings > Older ZBrush offers Update for plugins installed before this.
- A brush pick made outside Edit mode says "(Edit mode is off)" in the bridge log and Status, to explain a
  brush that seems not to switch. The pick still goes through.
- When ZBrush loads the plugin, it deletes a pick left over from a ZBrush that quit before applying it, so
  the first Apply of a new session can't carry out an old pick.

### Fixed
- Studio dialogs: Ctrl+S, undo and the Alt+number screen shortcuts no longer act behind an open dialog, two
  dialogs can no longer stack, and the safe button (Keep editing, Cancel) has focus in Revert, Delete menu
  and Remove plugin, so a stray Enter cannot confirm them.
- Deleting a menu that other menus open as a submenu now removes those links from the state as it is when
  you confirm, and keeps the right item selected afterwards.
- A double-click on the item inspector's delete button removed two items.
- Hotkeys recorded in Studio now use the character you typed rather than the key's position, so Dvorak and
  AZERTY layouts record the key you pressed.
- Removing the ZBrush 2022 to 2025 plugin from Settings > Older ZBrush asks first.
- Starting Studio while it is already open now restores a minimised window and leaves a maximised one
  maximised, and the second launch exits at once instead of loading the web view first.
- Pressing Ctrl+S in Studio before the menus had loaded, or on the error screen, could write `null` over
  `radial.json`.
- ZBrush 2026 and newer: loading the plugin ended in a Python error (`BRIDGE_DIR` is not defined) after
  everything else had started. Nothing stopped working, but `bridge.log` never said "bridge loaded".

## [0.6.0] - 2026-10-27

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

[0.7.1]: https://github.com/combwizard/zorbit/releases/tag/v0.7.1
[0.7.0]: https://github.com/combwizard/zorbit/releases/tag/v0.7.0
[0.6.0]: https://github.com/combwizard/zorbit/releases/tag/v0.6.0
[0.5.1]: https://github.com/combwizard/zorbit/releases/tag/v0.5.1
[0.5.0]: https://github.com/combwizard/zorbit/releases/tag/v0.5.0
[0.4.0]: https://github.com/combwizard/zorbit/releases/tag/v0.4.0
[0.3.0]: https://github.com/combwizard/zorbit/releases/tag/v0.3.0
[0.2.0]: https://github.com/combwizard/zorbit/releases/tag/v0.2.0
