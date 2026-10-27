# TODO

## Next

- [ ] Support ZBrush 2022–2025 (ZScript bridge in `bridge/zscript/`, Studio: Settings > Older ZBrush)
  - [x] Compile `RadialMenuBridge.txt` in ZBrush 2022 (commit the `.zsc` with the source)
  - [x] 2022: palette loads, Studio install, F9 Apply selects a loaded brush
  - [ ] 2022: load a brush that isn't loaded yet, press/set/toggle, steps, Status, Studio button
  - [ ] Let the plugin bind its own Apply hotkey (F9 is stored as code 88: `[ZPLUGIN:RADIAL MENU:APPLY,88]`)
    - [x] Docs and Studio say F9 needs no setup
    - [x] Tried the hotkey argument of `IButton` (`, , , 88`): Apply got no hotkey in 2022
    - [x] Now `[ISetHotkey, …Apply, 88]` at load when `[IGetHotkey]` is 0; `zscript_hotkey.log` shows the result
    - [x] Recompile `RadialMenuBridge.zsc` in ZBrush 2022 (commit it)
    - [x] With no stored binding, F9 applies picks in 2022. But the log says "at load: 0, now: 0": `IGetHotkey`
          reads 0 even after `ISetHotkey` worked, so the "already has a hotkey" guard may never hold
    - [ ] Check that a key the user binds and stores still wins over F9 (bind Alt+F9 or F10 and Store, restart).
          If it doesn't, drop the guard and say in the docs that a custom key needs F9 set there too, or
          read the stored key from `StartupHotkeys.txt` instead
    - [ ] Check 2023 and 2025 with the new `.zsc`
    - [ ] Restore 2022's own binding afterwards if wanted (`StartupHotkeys.txt.bak-radialmenu`)
  - [x] Launching: through `ZFileUtils64.dll` (MacroData) and `RadialMenuData\*.lnk`; `ShellExecute` goes via
        cmd.exe and Windows Terminal (~7 s) and is only the fallback. Auto-start runs once per session.
  - [ ] Unverified ZScript details: `[Val]` on a set value
  - [ ] Test the UAC path with a ZBrush under Program Files
  - [x] The 2022-compiled `.zsc` works in 2023 and 2025 too
  - [ ] Slow fallback when request.txt is still there ~1 s after the bridge key (key not bound, or bound to
        another key): write the pick as a one-off script and run `ZBrush.exe <script>`. Covers the
        `IGetHotkey` guard question above too
    - [ ] First check in 2022 that `ZBrush.exe <script>` runs it in the open ZBrush, not a second instance
    - [ ] "Bridge didn't respond" warning only when the fallback also leaves request.txt behind
  - [ ] Uninstalling Radial Menu leaves the plugin in each ZBrush (it can't elevate): say so, or offer removal
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

### Ring

- [ ] Auto slots: unpinned slots refill from usage (decay with a ~2 week half-life; a newcomer must win twice
      in a row before it takes a slot, so the ring doesn't reshuffle). A simpler first step: a "Recent brushes" ring
- [ ] Right-click the open ring: Keep (pin), Remove, Hide, without opening Studio
- [ ] More item kinds with library tabs and thumbnails: alpha (`Alpha:Import`), material (`Material:Load`),
      texture (`Texture:Import`), macro, load a tool/project/UI layout. Same pattern as brushes: press the
      item if it is loaded, else `FileNameSetNext` + the Load button
  - [ ] Load project: an "always the newest" option that opens the latest file in a folder, so saving
        `Blockout_012` after `_011` needs no menu edit
- [ ] Capture item: save the viewport (`Document:Export`) as a timestamped PNG in a folder chosen in Studio
- [ ] Match ZBrush's interface colours: read `Preferences:IColors:*` in the bridge and offer them as a ring theme
- [ ] Per-slot glow colour; slot shapes (circle, rounded square); hub size; a "ring is full" message in Studio

### Studio

- [ ] First-run wizard: find ZBrush, pick eight brushes, try the ring once
- [ ] A short guided tour, offered on first run and under Help

### macOS notes

- Ask for Accessibility once and show its state on the Status screen
- Open the ring over ZBrush without bringing our app to the front; watch for stuck modifiers and non-Latin
  input sources
- ZScript on a Mac: `FileNameSetNext` needs a `!:` prefix on paths; ZBrush 2023+ needs the universal
  `ZFileUtilsU.lib`
- Ship separate Apple Silicon and Intel builds, signed and notarized
