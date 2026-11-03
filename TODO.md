# TODO

Every open issue is listed here, and every item here is an issue, so the two always match. Tick an item when its
issue closes. The same issues are on these pages, where people can comment and add a thumbs-up:

- [Roadmap board](https://github.com/users/combwizard/projects/2): Next, In progress, Later, Ideas, Done
- [Milestone 1.0](https://github.com/combwizard/ZOrbit/milestone/1): what has to be done or checked before 1.0
- [Ideas, most wanted first](https://github.com/combwizard/ZOrbit/issues?q=is%3Aissue%20is%3Aopen%20label%3Aidea%20sort%3Areactions-%2B1-desc)

## Order of work

The lists below group issues by area. This is the order to take them in, worked out on 3 Nov 2026.

1. **One sitting at ZBrush 2022 and 2026**, because it unblocks the most:
   - [#102](https://github.com/combwizard/ZOrbit/issues/102), likely a real bug on 2022-2025: `request.txt` carries
     the menu name but not the file stem, and `RM_Alpha`/`RM_Texture` only look for `Alpha:<name>`. Fix by sending
     the stem, falling back to it in `RM_*`, and recompiling the `.zsc`.
   - [#101](https://github.com/combwizard/ZOrbit/issues/101) in the same sitting.
   - For [#24](https://github.com/combwizard/ZOrbit/issues/24): does `ZBrush.exe <script>` reuse the open ZBrush?
   - For [#30](https://github.com/combwizard/ZOrbit/issues/30): whether `{"press": "Macro:..."}` already runs a
     macro. (The capture and loader buttons exist in 2022 and 2026: `Document:Export`, `Tool:Load Tool`,
     `File:Open`, `Preferences:Config:Load Ui`.)
   - [#103](https://github.com/combwizard/ZOrbit/issues/103) on the current window code.
   - [#23](https://github.com/combwizard/ZOrbit/issues/23) whenever a standard (non-admin) account is to hand.
2. **Medium:** [#108](https://github.com/combwizard/ZOrbit/issues/108) first (small);
   [#99](https://github.com/combwizard/ZOrbit/issues/99) then
   [#94](https://github.com/combwizard/ZOrbit/issues/94) (`--profile next` is the hotkey's plumbing);
   [#106](https://github.com/combwizard/ZOrbit/issues/106) (timer inside the browser);
   [#31](https://github.com/combwizard/ZOrbit/issues/31) then
   [#30](https://github.com/combwizard/ZOrbit/issues/30) (one "set the file, then press" action);
   [#24](https://github.com/combwizard/ZOrbit/issues/24) if the check in step 1 works out.
3. **Ring look, back to back:** [#37](https://github.com/combwizard/ZOrbit/issues/37) (band helper), then
   [#35](https://github.com/combwizard/ZOrbit/issues/35) (`Item.colors`), then
   [#36](https://github.com/combwizard/ZOrbit/issues/36). Retake the ring pictures once at the end.
4. **Design first:** [#98](https://github.com/combwizard/ZOrbit/issues/98) (after #97),
   [#39](https://github.com/combwizard/ZOrbit/issues/39) then [#40](https://github.com/combwizard/ZOrbit/issues/40)
   (settle the favourites data first), [#104](https://github.com/combwizard/ZOrbit/issues/104) (after #103 passes; its checks are #104's test list),
   [#26](https://github.com/combwizard/ZOrbit/issues/26) last. Keep new IPC code out of `win32.py` and `radiald.py`.

Parked for now: [#29](https://github.com/combwizard/ZOrbit/issues/29) (Keep, Remove and Hide need more
detailing).

Issues #105, #34, #94 and #39 all edit `studio_ui/app.js`, so merge them one at a time.

## Before 1.0

- [ ] [#23](https://github.com/combwizard/ZOrbit/issues/23) Test installing the plugin into a ZBrush under Program Files
- [ ] [#24](https://github.com/combwizard/ZOrbit/issues/24) Older ZBrush: a slow fallback when the Apply key isn't bound

## Checks in ZBrush

- [x] [#101](https://github.com/combwizard/ZOrbit/issues/101) Check the "(Edit mode is off)" note on brush picks and the leftover request file cleanup, in ZBrush 2022 and 2026
- [x] [#102](https://github.com/combwizard/ZOrbit/issues/102) Check that an imported alpha or texture gets a button named by its file stem, and that `Texture:Import` takes .exr

## Studio

- [ ] [#103](https://github.com/combwizard/ZOrbit/issues/103) Test the window after the 0.10.1 flash fix: the PC that reported it, dragging off the top, another monitor, snap layouts
- [ ] [#104](https://github.com/combwizard/ZOrbit/issues/104) Draw the title bar through `WM_NCCALCSIZE` instead of removing `WS_CAPTION`
- [x] [#105](https://github.com/combwizard/ZOrbit/issues/105) Put the Browser card ahead of ZBrush bridge in Settings

## Build

- [x] [#100](https://github.com/combwizard/ZOrbit/issues/100) Move from Python 3.12 to 3.14

## Browser

- [ ] [#106](https://github.com/combwizard/ZOrbit/issues/106) Quit after a while unused and start again on the next press
- [ ] [#108](https://github.com/combwizard/ZOrbit/issues/108) Picks fall back to the bridge key when the browser was opened before the app
- [x] [#97](https://github.com/combwizard/ZOrbit/issues/97) Show a theme picked in Studio at once, not on the next half-second check

## Themes, profiles and platforms

- [ ] [#98](https://github.com/combwizard/ZOrbit/issues/98) Custom themes: make, save and share your own look for the ring, Studio and the browser
- [ ] [#94](https://github.com/combwizard/ZOrbit/issues/94) Profiles: a hotkey that cycles through them, and switching by ZBrush project name
- [ ] [#26](https://github.com/combwizard/ZOrbit/issues/26) macOS support

## Ideas

Ring and items:

- [ ] [#99](https://github.com/combwizard/ZOrbit/issues/99) Commands from other programs: open a menu, pick a brush or switch profile from the command line
- [ ] [#29](https://github.com/combwizard/ZOrbit/issues/29) Right-click the open ring: Keep, Remove, Hide
- [ ] [#30](https://github.com/combwizard/ZOrbit/issues/30) More item types: macro, and load a tool, project or UI layout
- [ ] [#31](https://github.com/combwizard/ZOrbit/issues/31) Capture item: save the viewport as a PNG
- [x] [#32](https://github.com/combwizard/ZOrbit/issues/32) A ring theme that matches ZBrush's interface colours

Tags:

- [x] [#34](https://github.com/combwizard/ZOrbit/issues/34) Any / All switch for tag filters
- [ ] [#35](https://github.com/combwizard/ZOrbit/issues/35) Show every tag on a slot's border
- [ ] [#36](https://github.com/combwizard/ZOrbit/issues/36) Group slots by tag on the ring
- [ ] [#37](https://github.com/combwizard/ZOrbit/issues/37) Tag band along a fan's arc
- [x] [#38](https://github.com/combwizard/ZOrbit/issues/38) Setting for how many slots a tag fan holds

Browser and ZBrush:

- [x] [#28](https://github.com/combwizard/ZOrbit/issues/28) Follow ZBrush 2026's Asset Directory setting
- [ ] [#39](https://github.com/combwizard/ZOrbit/issues/39) Favourites: drag to reorder, and several named lists
- [ ] [#40](https://github.com/combwizard/ZOrbit/issues/40) A strip of favourites over ZBrush
