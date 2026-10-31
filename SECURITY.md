# Security policy

## Supported versions

Only the latest release gets fixes. New versions come out often, so please check that you are on the
[latest release](https://github.com/combwizard/zorbit/releases/latest) before you report.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately with the
[**Report a vulnerability**](https://github.com/combwizard/zorbit/security/advisories/new) form on the repository's
**Security** tab.

Say what the problem is, how to reproduce it, and which ZOrbit and Windows versions you used. You should hear back
within a week. Once a fix is released, the advisory is published and you are credited, unless you would rather not be.

## What counts

ZOrbit runs on your own PC, next to ZBrush. Things worth reporting include:

- a way for a menus file, a brush or asset name, or a file in a ZBrush folder to run code or write outside the
  folders ZOrbit uses;
- a way for another program or web page to send commands to the app, the bridge or Studio;
- a problem with the installer or the update check.

The app runs with your own user rights and can press any ZBrush button you put on a ring. That is by design, and not
a vulnerability on its own.

## Known limitations

Installing the ZScript plugin into a ZBrush 2022 to 2025 under Program Files runs `ZOrbit.exe` as administrator from
the per-user install folder. The elevated step builds the plugin files itself, but anything already running as your
user could replace that program first. ZOrbit cannot change this while it installs per user, and it never asks for
administrator rights for anything else.

A menus file from someone else runs their buttons in ZBrush when you use it, so only import files you trust.

ZOrbit installs a Windows keyboard hook. It compares each key press with your hotkeys and acts only when ZBrush is the
front window. It does not record, store or send what you type.
