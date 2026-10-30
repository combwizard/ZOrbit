# ZOrbit

A radial brush menu for ZBrush on Windows. [README.md](README.md) says what it does, [CONTRIBUTING.md](CONTRIBUTING.md)
how to set up a checkout and run it.

## Keep the docs in step with the code

The user docs are the Markdown pages in `docs/`. Every push to `main` that touches them publishes them to
<https://zorbit.lol/docs/>, so they describe `main`, not the last release.

- **A change a user can see or do updates its docs page in the same commit.** That covers settings, screens, buttons,
  item types, hotkeys, defaults, file names and locations, log files, messages, requirements and install steps. A new
  feature is documented where a user would look for it; a removed one is taken out of every page that mentions it.
- **Add a line to `CHANGELOG.md`** under `## [Unreleased]` (create the section if the top one is a released version).
- **Check `README.md`** when the change touches install, requirements, first steps or the feature list.
- **Pictures:** when a change makes a screenshot or GIF in `docs/images/` out of date, say so in the reply. Don't
  leave it silently wrong.
- **Build the docs** after editing them: `mkdocs build --strict` (`pip install -r requirements-docs.txt` first). It
  fails on a broken link or anchor. Link between pages with relative `.md` links so they work on GitHub too.
- **The pre-commit hook** (`tools/hooks/pre-commit`) stops a commit that changes `zorbit/` or `bridge/` without
  touching `docs/` or `README.md`. When there really is nothing to document (a refactor, an internal fix, a bug fix
  that restores what the docs already say), commit with `ZORBIT_NO_DOCS=1` and say in the reply that you did.

Where each part is documented:

| Code | Page in `docs/` |
|---|---|
| `studio.py`, `webapi.py`, `studio_ui/` (Studio screens and settings) | `studio.md`, plus the page for the feature |
| `config.py`, `expand.py`, `default_menus.json` (menus, item types, submenus, fans) | `menus.md` |
| `usage.py` (auto slots, recent picks) | `menus.md`, `browser.md` |
| `tags.py`, tag colours in `ring.py` | `tags.md`, `appearance.md` |
| `popout.py`, `studio_ui/popout.html`, `assets.py`, `brushes.py` (browser, libraries) | `browser.md` |
| `radiald.py` (hotkeys, pick modes, picks mid-stroke) | `hotkeys.md` |
| `ring.py` (look, size, colours, labels, animations) | `appearance.md` |
| `bridge/`, `zscript_bridge.py` (bridge modes, bridge key, the Zplugin palette) | `bridge.md` |
| `paths.py`, `fsutil.py`, import and export, logs | `files.md` |
| `installs.py`, `onboarding.py`, `activity.py`, `packaging/` (install, Setup screen) | `install.md`, `getting-started.md` |
| A new way for something to fail, or a new log line worth reading | `troubleshooting.md` |
| `packaging/build.ps1`, `tools/` | `building.md`, `CONTRIBUTING.md` |

Write like the existing pages: plain, short, concrete sentences, British spelling (colour, behaviour, licence), UI
labels and keys in **bold**, no em dashes, no marketing words.

The docs theme is in `docs-theme/` and `docs/stylesheets/extra.css`. It copies the landing page, which lives on the
orphan `site` branch; `.github/workflows/pages.yml` (one copy on each branch) deploys both together.
