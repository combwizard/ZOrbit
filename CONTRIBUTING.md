# Contributing

Thanks for helping. This is a small project, so the process is light.

## Issues

Bug reports and ideas are welcome on the
[issue tracker](https://github.com/combwizard/zorbit/issues). For a bug, please include:

- your Windows and ZBrush versions;
- what you did, what you expected and what happened;
- the last lines of `%LOCALAPPDATA%\ZOrbit\radiald.log` and `bridge.log`. Look them over first and remove
  anything you would rather not share.

## Pull requests

1. Fork the repository and make a branch.
2. Keep the change focused: one fix or feature per pull request, with a short description of what and why.
3. Match the style of the surrounding code. Keep the ring code fast: a frame should cost a few milliseconds.
4. Try it in ZBrush if you can, and update `docs\user-guide.md` and `CHANGELOG.md` when behaviour changes.
5. By contributing, you agree that your work is licensed under the GPL-3.0, like the rest of the project.

## Development setup

You need Windows, Python 3.12 and ZBrush 2026 or newer.

```powershell
git clone https://github.com/combwizard/zorbit
cd zorbit
pip install -r requirements-dev.txt
.\tools\dev-install.ps1      # registers this checkout's bridge folder and a Start menu shortcut
```

Restart ZBrush once. From then on ZBrush starts the app from your checkout, so a code change takes effect the
next time ZBrush starts the app. Run `.\tools\dev-install.ps1 -Uninstall` to remove the registration.

Useful commands:

```powershell
python zorbit\main.py --check     # validate your menus file and print it
python zorbit\main.py --studio    # open Studio
python zorbit\main.py             # run the app by hand (it keeps running until you stop it)
```

Source layout:

| Folder | Contents |
|---|---|
| `zorbit\` | The app: hotkeys, ring drawing, config loading, brush thumbnails, Studio backend |
| `zorbit\studio_ui\` | Studio's interface (HTML, CSS, JavaScript) |
| `bridge\` | The plugin that runs inside ZBrush 2026+ (Python) |
| `bridge\zscript\` | The plugin for ZBrush 2022-2025 (ZScript source and its compiled `.zsc`) |
| `packaging\` | Build script for the installer |
| `tools\` | Developer scripts |
| `docs\` | User guide and images |

### The ZScript bridge (ZBrush 2022-2025)

Those versions have no Python API, so they get `bridge\zscript\ZOrbitBridge.txt` instead. ZBrush only
loads compiled plugins, and only ZBrush can compile them, so the compiled `ZOrbitBridge.zsc` is committed
next to the source. After changing the source:

1. Open the oldest supported ZBrush (2022), choose **ZScript > Load** and pick `ZOrbitBridge.txt`. ZBrush
   writes `ZOrbitBridge.zsc` next to it. Compiling in the oldest version is meant to keep it loadable in
   the newer ones; check it in the newest one you have too.
2. Commit the source and the `.zsc` together.
3. In Studio, **Settings > Older ZBrush > Update** puts the new build into each installed ZBrush.

The build bundles both files, and Studio copies the `.zsc` plus a `ZOrbitData\bridge.cfg` into
`<ZBrush>\ZStartup\ZPlugs64`. The file formats are described at the top of the source and in
`zorbit\zscript_bridge.py`.

### Working on Studio's interface in a browser

Run `python tools\make_mock.py`, then open `zorbit\studio_ui\index.html?mock` in a browser. This
lets you iterate on the UI without starting Studio.

**Privacy: never commit `zorbit\studio_ui\dev\mock_data.js`.** The script records responses from your own
machine, including your folder paths, hotkeys and logs. It is listed in `.gitignore`; keep it that way, and
check `git status` before you commit.

More generally, keep personal information out of commits, issues and screenshots: no real names, email
addresses, machine names or user-folder paths. Use placeholders such as `%APPDATA%` in documentation.

When you make documentation images, use the project's own renderer with the shipped starter menus, so that
only brushes included with ZBrush appear.
