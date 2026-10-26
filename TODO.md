# TODO

## Next

- [ ] Support ZBrush 2022–2025 (ZScript bridge in `bridge/zscript/`, Studio: Settings > Older ZBrush)
  - [x] Compile `RadialMenuBridge.txt` in ZBrush 2022 (commit the `.zsc` with the source)
  - [x] 2022: palette loads, Studio install, F9 Apply selects a loaded brush
  - [ ] 2022: load a brush that isn't loaded yet, press/set/toggle, steps, Status, Studio button
  - [ ] Let the plugin bind its own Apply hotkey (F9 is stored as code 88: `[ZPLUGIN:RADIAL MENU:APPLY,88]`)
  - [x] Launching: through `ZFileUtils64.dll` (MacroData) and `RadialMenuData\*.lnk`; `ShellExecute` goes via
        cmd.exe and Windows Terminal (~7 s) and is only the fallback. Auto-start runs once per session.
  - [ ] Unverified ZScript details: `[Val]` on a set value
  - [ ] Test the UAC path with a ZBrush under Program Files
  - [x] The 2022-compiled `.zsc` works in 2023 and 2025 too
  - [ ] "Bridge didn't respond" warning when request.txt is still there ~3 s after the key
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
