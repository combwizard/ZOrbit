<h1>
  <img src="assets/icon-256.png" alt="" width="48" align="absmiddle">
  Radial Menu for ZBrush
</h1>

Press **Q** over ZBrush and a ring of your favourite brushes and buttons appears around the cursor. Flick toward one and let go, and ZBrush switches to it. You choose what goes on the ring in a small editor called Radial Menu Studio. It is free, open source (GPL-3.0), and runs on Windows.

<p align="center">
  <img src="docs/images/open-animation.gif" alt="The ring opening around the cursor, then hovering a brush" width="447">
</p>

## Features

- **Fast picking.** Hold the hotkey, move toward a slot, release. Or tap the hotkey and click.
- **More than brushes.** A slot can select a brush, press any ZBrush button, set a slider, flip a switch, run several of those in a row, or open another ring.
- **Submenus.** Rings can open other rings, so a handful of hotkeys can reach a lot.
- **Radial Menu Studio.** Edit menus with a live preview of the real ring. Drag brushes in from a searchable library with thumbnails, record hotkeys, change colours, size and animation.
- **Twelve open animations**, from instant to a swirling spiral, plus ring size, dead zone and label options.
- **Starts and stops with ZBrush.** There is nothing to launch by hand.
- **Safe with your stroke.** A pick that arrives mid-stroke waits until you lift the pen.
- **High-DPI and multi-monitor aware.** The ring stays on screen, even at the screen edge.
- **Plain JSON menus** in `%APPDATA%\RadialMenu\radial.json`, so you can back them up, share them and keep them in version control.

![Brushes menu with ClayBuildup hovered](docs/images/ring.png)

## Requirements

- Windows 10 or 11
- ZBrush 2022 or newer. ZBrush 2026 and newer load the Python plugin that the installer sets up. ZBrush 2022 to 2025 have no Python API, so they get a ZScript plugin, which you install from Studio (see [ZBrush 2022 to 2025](#zbrush-2022-to-2025)).
- The Microsoft Edge WebView2 runtime, which Studio uses for its window. It is part of Windows 11 and of up-to-date Windows 10.

## Install

1. Download the installer from the [Releases page](https://github.com/combwizard/zbrush-radial-menu/releases).
2. Run it. It installs for your user only and does not need administrator rights. It adds the plugin folder to your `ZBRUSH_PLUGIN_PATH` user environment variable and creates a Start menu shortcut called **Radial Menu Studio**.
3. **Restart ZBrush once.** ZBrush reads `ZBRUSH_PLUGIN_PATH` only when it starts.
4. Open a canvas, hover over it and press **Q**.

The first run puts a starter set of menus in `%APPDATA%\RadialMenu\radial.json`. They use only brushes that come with ZBrush.

### ZBrush 2022 to 2025

These versions load plugins only from their own `ZStartup\ZPlugs64` folder, so Studio puts the plugin there:

1. Open **Radial Menu Studio** and go to **Settings > Older ZBrush**. It lists the 2022 to 2025 versions it found. If yours is missing, use **Add a ZBrush folder**.
2. Click **Install**. A ZBrush under Program Files asks for administrator rights once.
3. Restart that ZBrush.
4. Bind the bridge key: Ctrl+Alt+click **Zplugin > Radial Menu > Apply**, press **F9**, then **Preferences > Hotkeys > Store**. Each ZBrush version keeps its own hotkeys, so do this once per version, and don't skip **Store**.

The plugin has no listener window, so every pick in these versions goes through the bridge key. When a new Radial Menu has a newer plugin, **Settings** shows a badge and the row says **Update available**.

### Windows says "Windows protected your PC"

The installer is not code-signed yet. Code-signing certificates cost money every year, and this is a free hobby project, so Windows SmartScreen shows its warning for any program it does not recognise. The warning does not mean it found a problem.

To continue, click **More info**, then **Run anyway**. If you would rather not run a binary you did not build, the whole source is in this repository and [Build from source](#build-from-source) explains how to make the installer yourself.

## First steps

1. Open **Radial Menu Studio** from the Start menu (or from ZBrush: **Zplugin > Radial Menu > Studio**).
2. On the **Menus** screen, pick a menu on the left. The ring preview in the middle is drawn by the same code that draws it inside ZBrush.
3. Drag brushes from the **Library** onto the ring, or use **Add item** for buttons, sliders and switches.
4. Click **Save** (Ctrl+S). The next time you open the ring in ZBrush it uses your changes. There is no need to restart anything.

The [user guide](docs/user-guide.md) covers every setting and item type.

## Uninstall

Open **Windows Settings > Apps > Installed apps**, find **Radial Menu for ZBrush** and choose **Uninstall**. Restart ZBrush afterwards so it lets go of the plugin.

The uninstaller cannot reach the plugin inside a ZBrush 2022 to 2025. Remove it first with **Studio > Settings > Older ZBrush > Remove**, or afterwards by deleting `RadialMenuBridge.zsc` and the `RadialMenuData` folder from that ZBrush's `ZStartup\ZPlugs64`.

Your menus and logs are not part of the program. They live in `%APPDATA%\RadialMenu` and `%LOCALAPPDATA%\RadialMenu`; delete those folders if you want no trace.

## Build from source

You need Windows, Python 3.12 and the packages in `requirements-dev.txt`.

```powershell
pip install -r requirements-dev.txt
.\packaging\build.ps1
```

The script's header lists what else it needs and where the installer ends up.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.

## How it works

Radial Menu has two halves.

- **The app** (`radial_menu\`) runs outside ZBrush. A keyboard hook watches for your menu hotkeys, but only while ZBrush is the front window. When one is pressed it draws the ring in a window that never takes focus, so ZBrush keeps working underneath.
- **The bridge** (`bridge\radial_menu_bridge.py`) runs inside ZBrush as a Python plugin. It adds the **Zplugin > Radial Menu** palette, starts the app, and carries out picks by calling ZBrush's own commands.

When you pick a slot, the app writes the request to a small file and posts a Windows message to a hidden listener window the bridge keeps inside ZBrush. The bridge reads the file and does the work on ZBrush's main thread. If the listener is not available, the app can press a fallback key (F9) that you bind to **Zplugin > Radial Menu > Apply**.

ZBrush 2022 to 2025 have no Python API, so for them the bridge is a ZScript plugin (`bridge\zscript\`) with the same palette. ZScript cannot host a listener window, so the app always presses the bridge key there. The app also writes each pick in a plain line-by-line form that ZScript can read, and loads brushes from that ZBrush version's own files.

The app exits when ZBrush does.

## Troubleshooting

**Nothing happens when I press Q.**
Make sure ZBrush is the front window. Then in ZBrush open **Zplugin > Radial Menu > Status**. It should say the listener is verified and the app is running. If the palette is missing, ZBrush did not load the plugin: restart it, and check that `ZBRUSH_PLUGIN_PATH` (in Windows' environment variables, user section) contains the bridge folder.

**The ring opens but picks do nothing.**
Open **Zplugin > Radial Menu > Status** and check that the listener says "verified". Look at `bridge.log`, which shows exactly what ZBrush did with each pick. Failed items are listed there, for example a button path that does not exist.

**Use the fallback key.**
In ZBrush, Ctrl+Alt+click **Zplugin > Radial Menu > Apply**, press **F9**, then store it in **Preferences > Hotkeys > Store**. With the bridge mode on `auto` (the default), Radial Menu presses F9 when the listener does not answer.

**ZBrush 2022 to 2025: the ring opens, but picks do nothing.**
Picks there only arrive through the bridge key. Check that F9 is bound to **Zplugin > Radial Menu > Apply** and that you clicked **Preferences > Hotkeys > Store**; a binding that was not stored is gone after a restart. `zscript_bridge.log` shows what the last pick did.

**Logs.**
`%LOCALAPPDATA%\RadialMenu` holds `radiald.log` (the app), `bridge.log` (ZBrush side), `zscript_bridge.log` (ZBrush 2022 to 2025: the last pick), `studio.log` (how Studio started) and `app_stderr.log` (crashes at startup). Studio's **Status** screen shows the tail of the app log and has a button that opens the folder.

**Windows protected your PC.**
See [above](#windows-says-windows-protected-your-pc).

More is in the [user guide](docs/user-guide.md#troubleshooting).

## Licence

| | |
|---|---|
| **Licence key** | `RMZB-FREE-4EVR-NOKY-GPL3` |
| **Status** | Activated |
| **Seats** | All of them |
| **Expires** | Never |
| **Price** | 0.00 |

**Just kidding.** There is no licence key, no account, no trial and no expiry date. Radial Menu for ZBrush is licensed under the **GNU General Public License v3.0** (see [LICENSE](LICENSE)): free to use on as many machines as you like, to study, change and share. It stays free: if you distribute a modified version, you must also publish its source under the same licence. You are licensed. Forever.

(The Studio has the same Licence screen. Its buttons work exactly as well as this table does. Not amused? Hide it with the link at the bottom of that page, or in Settings > Studio.)

Third-party components and their licences are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

Radial Menu for ZBrush is an independent project. It is not affiliated with or endorsed by Maxon. ZBrush is a trademark of Maxon.
