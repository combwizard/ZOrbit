# TODO

The roadmap and the ideas list are on GitHub now, one issue per item, so people can comment on each one and add a
thumbs-up:

- [Roadmap board](https://github.com/users/combwizard/projects/2): Next, In progress, Later, Ideas, Done
- [Milestone 1.0](https://github.com/combwizard/ZOrbit/milestone/1): what has to be done or checked before 1.0
- [Ideas, most wanted first](https://github.com/combwizard/ZOrbit/issues?q=is%3Aissue%20is%3Aopen%20label%3Aidea%20sort%3Areactions-%2B1-desc)

Below are my own notes: checks of changes I made and internal clean-ups that nobody else would vote on.

## Checks in ZBrush

- [ ] Test two bridge changes in ZBrush: the "(Edit mode is off)" note on brush picks, and deleting a leftover
      `request.json`/`request.txt` when the bridge loads
  - [ ] ZScript side: recompile in 2022, install, check `[IGet, "Transform:Edit"]` and `FileDelete` there
  - [ ] Python side: reload in 2026 and check `bridge.log` ends with "bridge loaded" again
- [ ] Check in ZBrush 2026 and 2022 that an imported alpha or texture gets a button named by its file stem (else
      every pick re-imports); check that `Texture:Import` takes .exr

## Studio window

- [ ] Test the 0.10.1 flash fix on the PC that reported the black flash (open, and leaving maximised)
- [ ] Untested after the flash fix: drag a maximised window off the top, Win+Shift+Arrow to another monitor and
      restore, snap layouts
- [ ] Custom title bar through `WM_NCCALCSIZE` instead of removing `WS_CAPTION` (`winframe.custom_frame`). With
      the caption style kept, Windows and WinForms agree on the window size, so the restore correction, the
      `WM_GETMINMAXINFO` work-area limit and the normal-rectangle tracker can all go, and `GetWindowPlacement`
      becomes right again. The catch: the top resize edge is inside the area WebView2 covers (keep a thin top
      border, or hit-test it). Test on Windows 10 and 11, Aero Snap, drag off the top, two monitors

## Clean-ups

- [ ] Reorder the Settings cards: Ring geometry, Colours, Labels, Tag colours (the look); Open animation, Behaviour
      (the feel); Browser, ZBrush bridge; then the cards that save straight away: Older ZBrush, Tags,
      Studio. Do it by sorting the built cards by name before the "On this page" list is made, not by moving
      their code, and put the same order in the Settings row of the user guide's Studio table. Import and export
      comes last, after Studio. Optionally a
      **Manage tags...** button in the Tag colours card
- [ ] Idle exit for the browser process: quit after a while unused and start again on the next press
