# Build from source


This builds the installer from a checkout of the repository. You need Windows, Python 3.12 and the packages in `requirements-dev.txt`.

```powershell
pip install -r requirements-dev.txt
.\packaging\build.ps1
```

The script's header lists what else it needs and where the installer ends up.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.

## Test the plugin install under Program Files

ZBrush 2022 to 2025 load plugins only from their own `ZStartup\ZPlugs64` folder, which is usually under Program Files. There Studio's **Install**, **Update** and **Remove** cannot copy the files as you, so ZOrbit runs a helper as administrator instead. `tools\test_uac_install.py` tests that path without a real ZBrush:

```powershell
python tools\test_uac_install.py
```

Run it from a normal terminal, not as administrator. It makes a fake ZBrush in `C:\Program Files\ZOrbit UAC test` with the plugin from before the rename in it. Then it updates that plugin, removes it, and tries an install that you decline. After each step it checks the files, and at the end it deletes the fake ZBrush. Before each UAC prompt it prints which button to press. There are five prompts in all.

`--exe "%LOCALAPPDATA%\Programs\ZOrbit\ZOrbit.exe"` also tests the helper of an installed build. `--no-uac` runs only the checks that need no prompt. The header of the script lists the other options and what it does not cover.
