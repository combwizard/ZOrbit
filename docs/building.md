# Build from source


This builds the installer from a checkout of the repository. You need Windows, Python 3.12 and the packages in `requirements-dev.txt`.

```powershell
pip install -r requirements-dev.txt
.\packaging\build.ps1
```

The script's header lists what else it needs and where the installer ends up.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.
