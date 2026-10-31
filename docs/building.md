# Build from source


This builds the installer from a checkout of the repository. You need Windows, Python 3.12 and the packages in `requirements-dev.txt`.

```powershell
pip install -r requirements-dev.txt
.\packaging\build.ps1
```

The script builds the app, the portable zip (`dist\ZOrbit-<version>-portable.zip`) and, if Inno Setup 6 is installed, the installer (`packaging\Output\ZOrbitSetup-<version>.exe`). Without Inno Setup it warns and stops after the zip. Install it with `winget install JRSoftware.InnoSetup`, or pass `-SkipInstaller` to build only the app and the zip. The script's header lists the rest.

Windows may refuse to run the PowerShell scripts in `packaging\` and `tools\` ("running scripts is disabled on this system"). Allow scripts you wrote or built yourself with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or run one script without changing the policy:

```powershell
pwsh -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

Use `powershell` instead of `pwsh` if you only have Windows PowerShell 5.

`packaging\build.ps1` installs from `requirements-lock.txt` when that file exists. It holds the exact versions of every package the build needs, so a release is built from the same packages each time. `requirements-dev.txt` keeps the loose version ranges. The header of the lock file says how to regenerate it in a clean virtual environment.

## Tests and checks

```powershell
python -m pytest -q                   # the test suite (Windows only)
python zorbit\main.py --check         # validate the menus file
python zorbit\main.py --selftest      # check the libraries, modules and bundled files
dist\ZOrbit\ZOrbit.exe --selftest     # the same checks on the built app
```

The tests import the Windows modules, so they run on Windows only. `--selftest` imports pywebview, pythonnet and every app module, and looks for the Studio interface files, the icons, the default menus, the ZScript bridge and the WebView2 loader DLL. It prints one line per check and exits with 1 if any fails. Run it on the built exe to catch a file that PyInstaller left out.

GitHub Actions runs the tests on every push and pull request. A build only starts when they pass. After the build, the workflow runs `--check` and `--selftest` on the built exe. When you push a tag that starts with `v`, it also creates the release, and the release notes list the SHA256 hash of the installer and the portable zip.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.

## Test the plugin install under Program Files

ZBrush 2022 to 2025 load plugins only from their own `ZStartup\ZPlugs64` folder, which is usually under Program Files. There Studio's **Install**, **Update** and **Remove** cannot copy the files as you, so ZOrbit runs a helper as administrator instead. `tools\test_uac_install.py` tests that path without a real ZBrush:

```powershell
python tools\test_uac_install.py
```

Run it from a normal terminal, not as administrator. It makes a fake ZBrush in `C:\Program Files\ZOrbit UAC test` with the plugin from before the rename in it. Then it updates that plugin, removes it, and tries an install that you decline. After each step it checks the files, and at the end it deletes the fake ZBrush. Before each UAC prompt it prints which button to press. There are five prompts in all.

`--exe "%LOCALAPPDATA%\Programs\ZOrbit\ZOrbit.exe"` also tests the helper of an installed build. `--no-uac` runs only the checks that need no prompt. The header of the script lists the other options and what it does not cover.
