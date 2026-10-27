<h1>
  <img src="assets/icon-256.png" alt="" width="48" align="absmiddle">
  ZOrbit
</h1>

ZOrbit is a radial brush menu for ZBrush. Press **Q** over ZBrush and a ring of your favourite brushes and buttons appears around the cursor. Flick toward one and let go, and ZBrush switches to it. You choose what goes on the ring in a small editor called ZOrbit Studio. It is free, open source (GPL-3.0), and runs on Windows.

If you know pie menus from Blender or marking menus from Maya, ZOrbit brings that to ZBrush.

<p align="center">
  <img src="docs/images/open-animation.gif" alt="Holding Q: the ring opens around the cursor, the cursor hovers two brushes, the More Brushes submenu opens on hover, and a flick picks ClayTubes" width="550">
</p>

## Features

- **Fast picking.** Hold the hotkey and flick past a slot, or move toward it and release. Or tap the hotkey and click.
- **More than brushes.** A slot can select a brush, press any ZBrush button, set a slider, flip a switch, run several of those in a row, or open another ring.
- **Submenus.** Rings can open other rings, so a handful of hotkeys can reach a lot. Hover a submenu and it opens on the spot, so one stroke can reach an item two rings deep.
- **Fan-out submenus.** Switch a menu to fan out and it opens in place: its items spread in an arc beyond its slot while the ring you came from stays put. Fans can open fans, up to three deep.
- **ZOrbit Studio.** Edit menus with a live preview of the real ring. Drag brushes in from a searchable library with thumbnails, record hotkeys, change colours, size and animation.
- **Twelve open animations**, from instant to a swirling spiral, plus ring size, dead zone and label options.
- **Starts and stops with ZBrush.** There is nothing to launch by hand.
- **Safe with your stroke.** A pick that arrives mid-stroke waits until you lift the pen.
- **High-DPI and multi-monitor aware.** The ring stays on screen, even at the screen edge.
- **Plain JSON menus** in `%APPDATA%\ZOrbit\radial.json`, so you can back them up, share them and keep them in version control.

<p align="center">
  <img src="docs/images/ring.png" alt="Brushes menu with ClayBuildup hovered" width="600">
</p>

### Fan-out submenus

A submenu can open as a fan instead of a new ring. Turn on **Fan out when opened from another menu** in the menu's settings in Studio (or give the menu `"fan": true`). Hover its slot and the items spread out beyond it, joined by dashed lines, with the ring you came from still in place. Release over an item, click it, or flick past it to pick it. An item in a fan can be a fan submenu too, so one stroke can run three fans deep. Near a screen edge, where there is no room, the submenu opens as a ring as before.

<p align="center">
  <img src="docs/images/fan-out.gif" alt="Holding Q: hovering More Brushes fans its brushes out to the left; moving to Tools fans out its switches, SubDivide fans out its sizes above that, and a flick past 1.00 picks it" width="520">
</p>

## Requirements

- Windows 10 or 11
- ZBrush 2022 or newer. ZBrush 2026 and newer load the Python plugin that the installer sets up. ZBrush 2022 to 2025 have no Python API, so they get a ZScript plugin, which you install from Studio (see [ZBrush 2022 to 2025](#zbrush-2022-to-2025)).
- The Microsoft Edge WebView2 runtime, which Studio uses for its window. It is part of Windows 11 and of up-to-date Windows 10.

## Install

1. Download the installer from the [Releases page](https://github.com/combwizard/zorbit/releases).
2. Run it. It installs for your user only and does not need administrator rights. It adds the plugin folder to your `ZBRUSH_PLUGIN_PATH` user environment variable and creates a Start menu shortcut called **ZOrbit Studio**.
3. **Restart ZBrush once.** ZBrush reads `ZBRUSH_PLUGIN_PATH` only when it starts.
4. Open a canvas, hover over it and press **Q**.

The first run puts a starter set of menus in `%APPDATA%\ZOrbit\radial.json`. They use only brushes that come with ZBrush.

### Upgrading from Radial Menu for ZBrush

ZOrbit used to be called Radial Menu for ZBrush. Run the new installer over the old install. It moves the program to `%LOCALAPPDATA%\Programs\ZOrbit` and removes the old folder, its Start menu shortcut and its plugin path entry. Your menus and settings are copied to `%APPDATA%\ZOrbit` on the first start, and learned auto slots to `%LOCALAPPDATA%\ZOrbit`. The old `RadialMenu` folders stay where they are; you can delete them.

In ZBrush 2026 the palette is now **Zplugin > ZOrbit**. If you bound F9 to the old **Apply** by hand, bind it again on **Zplugin > ZOrbit > Apply**: Ctrl+Alt+click it, press **F9**, then **Preferences > Hotkeys > Store**. In ZBrush 2022 to 2025, Studio shows the old plugin as **Update available**. **Update** replaces it with the ZOrbit plugin.

### ZBrush 2022 to 2025

These versions load plugins only from their own `ZStartup\ZPlugs64` folder, so Studio puts the plugin there:

1. Open **ZOrbit Studio** and go to **Settings > Older ZBrush**. It lists the 2022 to 2025 versions it found. If yours is missing, use **Add a ZBrush folder**.
2. Click **Install**. A ZBrush under Program Files asks for administrator rights once.
3. Restart that ZBrush.

The plugin has no listener window, so every pick in these versions goes through the bridge key, F9. The plugin binds F9 to **Zplugin > ZOrbit > Apply** itself, so there is nothing to set up. If you change the bridge key in Studio, bind the new key by hand in each version: Ctrl+Alt+click **Apply**, press the key, then **Preferences > Hotkeys > Store**. When a new version of ZOrbit has a newer plugin, **Settings** shows a badge and the row says **Update available**.

### Windows says "Windows protected your PC"

The installer is not code-signed yet. Code-signing certificates cost money every year, and this is a free hobby project, so Windows SmartScreen shows its warning for any program it does not recognise. The warning does not mean it found a problem.

To continue, click **More info**, then **Run anyway**. If you would rather not run a binary you did not build, the whole source is in this repository and [Build from source](#build-from-source) explains how to make the installer yourself.

## First steps

1. Open **ZOrbit Studio** from the Start menu (or from ZBrush: **Zplugin > ZOrbit > Studio**).
2. On the **Menus** screen, pick a menu on the left. The ring preview in the middle is drawn by the same code that draws it inside ZBrush.
3. Drag brushes from the **Library** onto the ring, or use **Add item** for buttons, sliders and switches.
4. Click **Save** (Ctrl+S). The next time you open the ring in ZBrush it uses your changes. There is no need to restart anything.

<p align="center">
  <img src="docs/images/studio.png" alt="ZOrbit Studio: the menu list, the ring preview and the brush library">
</p>

The [user guide](docs/user-guide.md) covers every setting and item type.

## Uninstall

Open **Windows Settings > Apps > Installed apps**, find **ZOrbit** and choose **Uninstall**. Restart ZBrush afterwards so it lets go of the plugin.

The uninstaller cannot reach the plugin inside a ZBrush 2022 to 2025. Remove it first with **Studio > Settings > Older ZBrush > Remove**, or afterwards by deleting `ZOrbitBridge.zsc` and the `ZOrbitData` folder from that ZBrush's `ZStartup\ZPlugs64`.

Your menus and logs are not part of the program. They live in `%APPDATA%\ZOrbit` and `%LOCALAPPDATA%\ZOrbit`; delete those folders if you want no trace.

## Build from source

You need Windows, Python 3.12 and the packages in `requirements-dev.txt`.

```powershell
pip install -r requirements-dev.txt
.\packaging\build.ps1
```

The script's header lists what else it needs and where the installer ends up.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.

## How it works

ZOrbit has two halves.

- **The app** (`zorbit\`) runs outside ZBrush. A keyboard hook watches for your menu hotkeys, but only while ZBrush is the front window. When one is pressed it draws the ring in a window that never takes focus, so ZBrush keeps working underneath.
- **The bridge** (`bridge\zorbit_bridge.py`) runs inside ZBrush as a Python plugin. It adds the **Zplugin > ZOrbit** palette, starts the app, and carries out picks by calling ZBrush's own commands.

When you pick a slot, the app writes the request to a small file and posts a Windows message to a hidden listener window the bridge keeps inside ZBrush. The bridge reads the file and does the work on ZBrush's main thread. If the listener is not available, the app can press a fallback key (F9) that you bind to **Zplugin > ZOrbit > Apply**.

ZBrush 2022 to 2025 have no Python API, so for them the bridge is a ZScript plugin (`bridge\zscript\`) with the same palette. ZScript cannot host a listener window, so the app always presses the bridge key there. The app also writes each pick in a plain line-by-line form that ZScript can read, and loads brushes from that ZBrush version's own files.

The app exits when ZBrush does.

## Troubleshooting

**Nothing happens when I press Q.**
Make sure ZBrush is the front window. Then in ZBrush open **Zplugin > ZOrbit > Status**. It should say the listener is verified and the app is running. If the palette is missing, ZBrush did not load the plugin: restart it, and check that `ZBRUSH_PLUGIN_PATH` (in Windows' environment variables, user section) contains the bridge folder.

**The ring opens but picks do nothing.**
Open **Zplugin > ZOrbit > Status** and check that the listener says "verified". Look at `bridge.log`, which shows exactly what ZBrush did with each pick. Failed items are listed there, for example a button path that does not exist.

**Use the fallback key.**
In ZBrush, Ctrl+Alt+click **Zplugin > ZOrbit > Apply**, press **F9**, then store it in **Preferences > Hotkeys > Store**. With the bridge mode on `auto` (the default), ZOrbit presses F9 when the listener does not answer.

**ZBrush 2022 to 2025: the ring opens, but picks do nothing.**
Picks there only arrive through the bridge key. Hover **Zplugin > ZOrbit > Apply**: its hotkey should match the bridge key in Studio (F9 unless you changed it). If **Settings > Older ZBrush** says **Update available**, update the plugin; older plugins don't bind F9 themselves. If you use another key, bind it to **Apply** and click **Preferences > Hotkeys > Store**; a binding that was not stored is gone after a restart. `zscript_bridge.log` shows what the last pick did.

**Logs.**
`%LOCALAPPDATA%\ZOrbit` holds `radiald.log` (the app), `bridge.log` (ZBrush side), `zscript_bridge.log` (ZBrush 2022 to 2025: the last pick), `studio.log` (how Studio started) and `app_stderr.log` (crashes at startup). Studio's **Status** screen shows the tail of the app log and has a button that opens the folder.

**Windows protected your PC.**
See [above](#windows-says-windows-protected-your-pc).

More is in the [user guide](docs/user-guide.md#troubleshooting).

## Licence

| | |
|---|---|
| **Licence key** | `FCKGW-RHQQ2-YXRKT-8TG6W-2B7Q8` |
| **Status** | Activated |
| **Seats** | All of them |
| **Expires** | Never |
| **Price** | 0.00 |

**Just kidding.** There is no licence key, no account, no trial and no expiry date. ZOrbit is licensed under the **GNU General Public License v3.0** (see [LICENSE](LICENSE)): free to use on as many machines as you like, to study, change and share. It stays free: if you distribute a modified version, you must also publish its source under the same licence. You are licensed. Forever.

(The Studio has the same Licence screen. Its buttons work exactly as well as this table does. Not amused? Hide it with the link at the bottom of that page, or in Settings > Studio.)

Third-party components and their licences are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

ZOrbit is an independent project. It is not affiliated with or endorsed by Maxon. ZBrush is a trademark of Maxon.
