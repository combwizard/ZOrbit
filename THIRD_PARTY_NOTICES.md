# Third-party notices

Radial Menu for ZBrush is licensed under the GNU General Public License v3.0 (see `LICENSE`). The installer
bundles the components below, each under its own licence. Versions are the ones the project was built and
tested with. Each project's full licence text is available from its own repository or package, linked here.

| Component | Used for | Licence | Source |
|---|---|---|---|
| Python | The language runtime the app and Studio run on | Python Software Foundation License (PSF-2.0) | https://www.python.org/ |
| Pillow 12.x | Drawing the ring and decoding brush thumbnails | MIT-CMU (permissive, derived from HPND) | https://github.com/python-pillow/Pillow |
| pywebview 6.x | The Studio window | BSD-3-Clause | https://github.com/r0x0r/pywebview |
| pythonnet 3.x | Lets pywebview use .NET and WebView2 | MIT | https://github.com/pythonnet/pythonnet |
| clr_loader 0.3.x | Loads the .NET runtime for pythonnet | MIT | https://github.com/pythonnet/clr-loader |
| cffi 2.x | A dependency of clr_loader | MIT | https://github.com/python-cffi/cffi |
| pycparser 2.x | A dependency of cffi | BSD-3-Clause | https://github.com/eliben/pycparser |
| bottle 0.13.x | A dependency of pywebview | MIT | https://github.com/bottlepy/bottle |
| proxy_tools 0.1.x | A dependency of pywebview | MIT | https://github.com/jtushman/proxy_tools |
| typing_extensions 4.x | A dependency of pywebview | PSF-2.0 | https://github.com/python/typing_extensions |
| Microsoft Edge WebView2 SDK (the `Microsoft.Web.WebView2` assemblies and loader shipped inside pywebview) | Hosting the Studio page | BSD-3-Clause | https://www.nuget.org/packages/Microsoft.Web.WebView2 |
| PyInstaller bootloader | Starts the packaged app | GPL-2.0-or-later with a special exception that allows bundling non-GPL code | https://github.com/pyinstaller/pyinstaller |

## Notes

- **Edge WebView2 runtime.** Studio displays its pages with the Microsoft Edge WebView2 runtime. The runtime is
  part of Windows and is not bundled or redistributed by this project; it is subject to Microsoft's own
  terms. Only the small SDK libraries listed above are shipped.
- **Pillow** wheels contain compiled copies of image libraries (for example FreeType, zlib and libjpeg).
  Their licences are included in Pillow's own distribution.
- **Python** is bundled in the installer as the packaged interpreter and standard library. The interpreter
  carries a few C libraries (for example OpenSSL, libffi, SQLite and zlib) under their own permissive
  licences, which are collected in Python's own `LICENSE`.
- **PyInstaller** itself is GPL-licensed software, but its licence includes an exception that lets programs
  it packages use any licence. The packaged app is licensed under GPL-3.0 regardless.

The dependencies in `requirements.txt` are used unmodified. If you spot a missing or wrong entry, please open
an issue.
