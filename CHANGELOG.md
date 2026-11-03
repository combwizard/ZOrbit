# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Empty slots** (#110): an `{"empty": true}` item keeps its place in the ring with nothing in it. With **Keep slots in place** on (the **Menu** tab), adding, deleting or dragging an item in Studio leaves the others where they are: a delete leaves an empty slot, a new item fills the first one, and a drag swaps two slots. **+** and **−** on the ring preview add and remove slots. It is on for new menus and the starter menus.
- A **Match** switch for tag filters, in the Library and the browser. With two or more tags chosen, **Any** (the default) shows items with at least one of them and **All** shows only items with every one. Under **All**, each tag's number is what choosing it would leave.
- **Tag fan slots** in Settings (Full mode) sets how many slots a tag fan holds, from 4 to 24 (`ring.tag_limit` in `radial.json`). It stays at 12 unless you change it.

### Changed

- **Setup** has three steps. A step that is done folds to one line you can open again. **Your brushes** and **What's where** are gone; Setup ends with a **Next** row of links to the screens and **Take the tour**. The tour is six stops instead of ten.
- An open browser now changes theme the moment you pick one in Studio, instead of up to half a second later.
- ZOrbit is now built and tested on Python 3.14 instead of 3.12. The packaged app bundles the new interpreter; running from a checkout needs Python 3.14.
- **Settings** is shorter and in a better order: **Theme** and **Behaviour** come first, then **Ring look**, **Open animation**, **Studio**, **Import and export**, and in Full mode **ZBrush bridge** and **Older ZBrush**. The browser hotkey is a row at the end of **Behaviour**, in both modes, and the **Browser** and **Tags** cards are gone (the **Browser** button in the top bar stays; **Manage tags...** in the Library now shows the path of the tags file). The **Theme** card no longer has an **Experimental** badge; its hint still says so.
- On **Look**, the gallery of looks now sits right under the ring preview, above the **Preview menu** list, so it shows when the screen opens. Simple mode names its levels **All menus** and **This menu**, as Full does, and no longer has an **Applies to** label.
- In ZBrush 2022 to 2025, `radiald.log` now keeps what every pick did (`pick #12 result: ...`), copied from `zscript_bridge.log`, which only holds the last one. A pick with no result in 15 seconds is logged too.

### Fixed

- Studio: Simple mode no longer says the hint line was changed in Full mode, Press and Toggle items are everyday items, a look you pick for one menu is not a Full-mode setting, and problem links for a look, **Swallow hotkey** or **Fan out when opened from another menu** switch to Full mode first. The Look screen's note about settings changed in Full mode now covers a single menu, and a few hints in Simple no longer name controls only Full has.
- In ZBrush 2022 to 2025, picking an alpha, material or texture whose file is named differently from its name in the menu no longer imports it again every time. The plugin now looks for the button ZBrush names after the file.
- `app_stderr.log` no longer grows for ever: it moves to `app_stderr.log.old` at 200 KB. `radiald.log` is now kept under 1 MB while the app runs, not only when it starts.

## [0.16.0] - 2026-11-02

ZOrbit 0.16.0 adds **Show the hint** to Settings. Turn it off and the ring no longer shows the line of help
under the menu's title.

### Added

- **Show the hint** in Settings turns off the line of help under the menu's title on the ring (`ring.hint` in `radial.json`).

## [0.15.0] - 2026-11-01

ZOrbit 0.15.0 adds looks. A new **Look** screen in Studio (**Alt+2**) sets how the ring looks for every menu, for
one menu or for one slot: six slot shapes, hub styles, glow and label colours, and slot sizes. Seven looks are built
in and you can save your own, and a menu that uses a look follows it when you change it. A menu that has more items
than fit can now spill onto a second ring or end in a **More** slot instead of growing.

### Added

- A **Look** screen (**Alt+2**) for how the ring looks, at three levels: **Global** for every menu, **This menu** for
  one menu, and **This slot** (Full mode) for one slot. A badge on each setting says where its value comes from
  (default, theme, a look, Global, the menu or the slot), and clicking it goes there (#33).
- Looks: a look is a named set of look settings. Seven are built in (**Classic**, **Soft**, **Tiles**, **Crystal**,
  **Circuit**, **Diamonds** and **Minimal**), and **New from current** saves your own. Use one for all menus or for one
  menu; menus that use a look follow it when you edit it. They are saved under `looks` in `radial.json` (#33).
- Six slot shapes (circle, rounded square, squircle, hexagon, octagon and diamond), with **Corner roundness**, **Rim
  width** and **Icon size** (#33).
- The hub in the middle of the ring has a size from 0 to 64 px and a style: a dot (as before), a disc, a ring or the
  menu's icon, with its own colour and glow (#33).
- **Glow colour**, **Glow strength** and **Label colour**. A colour is a theme colour (bg, accent, highlight, text,
  lines), which follows the theme, or any `#rrggbb` (#33).
- One slot can have its own shape, size (75% to 125%), fill and rim colours, icon size, label colour and glow colour,
  saved as `style` on the item. The item panel's **Style** field lists them and has **Edit in Look** (#33).
- **When full** chooses what a menu does when its items do not fit at **Ring radius**: **Grow** (as before), **Second
  ring** (the rest go on a ring outside it; only the outer ring picks on a flick) or **More slot** (the last slot opens
  a ring with the rest). Fans are never paged (#33).
- In Full mode the **Menu** tab has a **Look** section to choose the menu's look, with **Edit in Look** (#33).
- **Export menu...** puts the looks of your own that the menu uses into the file. **Import menu...** joins a look that
  is the same as one you have, and renames one that differs, such as `Bold 2` (#33).
- Studio can install an update itself. Click the new version at the top, or **Install update** in **Settings > Studio**,
  to see the new version's release notes. **Download and install** fetches the installer from GitHub and checks its
  SHA-256. It then runs Setup, and Setup
  reopens Studio and the ring app when it is done. **Don't remind me again** hides that version until a newer one
  comes out. A portable copy gets a link to the download page.

### Changed

- Ring size, labels, colours and tag colours moved from **Settings** to the **Look** screen. **Library**, **Settings**,
  **Status** and **Setup** move to **Alt+3** to **Alt+6** (#33).
- **What's new** shows a link in the release notes as its text, not as `[text](address)`.
- The **Revert** confirmation lists the unsaved changes it would discard.
- The note above the item list shows when a ring is full at its radius, not after 12 items. It says how many items fit
  and what the ring does then (grows to a radius, a second ring, or a More slot), warns when it is too big for the
  screen, and has a **Change in Look** link (#33).
- The outline and the bar in the ring preview on Menus follow the shape of each slot, and the bar works across both
  rings and beside a **More** slot. The preview on Look lights a slot when you hover it and shows its hover glow (#33).
- **Unsaved changes** lists looks under **Looks** and ring look settings under **Look**, not **Settings** (#33).
- Studio's top bar gives way only when it has no room left, not whenever the window is narrower than 1100 px. First
  the **Ctrl+S** hint on **Save** goes, then the word Studio, then **Revert** and **Save** turn into icons, and last
  **Unsaved changes** keeps only its dot. After that the profile name is shortened.
- When an update is available, the version chip stacks your version above the new one, with the arrow beside them, so
  it takes half the width.

### Fixed

- Studio no longer opens as an empty dark window when it was closed maximised. The page now draws in a window that
  opens maximised.

### Removed

- The path to `radial.json` and its copy button are gone from Studio's top bar. With **Unsaved changes** showing, they
  pushed the version number out of sight. **Open menus folder** on the Status screen still opens the folder that holds
  it.

## [0.14.0] - 2026-11-01

ZOrbit now has an experimental **Theme** setting for the ring, the browser and Studio: Dark, Light, Follow Windows, and
Match ZBrush, which takes the interface colours you stored in ZBrush. Expect the light colours and the matching to
change a good deal as more people try them. If something is hard to read with your setup, say so in a
[new issue](https://github.com/combwizard/zorbit/issues). Studio also has a short tour of its window.

### Added

- A **Theme** setting on Settings, marked experimental: **Dark** (the default), **Light** and **Follow Windows**, for
  Studio, the browser and the ring. The ring's colour defaults follow it; a colour set under **Colours** still wins.
- **Match ZBrush** (experimental), a fourth **Theme** choice that colours the ring, the browser and Studio with the interface colours
  you last stored in ZBrush (**Preferences > Config > Store Config**). It reads ZBrush's own file and never changes it.
  Without a stored scheme it uses Dark (#32).
- Studio: a short guided tour of the window. It is offered once after Setup, and you can take it again from Setup step 5 or **Settings > Studio** (#41).
- Docs: a [blog](https://zorbit.lol/docs/blog/) with longer posts about releases, starting with profiles in 0.13.0. A
  release that has a post links to it from its release notes.

### Changed

- Studio: the header at the top has the same colour as the bar on the left, in every theme. In the browser, the tabs
  no longer sit on a darker strip, so the whole header has the colour of the folders column.

### Fixed

- Menu ids such as `constructor`, `toString` or `__proto__` (names a JavaScript object already has) broke Studio. They
  are now reserved: the app reports such a menu, the **Id** field refuses them, and **Import menu...** gives the menu a
  new id.
- Studio no longer opens on a blank screen when `studio.json` names a screen that does not exist.

## [0.13.0] - 2026-11-01

Profiles: a whole set of menus, settings, tags and usage for each kind of work, switched without a restart. Your files moved into the **Default** profile, and the old ones are kept in `%APPDATA%\ZOrbit\pre-profiles`. Going back to an older version and updating again no longer loses what you changed on it.

### Added

- Studio: **Export menu...** and **Import menu...** share one menu and its submenus as a small file, with the tags it uses (#67).
- Profiles: a whole set of menus, settings, tags and usage per kind of work, switched from Studio's top bar or the
  tray icon without a restart. New, rename, duplicate, delete, or make one from a settings file (#19).
- Profiles: files an older ZOrbit wrote to the old places after an update (after going back to 0.12.0, say) are offered in
  Studio as a new profile, or set aside. The brush usage in them is added to the profile in use when the app starts.
- A newer ZOrbit takes the place of an older one that is still running (a portable copy, say). **Studio > Status** offers
  **Restart app** when the app running is older than Studio.
- Studio shows **What's new** once after an update, with a summary of each release since the one you last saw.
  **Settings > Studio** has a **What's new** button to show it again.
- Files made by a newer ZOrbit are left alone. The app shows a message that says which version to install, and Studio
  shows a screen with only **Open folder**.

### Changed

- Your files moved into `%APPDATA%\ZOrbit\profiles\Default\`. The old ones are kept in `%APPDATA%\ZOrbit\pre-profiles\`,
  which you can delete. `usage.json` is per profile now, inside the profile folder.

### Fixed

- Studio: a menus file with a brush, alpha, material or texture name that is not text (`null` or a number, from a
  hand edit) left Studio half-built with Save greyed out. The item is now shown as unusable. A `ring`, `bridge` or
  `browser` section that is not an object, or a `steps` value that is not a list, no longer breaks a screen either.
- Studio: retyping a new menu's title and then clicking a button (such as **Duplicate**) lost the click, and Enter
  or Tab lost the focus. The menu's id now follows the title after the click, and the focus stays in the field.
- Studio: the import dialog said the tag buttons do not touch the menus; it now says both also load the file's
  menus and settings into the editor, which they do.
- Studio: after a Setup check failed, a **Fix**, **Install** or **Forget** button stayed on its busy label. Setup
  now redraws the last good steps, and says when ZBrush runs from a folder it does not know.
- ZBrush 2026 and newer: a pick made during a stroke that lasted more than 10 seconds was dropped without a word.
  The plugin's age limit no longer applies to a pick it held back for the stroke.
- Studio and the browser no longer wipe their own settings file after one failed read. A `studio.json` or
  `popout.json` that is held open or has a typo is left as it is; before, the next change wrote back almost
  nothing, losing the window position, the ZBrush folders you added and every preference.
- A `tags.json` that cannot be opened (held open, no access) is read again every few seconds instead of on every
  poll, which reloaded every ring twice a second and filled `radiald.log`.
- A tag fan with an item ZOrbit had not found yet could keep showing the old list until the next pick. It is now
  built again until the item turns up, and asks for a library rescan at most every five seconds.
- A ZBrush found only through `%APPDATA%\Maxon` (in a folder with no year in its name) now gets its year, so Setup
  shows it as ZBrush 2026 and an older version is no longer offered the plugin.
- The first menus file is written in one step, so the app and Studio starting together never read half of it.
- The bridge key can no longer be an `Alt` combination or **F10**. ZBrush 2022 and 2025 run no **Apply** for those
  when ZOrbit sends them, so every pick through the bridge key was lost. Studio's recorder refuses them, and a
  `radial.json` that names one is listed as a problem and uses F9.
- Browser: merging two tags points the ring's Tag and Browser slots that used the merged tag at the kept one in
  `radial.json` (the old file is kept as `radial.json.bak`), instead of leaving them empty or unfiltered.
- An `icon` that looks like a path but is not a full path, or a full path to a file that is not there, is listed as
  a problem instead of silently showing a letter tile.
- The message near the cursor when the plugin does not answer says whether the bridge mode is Message or no bridge
  key is set, and the no-listener and no-key messages say what to do.
- Studio: the hotkey recorder accepts the quote and backtick keys on US-International layouts instead of saying
  they are in a different place.

## [0.12.0] - 2026-10-31

### Added

- Studio: a **Simple** / **Full** mode switch in the top bar. Simple shows the controls most people use (brush,
  alpha, material, texture and submenu items; menu title and hotkey; one ring-size slider, open animation, labels,
  flick, the browser hotkey, Studio preferences, import and export) and hides the rest. A fresh install starts in
  Simple; an existing setup that uses something Simple hides opens in Full. The mode only changes what Studio
  shows and is kept in `studio.json` as `mode`.
- Studio: **Alt+Up/Down** moves a menu in the Menus list, and **Move to menu...** (a button on the Item tab, or
  **M** on an item row) moves an item to another menu without dragging. The Setup checks show their state as an
  icon and a word (OK, Needs attention, Not working, Not checked yet), not only as a colour.
- Uninstalling removes the plugin from every ZBrush 2022 to 2025 that Setup lists, wherever it is installed (one
  UAC prompt for each one under Program Files), and lists any folder it could not clean.
- A short message near the cursor when ZOrbit knows why a pick did nothing: no connection to the plugin, no answer
  from it, ZBrush not in front, no bridge key, an empty slot, a submenu with nothing in it, or a brush, alpha,
  material, texture or button that ZBrush could not find. A working pick shows nothing.
- A balloon from the tray icon when `radial.json` cannot be read, and after **Reload menus** ("Menus reloaded", or
  the reason it failed). The tray tooltip says the menus file cannot be read until it loads again.
- Tooling: GitHub Actions runs the test suite (`pytest`) on every push and pull request, and the build only starts
  when the tests pass. `ZOrbit.exe --selftest` checks that the libraries, app modules and bundled files are all
  present, and CI runs it on the built exe. `requirements-lock.txt` pins the exact package versions, and
  `packaging\build.ps1` and CI install from it. Release notes start with which file to download and the SHA256 of
  the installer and the portable zip.

### Changed

- Studio and browser: Library cards and folder rows are one Tab stop each, with the arrow keys, Home and End
  moving inside them; opening the problems list with the keyboard puts the focus on its first entry; dimmed and
  red text reach a 4.5:1 contrast; with Windows animations off the spinners and pulsing dots stand still instead
  of flickering (thanks to Jay, #92); a pen or a finger can drag rows, cards and ring slots. A rescan of an
  unchanged library keeps the list and its cards, and thumbnails load in small batches with the visible ones
  first.
- Studio: Setup says what to do when ZBrush has not loaded the plugin (press **Fix** and restart, or close ZBrush
  and start it from the Start menu, then read `bridge.log` or `zscript_launch.log` if it exists), notices a
  ZBrush started from a program that was already open before the plugin was registered, and explains a ZBrush
  running as administrator (the ring will not open; if its plugin listener is up it counts as loaded). Step 3
  says why a pick was not sent and what to do, naming your real bridge key. Badges read **Plugin registered**,
  **Plugin not installed**, **Plugin update available** and so on; Status shows the listener as **ZBrush closed**
  instead of **Stale** when ZBrush is not running; **Open config folder** is **Open menus folder**; the bridge
  key field says **F9 (the default)**; the Save anyway and Import dialogs show problems in plain words; the
  empty library message lists every file type it looks for; the browser's "ZBrush was not found" and "ZOrbit
  is not running" messages say what to do next; **Remove** shows the approve-the-prompt hint; **Also registered**
  says why it matters; an invalid tag colour says what to type; and "pressAlt+F9" has its space back.
- Studio: the import dialog says how many of the file's menus replace how many of yours, that nothing is written
  until Save, and that **Merge tags** and **Replace tags** touch tags only (hidden when the file has none).
  Problems from the menus file are described in plain words, the note about crowded menus says the ring grows,
  and a ZBrush folder added by hand can be forgotten from Setup.
- Browser and Library: thumbnails are decoded four at a time and big JPEGs are read at a reduced scale, so a
  page of large textures fills in about three times faster; at most a few hundred thumbnails are kept in
  memory; a library refresh that finds nothing new no longer resends the whole list.
- Studio: the first window fits a laptop screen (smaller than 1320 x 860 when the work area is), and the
  minimum height is 560 instead of 640. **Add a ZBrush folder** accepts a ZBrush 2026 or later that has not
  run yet, so Setup can show and fix it, and the ZScript plugin can be installed into a ZBrush 2022 to 2025
  that Studio only knows from its running process.
- Studio: **Setup** is Alt+5 (it was Alt+6). Alt+1 to Alt+4 are unchanged.
- The installer's last page says what to do next for ZBrush 2026 and newer (restart it) and for ZBrush 2022 to
  2025 (install the plugin from Studio's Setup screen). The plugin's "app was not found" dialog covers the
  installer, the portable zip and running from source.
- Studio: a new menu's id comes from its title (**Sculpting** becomes `sculpting`) instead of `menu`, `menu_2` and
  so on, and follows the title until the menu is saved or you type an id yourself. Accented letters are kept
  without the accent.
- The starter Brushes menu no longer swallows **Q** (new installs only): ZBrush switches to Draw mode when the ring
  opens, and **Q** still types in ZBrush's own fields. Switch **Swallow hotkey** on in the menu settings to hide the
  key again.
- The keyboard hook runs on its own thread, so file polling, thumbnail work, library rescans and process starts in
  the app can no longer make Windows drop it and stop the hotkeys from working. A hotkey tapped while the app is
  busy still opens the ring in hold mode.
- Typing another key closes a ring that was opened by a tap and is waiting for a click. Hotkeys are ignored in
  Windows dialogs (such as Save As) and Windows text boxes.
- Keys sent by a tablet driver, a macro tool or a key remapper open the ring like the real key. Only ZOrbit's own
  key presses are ignored. The hidden `--accept-injected` option is gone.
- Starter menus (new installs only): the **More Brushes** slot shows the ClayTubes picture instead of a letter
  placeholder, and the starter tags are recoloured, **Blocking** lime green and **Detailing** violet, so they no
  longer look like the ring's hover and submenu colours. The tag colour presets start with lime and violet. A saved
  `tags.json` keeps its own colours.
- Ring: the ring radius is now a minimum. A menu with many items makes the ring wider so neighbouring slots keep a
  gap (from 10 items at the default slot size); the Studio preview does the same.
- Ring: slot names sit on a soft dark pill, and every disc is drawn before any name, so a neighbouring slot no
  longer covers a label. The same goes for fans.
- Ring: the hint under the menu title is clearer ("release or flick to pick", "click a slot, centre or right-click
  cancels") and easier to see. The title and hint shrink or shorten to fit a small ring.
- Ring: a menu opened again reuses its drawn slots, so the ring appears sooner (about 4 ms instead of about 90 ms
  for an 11-item menu).
- Installer: Setup asks ZOrbit Studio to close the normal way and waits up to 15 seconds instead of ending it; if
  Studio is still open (it may have unsaved changes) Setup and the uninstaller stop and ask you to close it. An
  update keeps a custom install folder. `LICENSE` and `THIRD_PARTY_NOTICES.md` are installed next to the program
  and included in the portable zip, and the program's file properties name the copyright holder.
- ZBrush 2021 and older are no longer offered the ZScript plugin; Studio refuses to install it and marks them as
  unsupported. The docs say the plugin binds F9 to Apply when Apply has no hotkey (verified in ZBrush 2022), not
  that it always does.

### Removed

- The Licence screen in Studio, its rail button and the **Show the Licence button** setting, and the fake
  licence-key table in the README. ZOrbit is GPL-3.0 and the README and **Settings > Studio** say so plainly. An
  old `show_licence` entry in `studio.json` is ignored and dropped the next time Studio saves a preference.

### Fixed

- Studio: the focus was lost after deleting a menu from the Menu tab or renaming its id.
- Studio: **Rescan** rescans the tab you are on, not the one the Library opened on. Enter and **Add** no longer
  act on an item a filter has hidden. Merging a tag re-points the ring slots that used it (one Undo step) and
  the problems list refreshes after any tag is added, removed or merged. The ring preview no longer draws a
  slot for a submenu whose own menu has no usable items. A hand-edited menus file with a null menu or a menu
  without items no longer leaves Studio on "Loading...": it opens as an empty menu or on the recovery screen.
- Studio: the hotkey recorder refuses numpad keys and punctuation that sits elsewhere on your layout instead of
  recording a key that never fires, accepts dead and IME keys by position, and Alt+1 to Alt+5 work on AZERTY.
- Studio: the **Add item** list is no longer cut off in a short window and the Library toolbar wraps in a narrow
  one. The Add-to-menu list keeps its scroll position, the item inspector is not rebuilt under you when the
  library finishes loading, Undo and Redo keep the current tab, Set values like `.5`, `5.` and `1e-3` are
  accepted, and **Reset all colours** and clearing the bridge key leave no empty sections in the file.
- A thumbnail cache file that was cut short is decoded again instead of being shown broken, and a picture that
  failed to decode is tried again next time instead of staying blank.
- Studio: **Restore backup** asks first and keeps the `radial.json` it replaces as `radial.json.broken`, as
  **Start from defaults** already did, and so does a save over a `radial.json` that is not valid JSON. **Start from
  defaults** no longer claims the current file is lost. A menus file that cannot be written as text says "Could not
  save" and leaves no stray `.tmp` file.
- Studio no longer blocks Windows from shutting down, restarting or signing out: it saves its window position
  and closes.
- Studio: **Start app** waits up to 10 seconds with a busy label, treats a slow start as progress, and after a
  failure shows only the log lines from that launch, on Setup too with an **Open Status** button. When the Setup
  check itself fails, Setup shows the error and keeps the last good answer instead of an empty list, the rail dot
  stays as it was, and the details go to `studio.log`.
- Studio checks for the Microsoft Edge WebView2 runtime before it opens and says what is missing. Importing a file
  whose tags section is empty no longer offers to import tags.
- Ring: names, menu titles and placeholder letters in Chinese, Japanese and Korean are drawn with a font that has
  the characters (Microsoft YaHei, Yu Gothic, Malgun Gothic) instead of empty boxes. A long menu title is shortened
  with an ellipsis instead of running across the slots.
- Installer: updating no longer leaves files of older versions behind in the install folder, and uninstalling
  removes the install folder. A machine-wide `ZBRUSH_PLUGIN_PATH` is no longer shadowed: when you have no user
  value, the new one starts from the machine entries (installer and Setup's **Fix**).
- ZBrush 2022 to 2025: the plugin installs without its start shortcuts when PowerShell is restricted (Constrained
  Language Mode, AppLocker, an antivirus) instead of failing; the plugin then starts ZOrbit the slower way, and
  Studio no longer reports it as outdated. Installing is refused with a clear message when the data folder path
  cannot be passed to the plugin (characters outside the Windows code page with 8.3 names off). Pressing Apply with
  no pick waiting no longer overwrites the last pick in `zscript_bridge.log`, and the Status button shows the real
  last pick. Setup spots the old Radial Menu bridge folder as a second copy of the plugin.
- App: a second ZOrbit instance is detected reliably again (the check could be lost to another Windows call).
- App: a hotkey whose key-up the app missed (after Windows dropped the keyboard hook, say) no longer stays dead: a
  key that is no longer down is let go, a swallowed one after 30 seconds, and the hook is re-installed whenever no
  ring is open.
- App: a pick that waits for a stroke to end follows your primary mouse button, so it works with the buttons
  swapped in Windows. The plugin does the same.
- Bridge: with more than one ZBrush running, a pick goes to the listener of the ZBrush you are picking in, not to
  whichever one started last; otherwise the bridge key is used.
- Bridge: a pick that could not be handed to ZBrush is deleted instead of staying in the request file, and the
  plugin ignores a request more than 10 seconds old, so an old pick is never applied later by accident.
- App: a ZBrush running as administrator is reported in `radiald.log` and in `activity.json` (`elevated_zbrush`)
  within a few seconds, instead of the hotkeys doing nothing without a word.
- Ring: a quick tap of the hotkey with the cursor already over a slot picks that slot. Only a tap with the cursor in
  the middle keeps the ring open for a click.
- Ring: after a ring is moved in from a screen edge, nothing is picked or opened until the cursor has moved into
  it, and the hint says "move into the ring" until then.
- Ring: an error inside the ring is logged with a full traceback, and a ring that fails while opening takes its
  window down instead of leaving it on screen.
- App: a pick whose request file cannot be written is reported ("could not write the request file") instead of
  failing quietly.
- Ring: slot pictures refresh when the picture file is replaced or the library is rescanned, and a slot whose
  picture was missing is looked up again instead of showing the placeholder until ZBrush restarts.
- A `usage.json` that is locked or cannot be read no longer empties your brush scores, auto slots and recent
  picks: ZOrbit keeps what it had and tries again, and a file with a syntax error is copied to `usage.json.bad`
  before anything can overwrite it. One bad entry no longer drops the rest of the file.
- A `tags.json` that cannot be read when ZOrbit starts leaves the starter tags (Favourites, Blocking, Detailing)
  available, and nothing is written until the file is fixed. Tag slots then give one clear message instead of one
  per slot.
- A section of `radial.json` of the wrong type (such as `"ring": "big"`), or a file that is not an object, is
  reported by name instead of failing with an obscure error. A `fan` that is not true or false is reported. Typos
  in `ring.colors`, `bridge`, `browser` and item settings get "did you mean" hints.
- Brush, alpha, material and texture names that contain `\`, `/`, `:` or `..`, and icons that point at a network
  path, are reported as problems and not used.
- Saving a file no longer fails when a virus scanner or sync tool holds it open for a moment: ZOrbit retries for
  about 1.5 seconds first.
- If the `%APPDATA%\ZOrbit` folder cannot be created, the app logs a plain "cannot create the menus file in ..."
  line instead of a traceback.
- Browser: it no longer blocks shutting Windows down, restarting or signing out; it saves its place and closes
  with the session.
- Browser: a window left on a monitor you have since unplugged is brought back onto a screen every time it is
  shown, not only the first.
- Browser: when the Microsoft Edge WebView2 runtime is missing it says so, with the download link, and any other
  failure while it starts is written to `popout.log` as a traceback. `radiald.log` records when the browser
  process ends.
- Plugin (ZBrush 2026 and newer): an error while the plugin starts is written to `bridge.log` (it used to show only
  in ZBrush's console), and a button or the listener that fails no longer takes the rest of the palette down.
- Plugin: a pick with several brushes, alphas, materials or textures that ZBrush has to load first selects each one
  in turn. Before, a second one replaced the first, and a loaded later item cancelled it.
- Plugin: a brush, alpha, material or texture is found by its file name as well as its menu name, so
  `{"brush": "Clay Buildup"}` presses the button ZBrush names `ClayBuildup`.
- Thumbnails: the curve brushes (CurveSlash, DisplaceCurve, Grid1, GridDots, MoveCurve2, SnakeCurve) and the IMM
  inserts InsertEar2 and InsertRing showed letters. Their icons are stored Huffman coded, and ZOrbit reads that now.
  Every stock brush icon of ZBrush 2022 to 2027 reads.
- Library: the browser's list and the ring's lookup of brushes, alphas, materials and textures come from one folder
  walk, so they agree on sort order, on duplicates (case and spaces ignored, first folder wins) and on subfolders
  and links. A folder link that loops no longer runs away.
- Library: when a search folder has gone or its drive cannot be reached, the browser keeps the list it had and says
  why. An uninstalled or moved ZBrush no longer hides a working one, and ZBrush's path files are read as UTF-8 or
  in the ANSI code page.
- Tag fans look again for a brush, alpha, material or texture saved after the app first scanned, without waiting.
- Docs: `~` for the backtick key and `Control` for `Ctrl` are accepted in hotkeys and now documented.

## [0.11.0] - 2026-10-30

### Added

- Browser: when the folders and tags column is collapsed, a tag or folder filter that is on shows as a chip in the
  toolbar ("Filtered: Blocking", "Folder: My Brushes") with an x that clears it.
- Browser: it checks for tag changes made in Studio every 5 seconds while it is open, not only when it gets focus.
- Browser: deleting a tag in its tag manager now says how many ring items use it, and the warning about Tag and Browser
  slots is correct ("Tag slots that use it go empty; Browser slots open unfiltered.").

### Changed

- Studio: Ctrl+Z and Ctrl+Y now work after you have moved a slider or flipped a switch, a select or a colour swatch.
  Only a text box keeps its own undo. After an undo the Settings screen is rebuilt only when something it shows changed,
  and the control you were on keeps focus.
- Studio: the hotkey field can record `space`, `tab`, `enter`, `backspace`, `insert`, `delete`, `home`, `end`, `pageup`
  and `pagedown`, which the app already understood. The "not supported" message lists what is allowed.
- Studio: the "Not found in your library" hint names the files ZBrush needs for that kind (a .zbp file, a .zmt file, and
  the image types for alphas and textures). When the library could not be read, or ZBrush was not found, the hint says
  that and links to Library or Setup.
- Studio: the "file changed on disk" dialog says that reloading discards your unsaved changes, and Cancel has focus
  instead of Reload from disk.
- Studio: the top bar keeps the window buttons in view at the minimum width with an update chip, a problems pill and
  "Unsaved changes" showing. The pill and the label no longer wrap, the copy-path button goes with the path, and below
  1100 px the word Studio and the Ctrl+S hint on Save are hidden.
- Studio: when two menus share a hotkey, the warning says which one comes first and wins.
- Studio: long menu hotkeys are cut with an ellipsis instead of squeezing the title away; a menu without a hotkey shows
  a small submenu icon instead of the word. Menu and item rows have a tooltip with the full title, hotkey and target.
- Studio: step buttons (move up, move down, remove), the step type, the action type and the inspector's Delete leave the
  keyboard on a nearby control instead of dropping it. The inspector's Delete behaves like the button on the row.
- Studio: each list (menus, items) is one stop for the Tab key. Up, Down, Home and End move through it, and the Library
  tab's item list does the same. The buttons on the rows are reached with the mouse or the Delete, F2 and Alt+Up/Down
  keys.
- Studio: the problems panel opens after a save or an import only when there is a problem that was not there before.
- Studio: the Status log is not redrawn when its lines have not changed, so a selection in it survives the refresh.
- Studio: the Setup hint for a pick the plugin did not act on shows the failure from the bridge log when there is one,
  and otherwise says to open the logs folder from Status. It has an Open Status button.
- Studio: a slider put back to its default is taken out of the file again, so Save does not light up and the close
  dialog does not list "default -> 145". A switch does the same, and an empty `ring` object that the file did not have
  is not left behind.
- Studio: clicking empty space in the ring clears the selection but stays on the Item tab.
- Studio: moving an item to another menu keeps you on the menu you were editing, flashes the target menu's row, and the
  Ctrl copy cue follows the Ctrl key during a drag, not only the pointer.
- Studio: the Swallow hotkey switch is off and says "Set a hotkey first" while the menu has no hotkey.
- Studio: a note above the item list says rings work best with 4 to 12 items when a menu has more than 12.
- Studio: the recovery screen has an Open logs folder button, and the rail is dimmed with a tooltip ("Fix or reset the
  menus file first") while the menus file cannot be read.
- Studio: the Browser buttons show "Opening the browser..." at once, because a cold start takes a moment.
- Studio: wording. "1 item" instead of "1 items", "Delete (Del key)", the Accent colour hint says "Centre dot, hover and
  title", Setup's user guide row says it is at zorbit.lol/docs, the Message bridge mode says a pick is dropped and
  logged when no listener is live, and the problem markers on rows have a text for screen readers. The Install button
  says "Installing..." and adds "approve the prompt if Windows asks" only after four seconds of waiting.
- Browser: the toast after a pick now says "Sent Anchors to ZBrush" instead of "Selected Anchors", because it only means
  the app took the pick. When the app is not running it says "ZOrbit is not running. It starts and stops with ZBrush.";
  when it is running but does not answer in time, "ZOrbit did not answer. Try again in a moment."
- Browser: a Rescan keeps the highlighted item and the scroll position, says what changed ("Found 12 brushes, 2 new, 1
  gone", or "no changes"), and when the folders cannot be read it keeps the list you had and shows the error.
- Browser: when it appears, or when you open a tab, the list is read again if the last read is more than a minute old,
  so a brush saved in ZBrush meanwhile shows up without pressing Rescan.
- Browser and Library: the tag chips say they count the current tab; the tag picker and the tag manager say they count
  every item across all four tabs.
- Browser: the "ZBrush was not found" message says "ZOrbit Studio", and the Library's version has a "Find ZBrush in
  Studio" button that opens the Setup screen.
- Tags: merging a tag into another one now asks for confirmation first, with Cancel as the default.
- Docs: the documentation moved to <https://zorbit.lol/docs/>: the user guide and the longer parts of the README are now
  separate pages with search. Studio's **Setup** screen opens it there.
- Docs: the browser page now says correctly that the folder and the selection reset when you switch tab, and that the
  search text, tag filter and thumbnail size stay.
- Docs: menus and items: the Auto item type is documented, and the 12-item advice says why. Studio: the Menu and Item
  tabs, renaming a menu id, the Used by list, the item-type toast, the arrow keys in the lists and the way saving, undo
  and the problems panel behave.

### Fixed

- A pick made during a stroke no longer applies in the middle of it in ZBrush 2026 and newer: while the mouse button is
  down the app waits instead of falling back to the bridge key, and the plugin's **Apply** waits too. ZBrush 2022 to
  2025 still cannot wait.
- A ring opened near a screen edge is moved in so the whole ring is on screen, instead of being cut off. Nothing is
  picked or opened by hover until the cursor has moved inside it.
- With no `bridge.key` in `radial.json`, the bridge key is F9, as Studio says. A key with Ctrl or Shift, or one that
  cannot be read, is reported and F9 is used.
- A `radial.json` that cannot be read when the app starts no longer stops the app: it starts without menus, logs "cannot
  load radial.json" and picks the file up as soon as it is fixed.
- A brush, alpha, material or texture saved after the app started is found on the next pick instead of failing with "NOT
  loaded in ZBrush and no file known" until a restart. Tag fans notice new files too.
- A submenu slot that points at a menu with no usable items is reported ("submenu 'x' has no usable items") and skipped,
  instead of closing the ring without a word.
- "Remove from Recent" and the use counts now treat `Clay Buildup` and `ClayBuildup` as one brush. Older `usage.json`
  entries are merged when the file is read.
- A setting name that is misspelt in `radial.json` (for example `ring.raduis` or a menu's `itmes`) is now listed as a
  problem, with a suggestion. A `swallow` that is not `true` or `false` is listed too.
- **Reload menus** in the tray no longer logs "menus reloaded" after a file that could not be read.
- The app logs a line when ZBrush runs as administrator and its hotkeys are ignored for that reason.
- `request.txt` is only written, and its code page warning only logged, when a ZBrush 2022 to 2025 is installed.
- ZBrush 2022 to 2025: the plugin's log says "NOT loaded in ZBrush and no file known" like the rest of ZOrbit, and a
  pick with several steps logs the result of every step, not only the last.
- Studio: the "your hotkeys ()" hint in the suggestions has no empty brackets. **Add a ZBrush folder** with a ZBrush
  2026 or newer explains when it appears on Setup. Status shows a changed bridge mode as soon as you save (it lagged by
  up to 30 seconds), and Status and Setup use less CPU (no `tasklist` every three seconds, the install scan is kept for
  five seconds).
- Browser: after clicking a tag chip, a folder, a tab, Rescan or the pin, Enter picks the highlighted item again (it
  used to press the control you had clicked), and a focused size slider no longer swallows typed letters. The cursor
  goes back to the search box after a mouse click on any of them.
- Browser: Enter and the arrow keys pressed straight after typing in the search box act on the new results, not on the
  ones from before the last keystroke.
- Tags and Recent: a tags.json or usage.json that was deleted or put back from an older copy is picked up straight away
  instead of being ignored until restart.
- Library: two files whose names differ only by spaces now count as one item (the first folder wins), as they already
  did for tags and favourites.
- Studio: a Rescan that fails keeps the list it had and shows the error.

## [0.10.2] - 2026-10-30

### Fixed

- The **Skip to content** link no longer shows at the top left of Studio when it opens. Since 0.10.1 the window passes
  keyboard focus to the page when it is shown, and the page put that focus on the link. It now takes focus only after
  a Tab press.

## [0.10.1] - 2026-10-30

### Fixed

- Studio no longer flashes black when it opens or when it leaves maximised. It now opens hidden, gets its title bar
  removed, its saved size and position and its maximised state, and shows once the page has loaded (after 3 s at
  most). Leaving maximised is one resize straight to the remembered size, instead of a resize one title bar too tall
  followed by a correction. The browser window restores the same way.
  Not yet tested on the PC that reported the flash: on a test machine the extra resizes are gone, but nobody has
  checked the flash itself there yet.
- The Studio and browser windows start in the page's own background colour.

## [0.10.0] - 2026-10-30

### Added

- Alphas, materials and textures as ring items: `{"alpha": "Alpha 058"}`, `{"material": "SkinShade4"}` and
  `{"texture": "Txtr01"}`, also as steps in a `steps` item. The name is the file's name; case and spaces are ignored,
  and the first folder that has the file wins. An item ZBrush already has is selected. Otherwise it is loaded from its
  file with Alpha > Import, Material > Load or Texture > Import, then selected. Material > Load replaces the material
  in the selected material slot, as ZBrush does itself.
- Both bridges handle the new items: the Python plugin for ZBrush 2026 and newer, and the ZScript plugin for ZBrush
  2022 to 2025. The 2022 to 2025 plugin needs an update from **Settings > Older ZBrush** (**Update**) before these items
  work there.
- Thumbnails for the new kinds, cached in `%LOCALAPPDATA%\ZOrbit\thumbs`. Materials use the icon stored in their `.zmt`
  file, and alphas and textures use their image. EXR textures have no thumbnail.
- The browser window has four tabs, **Brushes**, **Alphas**, **Materials** and **Textures**. Ctrl+Tab and
  Ctrl+Shift+Tab switch between them. Search, folders, tag chips and the size slider work per tab. The tab you were on
  is remembered in `popout.json`. `--kind brush|alpha|material|texture` opens the browser on a tab, and a browser slot
  can say `"kind"` too.
- Studio's Library and the Library tab on the Menus screen have the same four tabs. Add to menu and drag and drop work
  for every kind. The item inspector offers Alpha, Material and Texture, each with a picker and a "Not found" warning,
  and a Browser item has a "Shows" select.
- Tags apply to every kind, with one shared tag set. A `tag` slot's fan lists brushes first, most used first, then
  alphas, materials and textures by name.
- The browser has its own icon, and its Start menu shortcut is called **ZOrbit Browser**.
- A **Browser** button in Studio's top bar opens the ZOrbit Browser from any screen.
- Two buttons in the browser's header: one collapses the folders and tags column and shows it again, the other
  moves it to the right side of the window and back. Both are remembered in `popout.json` (`column`, `side`).
- `ZOrbit.exe --check` prints each item's resolved file, `opens on <kind>` for browser items and `N items tagged` for
  tag slots.
- **Settings > Import and export**. **Export...** saves the menus, settings and tags to one `.json` file, as they are
  on screen. **Import...** accepts that file, or a plain `radial.json` or `tags.json`, and shows what it holds first.
  Imported menus and settings load as an unsaved change, so Undo takes them back. For tags, choose **Merge tags** or
  **Replace tags**; a replaced `tags.json` is kept as `tags.json.bak`.
- A **Setup** screen in Studio, the sixth button in the rail (Alt+6). It is a checklist with live state: ZBrush found,
  plugin loaded in ZBrush, try the ring, your brushes, and what's where. A fresh install opens Studio on it; **Finish**
  or **Skip for now** marks it done (`setup_done` in `studio.json`), and closing Studio without either brings it back.
  Existing users are not sent to it, and **Show Setup on next start** at the bottom brings it back.
- Setup shows every ZBrush version found. For ZBrush 2026 and newer it says whether `ZBRUSH_PLUGIN_PATH` points at the
  plugin, and **Fix** adds it the way the installer does. Rows for ZBrush 2022 to 2025 have the same **Install**,
  **Update** and **Remove** as **Settings > Older ZBrush**, plus **Add a ZBrush folder**.
- Setup checks whether ZBrush is running, which version, whether it loaded the plugin, and whether it needs a restart
  because it was started before the plugin was set up. **Start app** starts the app from there.
- **Try the ring** on Setup ticks off three checks as you use the ring in ZBrush (ring opened, pick sent, ZBrush did
  it), and gives a hint for the pick's route when ZBrush does not confirm it within a few seconds.
- An amber dot on the Setup button when no ZBrush found has the plugin set up, or a running ZBrush does not.
- `%LOCALAPPDATA%\ZOrbit\activity.json`, written by the app: the last ring opened and the last pick it sent, with its
  route and whether the plugin picked it up. Setup reads it. Safe to delete.
- Favourites: a built-in tag, shown with a gold star instead of a dot. It always exists and always comes first. It
  cannot be deleted, renamed or merged away, but its colour can be changed in the tag manager. Starring an item does
  not change its colour cue; the first other tag does.
- Star an item in the browser (on every tab) or in Studio's Library: hover a card and press the star in its top-right
  corner. The selection strip has a star button for the whole selection, **Ctrl+D** toggles Favourites on the
  selection or the highlighted card, and the right-click tag picker lists Favourites first.
- A **Favourites** entry at the top of the folders list on every tab, with a count. It lists starred items, most used
  first, then by name.
- A `{"tag": "favourite"}` ring slot: a fan of your favourites, drawn with a star. `{"browser": "favourite"}` opens the
  browser filtered to favourites. New installs get a Favourites slot in the starter **Tools** menu; existing menus are
  not changed.
- **Recent**, under Favourites: every brush, alpha, material or texture you pick in ZBrush, from a ring or from the
  browser, newest first. Up to 24 per tab, and 200 across all kinds in the file. Right-click an item in the Recent view
  for **Remove from Recent**. Stored under `"picks"` in `usage.json`.

### Changed

- Picks of alphas, materials and textures are now recorded in `usage.json` too, for Recent. Brush auto slots are
  unchanged.
- "Brush browser" is now "Browser" in Studio, the Start menu and the user guide.
- The Studio web API: `get_library(refresh, kind)` returns the items under `items`. The `brushes` key is kept for the
  brush kind for one release. `get_thumbs(names, size, kind)` takes a kind.

## [0.9.0] - 2026-10-30

### Added

- A tag band on the ring. `ring.tag_band` (`none`, `hairline`, `narrow`, `medium` or `wide`, default `medium`)
  draws a strip through the slot centres, each slot's stretch in its tag colour and a faint grey one for an
  untagged slot. A ring with no tagged slots has no band. `ring.tag_band_opacity` (0 to 1, default 0.45) sets
  how solid it is. The band does not depend on `tag_colors`. Slot colours are now dropped entirely only when
  both `tag_colors` and `tag_band` are `none`.
- Opacity for the glow and the tint: `ring.tag_glow_opacity` (default 0.4) and `ring.tag_tint_opacity` (default
  0.3), both 0 to 1.
- Tint style and blend. `ring.tag_tint_style` (`flat` or `gradient`, default `gradient`, which is stronger
  towards the rim) and `ring.tag_tint_blend` (`multiply` or `overlay`, default `multiply`).
- A reworked **Settings > Tag colours** card with three groups, **Icon tint**, **Glow** and **Band**, each with
  a switch. The tint and glow switches together set `tag_colors`, and the band switch sets `tag_band`.
  Opacities show as percentages, and controls under a switch that is off are dimmed. The preview beside them
  shows the current menu if it has a tagged brush, and otherwise a sample ring of your brushes coloured with
  your tags.

### Changed

- `tint` now lays the tag colour over the brush icon, with a rim in the same colour, instead of only colouring
  the disc behind the icon. The old disc tint is gone. By default it multiplies at 0.3 and is stronger towards
  the rim, so tagged slots read more clearly.
- The tag band is on by default. Set `ring.tag_band` to `none` to turn it off.

## [0.8.1] - 2026-10-30

### Fixed

- Clicking the pin (**Keep on top**) in the brush browser froze its window, and it stayed frozen until ZOrbit
  was restarted.

## [0.8.0] - 2026-10-30

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
- The portable zip failed at startup on some PCs with "Failed to resolve Python.Runtime.Loader.Initialize".
  Windows marks files unzipped from a download as coming from the internet, and .NET Framework would not load
  the marked DLLs. ZOrbit now removes that mark from its own DLLs when it starts.


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

[0.16.0]: https://github.com/combwizard/zorbit/releases/tag/v0.16.0
[0.15.0]: https://github.com/combwizard/zorbit/releases/tag/v0.15.0
[0.14.0]: https://github.com/combwizard/zorbit/releases/tag/v0.14.0
[0.13.0]: https://github.com/combwizard/zorbit/releases/tag/v0.13.0
[0.12.0]: https://github.com/combwizard/zorbit/releases/tag/v0.12.0
[0.11.0]: https://github.com/combwizard/zorbit/releases/tag/v0.11.0
[0.10.2]: https://github.com/combwizard/zorbit/releases/tag/v0.10.2
[0.10.1]: https://github.com/combwizard/zorbit/releases/tag/v0.10.1
[0.10.0]: https://github.com/combwizard/zorbit/releases/tag/v0.10.0
[0.9.0]: https://github.com/combwizard/zorbit/releases/tag/v0.9.0
[0.8.1]: https://github.com/combwizard/zorbit/releases/tag/v0.8.1
[0.8.0]: https://github.com/combwizard/zorbit/releases/tag/v0.8.0
[0.7.1]: https://github.com/combwizard/zorbit/releases/tag/v0.7.1
[0.7.0]: https://github.com/combwizard/zorbit/releases/tag/v0.7.0
[0.6.0]: https://github.com/combwizard/zorbit/releases/tag/v0.6.0
[0.5.1]: https://github.com/combwizard/zorbit/releases/tag/v0.5.1
[0.5.0]: https://github.com/combwizard/zorbit/releases/tag/v0.5.0
[0.4.0]: https://github.com/combwizard/zorbit/releases/tag/v0.4.0
[0.3.0]: https://github.com/combwizard/zorbit/releases/tag/v0.3.0
