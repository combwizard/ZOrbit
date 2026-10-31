# Troubleshooting

Entries are grouped by what you see. Studio's **Setup** screen (Alt+5) is the quickest first check: it looks at ZBrush, the plugin and the app, and says which step is missing. The log files named below are listed under [Logs](#logs).

## Installing

### Windows protected your PC

The installer is not code-signed yet. Click **More info**, then **Run anyway**. [Install and uninstall](install.md#windows-says-windows-protected-your-pc) says why.

### The portable version stops at startup with "Failed to resolve Python.Runtime.Loader.Initialize"

Windows marked the unzipped files as downloaded, and ZOrbit could not remove the mark, usually because it is in a folder it cannot write to. Close ZOrbit, right-click the zip, choose **Properties**, tick **Unblock**, and unzip it again into a folder of your own, such as one under `Documents`.

### I upgraded from Radial Menu for ZBrush and F9 stopped working

The palette was renamed, so a hotkey you bound by hand to the old **Apply** does not carry over in ZBrush 2026. Ctrl+Alt+click **Zplugin > ZOrbit > Apply**, press **F9**, then click **Preferences > Hotkeys > Store**. ZBrush 2022 to 2025: update the plugin in **Studio > Setup** step 1 (or **Settings > Older ZBrush** in Full mode); it binds F9 if **Apply** has no hotkey. Your menus were copied from `%APPDATA%\RadialMenu` to `%APPDATA%\ZOrbit` on the first start, and learned auto slots from `%LOCALAPPDATA%\RadialMenu`. The old folders are left in place; you can delete them.

## The ring does not open

### Pressing the hotkey does nothing

1. Open Studio's **Setup** screen (Alt+5). It checks ZBrush, the plugin and the app, and says which step is missing. An amber dot on its button in the rail means a check is failing.

    ![The Setup screen with ZBrush found ticked, and the Plugin loaded in ZBrush step waiting: ZBrush 2026 shows Restart ZBrush because it was started before the plugin was set up](images/setup-restart.png)

2. Is ZBrush the front window? The hotkey is ignored everywhere else.
3. In ZBrush, open **Zplugin > ZOrbit**. If the palette is missing, ZBrush did not load the plugin. On Studio's **Setup** screen, press **Fix** next to your ZBrush if it shows that button, then restart ZBrush. If there is no **Fix**, or the palette is still missing, the next steps depend on your version:
    - **ZBrush 2026 and newer:** the plugin folder (`<install folder>\bridge`, the one that holds `zorbit_bridge.py`) must be in your user environment variable `ZBRUSH_PLUGIN_PATH` (in Windows' environment variables, user section). As a one-off you can also load `zorbit_bridge.py` with **ZScript > Python Scripting > Load**. **Zplugin > ZOrbit > Status** should say the listener is verified and the app is running. If the plugin failed while starting, `bridge.log` (in `%LOCALAPPDATA%\ZOrbit`) holds the error, after a line that says "the plugin could not start". Its listener line says whether the listener is up.
    - **ZBrush 2022 to 2025:** the **Zplugin > ZOrbit** palette comes from the ZScript plugin, not from `ZBRUSH_PLUGIN_PATH`. If it is missing, install the plugin from the **Setup** screen or from **Settings > Older ZBrush** (Full mode), then restart that ZBrush. `zscript_launch.log` and `zscript_bridge.log` (in `%LOCALAPPDATA%\ZOrbit`) show whether the plugin started the app and what the last pick did. See also [ZBrush 2022 to 2025: the ring opens, but picks do nothing](#zbrush-2022-to-2025-the-ring-opens-but-picks-do-nothing).
4. If the status says the app is not running, press **Start App**, then read `app_stderr.log` and `radiald.log`.
5. In Studio, check for the **problems** pill. A menu with no usable items, a duplicate hotkey or a hotkey the app cannot read all stop a ring from opening.
6. Another program may grab the same key before it reaches the app. Try a different hotkey.
7. Is ZBrush running as administrator? The app cannot read an elevated program's process, so it cannot tell that ZBrush is the front window, and it ignores the hotkey. `radiald.log` then says "zbrush.exe (pid 1234) could not be read, so it is probably running as administrator; hotkeys ignored in it", or, when the front window is the one it cannot read, "foreground window's process could not be read (is ZBrush running as administrator?); hotkeys ignored". Start ZBrush without "Run as administrator".
8. Typing is affected too. A menu hotkey is swallowed in ZBrush's text fields (a rename box, a file name), so a plain letter such as **Q** cannot be typed there while a menu uses it. Use a key you do not type, add a modifier, or turn off **Swallow hotkey** for that menu.

## Picks do nothing

### The ring opens, but picks do nothing

When the app knows why a pick went nowhere, it shows a short message near the cursor for about two seconds. It never takes the focus and never shows for a pick that worked. The messages are:

- **No connection to ZBrush's plugin. Check Zplugin > ZOrbit > Status.** The bridge mode is `message` and the app found no live plugin in that ZBrush. Start ZBrush, or load the plugin.
- **The plugin did not answer. Check Zplugin > ZOrbit > Status.** The plugin was there, but did not pick the request up within half a second, and there is no bridge key to fall back on.
- **ZBrush was not the front window, nothing sent.** The pick needed the bridge key, and the key is only pressed while ZBrush is in front. Do not click another program right after you pick.
- **No bridge key is set. Check Settings > ZBrush bridge.** The pick needed the bridge key and none is set.
- **This slot is empty.** You picked an auto slot nothing has filled yet, or a tag slot whose tag has no items.
- **That menu has nothing usable in it.** You picked a submenu whose items are all empty or unusable.
- **A name followed by "could not be found in ZBrush"** or **"is not a ZBrush button"**, or **ZBrush could not carry out that pick. See bridge.log.** The plugin picked the request up and reported a problem: the brush, alpha, material or texture is not installed, the `press`, `set` or `toggle` path does not exist, or ZBrush raised an error. `bridge.log` has the details.

If you see no message and nothing happens, work through the steps below.

On Studio's **Status** screen, the listener card should say **Connected**. In ZBrush, **Zplugin > ZOrbit > Status** should say "verified". If it is not, use the fallback: [bind the bridge key](#use-or-test-the-fallback-key) and leave the mode on `auto`. Then read `bridge.log`; it names each action and says whether it worked. Common causes: a `press`, `set` or `toggle` path that does not exist in your ZBrush (logged as "no such interface item"), or a `brush`, `alpha`, `material` or `texture` whose file ZOrbit cannot find (logged as "NOT loaded in ZBrush and no file known"). A brush you saved after ZOrbit started is found anyway: when a name is missing, ZOrbit looks through your brush, alpha, material and texture folders again before it gives up (at most once every five seconds).

### ZBrush 2022 to 2025: the ring opens, but picks do nothing

Picks there only arrive through the bridge key. Hover **Zplugin > ZOrbit > Apply** in that ZBrush: its hotkey should match the bridge key in Studio (F9 unless you changed it). The plugin binds F9 itself when **Apply** has no hotkey, but only once it is up to date, so update it if **Setup** step 1 (or **Settings > Older ZBrush** in Full mode) says **Update available**. For any other key, check that it is bound to **Apply** and that you clicked **Preferences > Hotkeys > Store**; a binding that was not stored is gone after a restart. If the palette is missing, install the plugin again from **Studio > Setup** step 1 and restart that ZBrush. `zscript_bridge.log` shows what the last pick did.

Messages Studio can give when you install the plugin:

- **Installed without the start shortcuts (PowerShell is restricted here).** The plugin is installed and works, but starts ZOrbit the slower way. `ZOrbitData\install.txt` in that ZBrush's `ZStartup\ZPlugs64` says why the shortcuts failed. Restart ZBrush; nothing else is needed.
- **The ZBrush 2022 to 2025 plugin cannot find ZOrbit's data folder from this account.** The path of `%LOCALAPPDATA%\ZOrbit` has characters outside the Windows code page and 8.3 short names are off, so ZScript cannot read it. Move the data folder, or turn on 8.3 names (`fsutil 8dot3name set 0` as administrator), then install again.
- **ZBrush 2021 is not supported (2022 or newer).** Older versions cannot use the plugin.

### Use or test the fallback key

In ZBrush, Ctrl+Alt+click **Zplugin > ZOrbit > Apply**, press **F9**, then store it in **Preferences > Hotkeys > Store**. With the bridge mode on `auto` (the default), ZOrbit presses F9 when the listener does not answer. The rules for the key and the other modes are in [How picks reach ZBrush](bridge.md#how-picks-reach-zbrush-bridge-modes).

To test it, set `"mode": "key"` temporarily, pick something, and check `bridge.log` for the result. Switch back to `auto` afterwards.

### Picks feel late during a stroke

In ZBrush 2026 and newer that is intended. A pick waits until you release the mouse button or lift the pen, so a tool change never lands in the middle of a stroke. The bridge key fallback waits too: it is pressed half a second after you lift. ZBrush 2022 to 2025 cannot wait. Their plugin applies a pick as soon as the bridge key arrives, even in the middle of a stroke.

## The browser

### The browser does not appear

1. Is ZBrush (or the browser itself) the front window? The browser hotkey is ignored everywhere else. The tray menu, Studio's **Browser** button and the Start menu shortcut work from anywhere.
2. Does your `radial.json` have a `browser` hotkey (new installs have Alt+B)? Check **Settings > Browser**. If a menu uses the same key, the menu wins and the problems pill says so. A **Browser** slot on a ring opens it too.
3. After the app starts, the browser needs a few seconds to be ready. The first press can take a moment when it was not started in advance. If it is open but you cannot see it, it may be behind other windows (Keep on top is off): press the hotkey, or open it from the tray menu. A browser left on a screen you have since unplugged is brought back onto a screen the next time it opens.
4. Read `radiald.log` (lines that start with `browser`, and `popout exited with code N` when the browser stopped) and `popout.log`. Without the Microsoft Edge WebView2 runtime the browser cannot open: it shows **ZOrbit needs the Microsoft Edge WebView2 runtime for this window** with the download link, and `popout.log` says so. Install the runtime and press the hotkey again. Any other failure while it starts is written to `popout.log` as a traceback; send that with your report.

### The browser is empty

The browser and the Library read the folders of a ZBrush that has run at least once. When either says **ZBrush was not found**, the list stays empty until ZOrbit finds one. In Studio, the Library's message has a **Find ZBrush in Studio** button that opens Setup. In the browser window, open Studio from the tray icon or the Start menu and go to **Setup**.

### The browser opens but does not take the keyboard

Click the search box once. If you have to do that every time, send `popout.log` and the `browser` lines of `radiald.log`.

### A pick in the browser does nothing

After a pick, read the toast. A toast that says **Sent X to ZBrush** (X is the item's name) means the app took the pick, and `bridge.log` says what ZBrush did with it. **ZOrbit is not running. It starts and stops with ZBrush.** means the browser found no app window: start ZBrush, and the app starts with it. **ZOrbit did not answer. Try again in a moment.** means the app's window exists but did not answer within half a second. `popout.log` has a line `pick ... app window ..., result ...` for each pick.

In `radiald.log`, look for `pick from browser`. If it says the pick was dropped because ZBrush did not get the focus back in 2 s, you are in ZBrush 2022 to 2025, which can only take a pick through the bridge key while ZBrush is the front window: do not click another program right after you pick. Check that the app is running on the Status screen if the toast says it is not.

## Slots and tags

### A tag slot is faint and does nothing

No installed item carries that tag, or the tag no longer exists (the problems pill says which). Tag some items in the Library, or point the slot at another tag.

### My slots are not coloured by tag

Check **Settings > Tag colours** (Full mode): the **Icon tint**, **Glow** and **Band** switches may all be off. Only an item's first tag colours its slot, and an item with no tag is not coloured. A change made by hand to `tags.json` shows within a moment.

### A slot shows letters instead of a picture

Letters mean ZOrbit could not read a picture for the slot. The item still works when you pick it. For a brush, either no `.zbp` was found for the name, or its icon is in a format ZOrbit does not know. A material with no icon in its `.zmt` file (some old MatCap files) and an EXR texture show letters too. For other items it is the normal placeholder; set an `icon` to change it.

## Studio

### I cannot find a setting in Studio

Studio may be in Simple mode, which hides some settings and item types. Press **Full** in the top bar. A hidden setting keeps its value, so nothing is lost by switching. If a Full-only setting is not at its default, the top of the Settings page names it and has a **Switch to Full mode** link. [Simple and Full mode](studio.md#simple-and-full-mode) lists what each mode shows.

## Your menus file

### I broke my menus file

Studio keeps the last version as `radial.json.bak`. If you edit the file by hand and the app cannot read it, it keeps using the last good version and logs the error. It also shows a balloon from the tray icon, **ZOrbit cannot read your menus file**, once for each saved version of the file, and the tray icon's tooltip says the menus file cannot be read until the file loads again. **Reload menus** in the tray menu shows the reason in a balloon. When Studio cannot read it either, it opens on a recovery screen that shows the error with its line and column, and has these buttons:

- **Open folder** opens the folder that holds `radial.json`.
- **Open logs folder** opens the logs folder.
- **Restore backup** replaces the file with `radial.json.bak`. It only appears when that file exists. The file it replaces is kept as `radial.json.broken`, so you can open it in a text editor and recover what you need.
- **Start from defaults** replaces the file with the built-in menus, after a confirmation. The unreadable file is kept as `radial.json.broken`.
- **Try again** reloads Studio, for when you have fixed the file by hand.

The rail and the **Alt+1** to **Alt+5** keys do nothing, and the rail is dimmed, until the file loads. Nothing is changed or saved until you choose a button.

A section of the wrong type, for example `"ring": "big"`, is reported with the section name, and the defaults are used for it. A brush, alpha, material or texture name may not contain `\ / :` or `..`, and an `icon` may not point at a network path; the problem names the item, and a bad name skips the item. A byte-order mark left by an editor is accepted. Deleting `radial.json` makes the app create a fresh one from the starter menus.

If the file cannot be read when the app starts, the app still starts: the tray icon appears, no ring opens, and `radiald.log` says "cannot load radial.json" with the reason. Fix the file in Studio or by hand; the app reads it again as soon as it changes. **Reload menus** in the tray menu logs "tray: reload failed" with the reason when the file is still unreadable.

A setting name ZOrbit does not know, such as `raduis` for `radius` in `ring` or `itmes` in a menu, is listed as a problem and ignored, with a "did you mean" when a known name is close. A `swallow` that is not `true` or `false` is a problem too, and counts as `true`. A submenu slot that points at a menu with no usable items is listed and skipped.

### Checking a file from a source checkout

`python zorbit\main.py --check` prints every menu and lists problems without starting anything.

## Logs

`%LOCALAPPDATA%\ZOrbit` holds `radiald.log` (the app), `bridge.log` (ZBrush side), `zscript_bridge.log` (ZBrush 2022 to 2025: the last pick), `studio.log` (how Studio started), `popout.log` (the browser) and `app_stderr.log` (crashes at startup). Studio's **Status** screen shows the tail of the app log and has a button that opens the folder. [Files, backups and logs](files.md#files-and-logs) lists every file ZOrbit keeps.
