# Build from source


This builds the installer from a checkout of the repository. You need Windows, Python 3.14 and the packages in `requirements-dev.txt`.

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

The tests import the Windows modules, so they run on Windows only. `--selftest` imports pywebview, pythonnet, truststore and every app module, and looks for the Studio interface files, the icons, the default menus, the ZScript bridge and the WebView2 loader DLL. It prints one line per check and exits with 1 if any fails. Run it on the built exe to catch a file that PyInstaller left out.

`tests\test_upgrade.py` runs the profile migration over data that real past releases wrote. The data is in `tests\fixtures\upgrade\<tag>\`: one folder each for v0.7.0, v0.7.1, v0.9.0 and v0.12.0, and a `downgrade` folder for 0.12.0 run again after the move. `python tools\make_upgrade_fixtures.py` makes them. It runs each release's own code from `git archive`, with a fresh `APPDATA` and `LOCALAPPDATA`. CI does not run the generator.

`tests\test_starters.py` checks that `profiles.KNOWN_STARTERS` lists the hash of every `default_menus.json` in the git history. It needs the full history, which CI gets with `fetch-depth: 0`. When `default_menus.json` changes, add its new hash to `KNOWN_STARTERS`.

`tests\test_docs.py` fails on a raw HTML tag with a local `src` or `href` in `docs\`, such as `<img src="images/x.png">`. MkDocs does not rewrite those paths and `mkdocs build --strict` does not check them, so the page builds and the picture breaks once it is published. Write pictures and links in Markdown.

GitHub Actions runs the tests on every push and pull request. A build only starts when they pass. After the build, the workflow runs `--check` and `--selftest` on the built exe, and `python tools\upgrade_check.py dist\ZOrbit\ZOrbit.exe`, which runs the exe's `--check` over each upgrade fixture. When you push a tag that starts with `v`, it also creates the release, and the release notes list the SHA256 hash of the installer and the portable zip. When `docs\blog\posts\` has a post whose `slug` is `zorbit-` and the version with dashes (`zorbit-0-13-0`), the notes also link to that [blog](blog/index.md) post.

To run straight from a checkout while you work on the code, use `tools\dev-install.ps1`. It registers the checkout's `bridge` folder in `ZBRUSH_PLUGIN_PATH` and adds the Start menu shortcut, and `-Uninstall` takes both away again. Add `-WhatIf` to see what it would do first.

## Reading ZBrush's colour schemes

`tools\icolors_probe.py` finds out where a ZBrush colour scheme (**Preferences > Icolors**) keeps each colour. Close ZBrush first, then run:

```powershell
python tools\icolors_probe.py auto               # ZBrush 2026
python tools\icolors_probe.py auto --year=2022   # another installed version
```

It starts ZBrush twice with a script and closes it after each, with no clicks. The first run lists the Icolors items. The second sets each colour patch to a marker colour in turn, saves the scheme with **Save Ui Colors** after each, and loads the original back. Nothing is stored, so your colours are as before afterwards. Then it compares the files and prints where each patch sits and how a colour is packed. Everything goes to `%LOCALAPPDATA%\ZOrbit\icolors`, with the map in `icolors_map.json`. The script's header lists the steps it runs and the ZBrush quirks it works around. Run it again when a new ZBrush version comes out, to check the layout has not changed.

## Test on a clean Windows

`tools\vm` makes a Hyper-V VM with a fresh Windows 11 Pro and drives it from your PC: screenshots, keys, mouse, commands and files. Use it to see what a first install does, and to catch what only works because your own PC has been in use for years. You need:

- Windows Pro with Hyper-V turned on, and PowerShell 7 (`pwsh`).
- Your account in the **Hyper-V Administrators** group. Run `Add-LocalGroupMember -SID S-1-5-32-578 -Member $env:USERNAME` once as administrator, which works whatever your Windows calls the group, then sign out and in. Nothing else needs an administrator terminal.
- A Windows 11 ISO that has the Pro edition and en-GB. The answer file asks for both, and Setup can stop at an error without them.
- Your own ZBrush licence.

```powershell
.\tools\vm\new-test-vm.ps1 -Iso C:\Users\you\Downloads\Windows11.iso -Folder D:\VMs -Password pick-one
```

This makes a VM called **ZOrbit Test** in that folder. Pick a folder you can write to without elevation, so not Hyper-V's default under `ProgramData`, on a drive with room: the disk can grow to 160 GB, and each checkpoint adds to that. The VM takes a fixed 16 GB of memory and 8 processors, so lower them on a smaller PC. `-MemoryGB`, `-Cpus` and `-DiskGB` change these, and `-WhatIf` shows the settings without making anything. The script installs Windows with no clicks, which takes 15 to 30 minutes, and takes a checkpoint called `windows`. The local account is `tester`, an administrator that signs in by itself. Without `-Password` it gets a random password. Either way the password is saved in plain text in `%LOCALAPPDATA%\ZOrbit-test-vm\vm.json`, so don't use one you use anywhere else. Windows is not activated, and the VM reaches the internet and your network through the Default Switch.

If the script is still waiting after 30 minutes, look at the VM in Hyper-V Manager. It presses a key for the first 8 seconds to boot from the ISO, and if it missed the prompt, or Setup stopped at an error, it waits a full hour before giving up. To start over, run `Remove-VM`, delete the VM's folder, and run the script again. The module drives the VM you made last.

Open the VM in Hyper-V Manager, install the ZBrush versions you want, start each one once to sign in, and close them. Then take the checkpoint your tests start from:

```powershell
Import-Module .\tools\vm\TestVM.psm1
Connect-TestVMConsole            # takes the VM's screen back from Hyper-V Manager's enhanced session
New-TestVMCheckpoint vanilla
```

A test goes like this:

```powershell
Restore-TestVM vanilla           # about 35 seconds, back at the desktop
Copy-ToTestVM .\packaging\Output\ZOrbitSetup-1.2.3.exe C:\zorbit-test     # the second path is a folder
Start-TestVMApp C:\zorbit-test\ZOrbitSetup-1.2.3.exe
Save-TestVMScreen                # writes a PNG and returns its path
Invoke-TestVMClick 1127 721      # screen pixels, the same as in the PNG
Send-TestVMKeyDown Q             # Send-TestVMKeyUp, Send-TestVMKeys 'Ctrl+S', Send-TestVMText, Move-TestVMMouse
Invoke-TestVM { Get-Content "$env:LOCALAPPDATA\ZOrbit\radiald.log" -Tail 5 }
```

Good to know:

- `Invoke-TestVM` runs with no desktop, so anything with a window goes through `Start-TestVMApp`. A program started that way does not get the keyboard: click into it first.
- Screenshots are 16-bit, so colours are close but not exact.
- The VM uses the UK keyboard layout, and `Send-TestVMText` is written for it. Any first-run test runs under en-GB.
- ZBrush opens Lightbox and its Home Page when it starts. Close them and hover over the canvas before you press **Q**.
- Run a first-run test straight after a restore. Windows adds root certificates when something asks for them, so a browser or `Invoke-WebRequest` in the VM can hide a problem with an HTTPS request.
- ZBrush 2022.0.7 and 2026.2.1 run in the VM without a graphics card passed through. ZBrush 2027.0.1 did not start, with error `0xc0000142` from its own DLLs, on Windows build 26300. We have not tried it on another Windows build.

## Test the plugin install under Program Files

ZBrush 2022 to 2025 load plugins only from their own `ZStartup\ZPlugs64` folder, which is usually under Program Files. There Studio's **Install**, **Update** and **Remove** cannot copy the files as you, so ZOrbit runs a helper as administrator instead. `tools\test_uac_install.py` tests that path without a real ZBrush:

```powershell
python tools\test_uac_install.py
```

Run it from a normal terminal, not as administrator. It makes a fake ZBrush in `C:\Program Files\ZOrbit UAC test` with the plugin from before the rename in it. Then it updates that plugin, removes it, and tries an install that you decline. After each step it checks the files, and at the end it deletes the fake ZBrush. Before each UAC prompt it prints which button to press. There are five prompts in all.

`--exe "%LOCALAPPDATA%\Programs\ZOrbit\ZOrbit.exe"` also tests the helper of an installed build. `--no-uac` runs only the checks that need no prompt. The header of the script lists the other options and what it does not cover.
