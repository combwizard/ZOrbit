# TODO

## Next

- [x] Compile `ZOrbitBridge.txt` in ZBrush 2022 and commit `ZOrbitBridge.zsc` (the rename removed the old `.zsc`)
- [x] Retake docs/images screenshots (Studio wordmark and palette now say ZOrbit)
- [ ] Support ZBrush 2022–2025 (ZScript bridge in `bridge/zscript/`, Studio: Settings > Older ZBrush)
  - [x] Compile `ZOrbitBridge.txt` in ZBrush 2022 (commit the `.zsc` with the source)
  - [x] 2022: palette loads, Studio install, F9 Apply selects a loaded brush
  - [ ] 2022: load a brush that isn't loaded yet, press/set/toggle, steps, Status, Studio button
    - The 2026 bridge had to press a freshly loaded brush again once ZBrush had added its button (a timer on
      the listener). The ZScript bridge presses it straight after `Brush:Load Brush` too: check whether 2022
      selects it, and if not, retry the press (ZScript has no timer: a second Apply, or `[Delay]`)
  - [ ] Let the plugin bind its own Apply hotkey (F9 is stored as code 88: `[ZPLUGIN:ZORBIT:APPLY,88]`)
    - [x] Docs and Studio say F9 needs no setup
    - [x] Tried the hotkey argument of `IButton` (`, , , 88`): Apply got no hotkey in 2022
    - [x] Now `[ISetHotkey, …Apply, 88]` at load when `[IGetHotkey]` is 0; `zscript_hotkey.log` shows the result
    - [x] Recompile `ZOrbitBridge.zsc` in ZBrush 2022 (commit it)
    - [x] With no stored binding, F9 applies picks in 2022. But the log says "at load: 0, now: 0": `IGetHotkey`
          reads 0 even after `ISetHotkey` worked, so the "already has a hotkey" guard may never hold
    - [ ] Check that a key the user binds and stores still wins over F9 (bind Alt+F9 or F10 and Store, restart).
          If it doesn't, drop the guard and say in the docs that a custom key needs F9 set there too, or
          read the stored key from `StartupHotkeys.txt` instead
    - [ ] Check 2023 and 2025 with the new `.zsc`
    - [ ] Restore 2022's own binding afterwards if wanted (`StartupHotkeys.txt.bak-zorbit`)
  - [x] Launching: through `ZFileUtils64.dll` (MacroData) and `ZOrbitData\*.lnk`; `ShellExecute` goes via
        cmd.exe and Windows Terminal (~7 s) and is only the fallback. Auto-start runs once per session.
  - [ ] Unverified ZScript details: `[Val]` on a set value
  - [ ] Test the UAC path with a ZBrush under Program Files
  - [x] The 2022-compiled `.zsc` works in 2023 and 2025 too
  - [ ] Slow fallback when request.txt is still there ~1 s after the bridge key (key not bound, or bound to
        another key): write the pick as a one-off script and run `ZBrush.exe <script>`. Covers the
        `IGetHotkey` guard question above too
    - [ ] First check in 2022 that `ZBrush.exe <script>` runs it in the open ZBrush, not a second instance
    - [ ] "Bridge didn't respond" warning only when the fallback also leaves request.txt behind
  - [ ] Uninstalling ZOrbit leaves the plugin in each ZBrush (it can't elevate): say so, or offer removal
  - [x] Docs: README requirements and troubleshooting, user guide section, CHANGELOG

## Later

- [ ] macOS support
  - Bridge: replace the WM_APP listener window and WM_TIMER retries with another IPC path.
  - App: global hotkey, ring overlay, tray (menu bar) and window handling are all Win32 today (`win32.py`, `ring.py`, `radiald.py`, `tray.py`, `studio.py`).
  - Hotkey and cursor tracking need the Accessibility permission.
  - Config path: `~/Library/Application Support` instead of `%APPDATA%`.
  - Packaging: `.dmg`/`.pkg` instead of Inno Setup. Unsigned apps hit Gatekeeper harder than SmartScreen, so this likely needs an Apple Developer account and notarization.

## Ideas

### Bridge

- [x] Brush picks note "(Edit mode is off)" from `Transform:Edit` (both bridges; the pick still goes through)
- [x] Delete a leftover `request.json`/`request.txt` when the bridge loads, so a pick from a crashed session
      can't run on the next Apply (both bridges)
  - [ ] ZScript side: recompile in 2022, install, check `[IGet, "Transform:Edit"]` and `FileDelete` there
  - [ ] Python side: reload in 2026 and check `bridge.log` ends with "bridge loaded" again
- [ ] ZBrush 2026 can move the user asset folder (Preferences > Asset Directory, `ZBRUSH_USER_ASSETS_DIR`).
      `brushes.zbrush_dirs()` reads only `userassets_path.txt`; have the bridge write
      `zbc.resolve_path("ZPLUGINDATA_")` to a file the app reads
- [ ] Check in ZBrush 2026 and 2022 that an imported alpha or texture gets a button named by its file stem (else
      every pick re-imports); check that `Texture:Import` takes .exr

### Ring

- [ ] Auto slots: unpinned slots refill from usage (decay with a ~2 week half-life; a newcomer must win twice
      in a row before it takes a slot, so the ring doesn't reshuffle). A simpler first step: a "Recent brushes" ring
- [ ] Right-click the open ring: Keep (pin), Remove, Hide, without opening Studio
- [x] More item kinds with library tabs and thumbnails: alpha (`Alpha:Import`), material (`Material:Load`),
      texture (`Texture:Import`). Same pattern as brushes: press the item if it is loaded, else
      `FileNameSetNext` + the Load button
- [ ] More item kinds: macro, load a tool/project/UI layout
  - [ ] Load project: an "always the newest" option that opens the latest file in a folder, so saving
        `Blockout_012` after `_011` needs no menu edit
- [ ] Capture item: save the viewport (`Document:Export`) as a timestamped PNG in a folder chosen in Studio
- [ ] Match ZBrush's interface colours: read `Preferences:IColors:*` in the bridge and offer them as a ring theme
- [ ] Per-slot glow colour; slot shapes (circle, rounded square); hub size; a "ring is full" message in Studio

### Tags and the browser

- [x] Alphas, materials and textures in the browser: `alpha:<path>` style item keys in `tags.json` (the store and
      keys already take other kinds), tabs in the browser and the Library, and the matching bridge actions
      (`Alpha:Import`, `Material:Load`, `Texture:Import`)
- [x] Favourites (a built-in star tag) and Recent in the browser
- [ ] Any / All toggle for the tag chips (they match any chosen tag today)
- [ ] A segmented slot border when a brush has several tags (only the first colours it now)
- [ ] Group same-tag slots: an option to draw a ring with each tag's slots side by side, so the band forms
      solid arcs (it would move slots, so it needs to be per menu and off by default)
- [ ] The tag band along a fan's arc (only the ring has it; a fan's slots take the tint and glow)
- [ ] Idle exit for the browser process: quit after a while unused and start again on the next press
- [ ] `ring.tag_limit`: change the 12-slot cap of a tag fan
- [x] Import and export tags (share a tag set or merge another `tags.json`)
- [ ] Favourites: manual drag-to-reorder and several named favourite tabs (XMD Toolbox style); a mini-mode strip of
      favourites over ZBrush

### Studio

- [x] First-run wizard: find ZBrush, pick eight brushes, try the ring once (Setup screen; brushes are a preview plus a hand-off to Menus)
- [ ] A short guided tour, offered on first run and under Help (Setup ends with a "What's where" step; the tour itself is not done)
- [ ] Reorder the Settings cards: Ring geometry, Colours, Labels, Tag colours (the look); Open animation, Behaviour
      (the feel); Brush browser, ZBrush bridge; then the cards that save straight away: Older ZBrush, Tags,
      Studio. Do it by sorting the built cards by name before the "On this page" list is made, not by moving
      their code, and put the same order in the Settings row of the user guide's Studio table. Import and export
      comes last, after Studio. Optionally a
      **Manage tags...** button in the Tag colours card

### macOS notes

- Ask for Accessibility once and show its state on the Status screen
- Open the ring over ZBrush without bringing our app to the front; watch for stuck modifiers and non-Latin
  input sources
- ZScript on a Mac: `FileNameSetNext` needs a `!:` prefix on paths; ZBrush 2023+ needs the universal
  `ZFileUtilsU.lib`
- Ship separate Apple Silicon and Intel builds, signed and notarized
