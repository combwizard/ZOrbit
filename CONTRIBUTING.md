# Contributing

Thanks for helping. This is a small project, so the process is light.

## Issues

Bug reports and ideas are welcome on the
[issue tracker](https://github.com/combwizard/zorbit/issues). For a bug, please include:

- your Windows and ZBrush versions;
- what you did, what you expected and what happened;
- the text from **Copy report** on Studio's **Status** screen, which has the logs with your user name and folders
  hidden. Look it over first and remove anything you would rather not share. The
  [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) says what to send if Studio does not start.

What's planned is on the [roadmap board](https://github.com/users/combwizard/projects/2), and every idea there is
an issue of its own. Add a thumbs-up to the ideas you want and comment on how you'd use them.
[This list](https://github.com/combwizard/zorbit/issues?q=is%3Aissue%20is%3Aopen%20label%3Aidea%20sort%3Areactions-%2B1-desc)
puts the ideas with the most thumbs-ups first. Issues marked
[needs testing](https://github.com/combwizard/zorbit/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22needs%20testing%22)
ask for someone with a particular ZBrush version to try something.

Report security problems privately, as [SECURITY.md](SECURITY.md) describes. Everyone taking part is expected to
follow the [code of conduct](CODE_OF_CONDUCT.md).

## Pull requests

1. Fork the repository and make a branch.
2. Keep the change focused: one fix or feature per pull request, with a short description of what and why.
3. Match the style of the surrounding code. Keep the ring code fast: a frame should cost a few milliseconds.
4. Try it in ZBrush if you can. When behaviour changes, update the page in `docs\` that describes it (the table in
   [CLAUDE.md](CLAUDE.md) says which) in the same pull request. Leave `CHANGELOG.md` alone: the maintainer adds
   the line when merging. The docs are published at
   <https://zorbit.lol/docs/>; preview them with `pip install -r requirements-docs.txt` and `mkdocs serve`.
   The pre-commit hook stops a commit that changes `zorbit\` or `bridge\` without touching `docs\`. Install it once
   with `sh tools/hooks/install.sh` in Git Bash. When there is nothing to document, commit with
   `ZORBIT_NO_DOCS=1 git commit ...` in Git Bash, or `$env:ZORBIT_NO_DOCS=1; git commit ...` in PowerShell.
5. By contributing, you agree that your work is licensed under the GPL-3.0, like the rest of the project.

## Development setup

You need Windows, Python 3.14 and ZBrush 2026 or newer. A change to the ZScript bridge also needs ZBrush 2022
installed, to compile it (see [The ZScript bridge](#the-zscript-bridge-zbrush-2022-2025) below).

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
python zorbit\main.py --selftest  # check that the libraries, modules and bundled files are all there
python zorbit\main.py --studio    # open Studio
python zorbit\main.py             # run the app by hand (it keeps running until you stop it)
pytest                            # run the tests
```

The tests that run JavaScript need `node` on the `PATH`, and pytest skips them without it. If
`tests\test_studio_looks.py` fails and names `tools/make_look_cases.py`, run that and commit the two fixtures it
rewrites.

Source layout:

| Folder | Contents |
|---|---|
| `zorbit\` | The app: hotkeys, ring drawing, config loading, thumbnails for brushes, alphas, materials and textures (`brushes.py`, `assets.py`), Studio backend |
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

1. Close ZBrush (only one version can run at a time) and run `tools\compile-zscript.ps1`. It starts the
   oldest supported ZBrush (2022) with the source, waits for the `.zsc`, closes ZBrush and puts the result
   in `bridge\zscript`. By hand: in ZBrush 2022 choose **ZScript > Load** and pick `ZOrbitBridge.txt`; ZBrush
   writes `ZOrbitBridge.zsc` next to it. Compiling in the oldest version is meant to keep it loadable in
   the newer ones; check it in the newest one you have too.
2. Commit the source and the `.zsc` together. The pre-commit hook does step 1 for you: run
   `sh tools/hooks/install.sh` once (Git Bash), and every commit that includes `ZOrbitBridge.txt` compiles it
   and adds the `.zsc`. Close ZBrush before committing; `ZORBIT_SKIP_ZSC=1 git commit ...` skips the compile.
3. In Studio, **Settings > Older ZBrush > Update** puts the new build into each installed ZBrush.

The build bundles both files, and Studio copies the `.zsc` plus a `ZOrbitData\bridge.cfg` into
`<ZBrush>\ZStartup\ZPlugs64`. The file formats are described at the top of the source and in
`zorbit\zscript_bridge.py`.

After a change to installing or removing the plugin, run `python tools\test_uac_install.py` from a normal
terminal. It tests the install into a ZBrush under Program Files, where ZOrbit needs administrator rights; see
[Build from source](docs/building.md#test-the-plugin-install-under-program-files).

### Changing what ZOrbit keeps on disk

If a change to what ZOrbit keeps on disk would make an older version misread or overwrite the new layout, it needs a format step:

1. Raise `profiles.FORMAT` by one. An older version then leaves the files alone and says so, as [These files were made by a newer ZOrbit](docs/troubleshooting.md#these-files-were-made-by-a-newer-zorbit) describes.
2. Add the migration step to `zorbit\profiles.py`.
3. Add an upgrade fixture made by the last release: add its tag to `tools\make_upgrade_fixtures.py` and run it. `tests\test_upgrade.py` then checks the migration over it. See [Build from source](docs/building.md#tests-and-checks).

### Release notes

At release time, add a short plain summary of two to four sentences under the `## [x.y.z]` heading in `CHANGELOG.md`, before the `###` groups. Studio's **What's new** shows it, and the GitHub release notes include it. Without one, **What's new** shows the first five bullets. Wrap its lines as you like: the release notes join the lines of each paragraph and bullet, since GitHub shows every line break in them.

A bigger release can also get a post on the [blog](https://zorbit.lol/docs/blog/): a Markdown file in `docs\blog\posts\` with a `date`, `authors` (from `docs\blog\.authors.yml`) and `slug` at the top, and `<!-- more -->` after the opening paragraphs, which are what the blog's front page shows. Give it the slug `zorbit-` and the version with dashes for dots (`zorbit-0-13-0`), and the release notes link to it. Push the post before the tag so the link works when the release appears.

### Working on Studio's interface in a browser

Run `python tools\make_mock.py`, then open `zorbit\studio_ui\index.html?mock` in a browser. This
lets you iterate on the UI without starting Studio.

**Privacy: never commit `zorbit\studio_ui\dev\mock_data.js`.** The script records responses from your own
machine, including your folder paths, hotkeys and logs. It is listed in `.gitignore`; keep it that way, and
check `git status` before you commit.

More generally, keep personal information out of commits, issues and screenshots: no real names, email
addresses, machine names or user-folder paths. Use placeholders such as `%APPDATA%` in documentation. The
pre-commit hook refuses a commit that contains a `C:\Users\<name>` path other than `C:\Users\you`.

When you make documentation images, use the project's own renderer with the shipped starter menus, so that
only brushes included with ZBrush appear.

### Taking the pictures for the docs

`python tools\docs_shots.py` takes the Studio and browser screenshots from the mock UI. `python tools\ring_shots.py`
draws the ring pictures and GIFs (`ring.png`, `fan.png`, `looks.png` and the rest of the `SHOTS` table in the script)
with the real ring renderer. Both work on a throw-away copy of the starter menus, so your own menus
and tags never appear in a picture, and the Studio pictures leave out the version at the top, so a release does not
change them. Name pictures after the script to retake only those, and add `--out DIR` to look
at them before they replace the ones in `docs\images`.
