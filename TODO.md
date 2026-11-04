# TODO

The GitHub issues are the list of what needs doing. This file is the plan: the order to take the open issues in,
and the notes that tie one issue to another. Closing an issue needs no change here. Change this file when the
plan changes.

The issues themselves, where people can comment and add a thumbs-up:

- [Roadmap board](https://github.com/users/combwizard/projects/2): Next, In progress, Later, Ideas, Done
- [Milestone 1.0](https://github.com/combwizard/ZOrbit/milestone/1): what has to be done or checked before 1.0
- [Ideas, most wanted first](https://github.com/combwizard/ZOrbit/issues?q=is%3Aissue%20is%3Aopen%20label%3Aidea%20sort%3Areactions-%2B1-desc)
- [All open issues](https://github.com/combwizard/ZOrbit/issues)

## Order of work

Worked out on 3 Nov 2026. A new issue goes on the board straight away and joins this order the next time it is
worked out.

1. **Checks that need a person or real hardware.** The test VM (`tools/vm`) can do the rest:
   - [#103](https://github.com/combwizard/ZOrbit/issues/103) on the current window code. The VM has one screen, so
     the part on monitors of different sizes needs real ones.
   - [#23](https://github.com/combwizard/ZOrbit/issues/23) whenever a standard (non-admin) account is to hand.
2. **Medium:** [#108](https://github.com/combwizard/ZOrbit/issues/108) first (small), then
   [#109](https://github.com/combwizard/ZOrbit/issues/109) (pick hide, dim or a message first);
   [#116](https://github.com/combwizard/ZOrbit/issues/116) (Copy report on Status);
   [#99](https://github.com/combwizard/ZOrbit/issues/99) then
   [#94](https://github.com/combwizard/ZOrbit/issues/94) (`--profile next` is the hotkey's plumbing);
   [#106](https://github.com/combwizard/ZOrbit/issues/106) (timer inside the browser);
   [#31](https://github.com/combwizard/ZOrbit/issues/31) then
   [#30](https://github.com/combwizard/ZOrbit/issues/30) (one "set the file, then press" action);
   [#24](https://github.com/combwizard/ZOrbit/issues/24) (its check worked out);
   [#104](https://github.com/combwizard/ZOrbit/issues/104) (the #103 checks of 3 Nov failed on monitors of
   different sizes and found no snap layouts flyout; #103's checks are its test list).
3. **Ring look, back to back:** [#37](https://github.com/combwizard/ZOrbit/issues/37) (band helper), then
   [#35](https://github.com/combwizard/ZOrbit/issues/35) (`Item.colors`), then
   [#36](https://github.com/combwizard/ZOrbit/issues/36). Retake the ring pictures once at the end.
4. **Design first:** [#98](https://github.com/combwizard/ZOrbit/issues/98),
   [#39](https://github.com/combwizard/ZOrbit/issues/39) then [#40](https://github.com/combwizard/ZOrbit/issues/40)
   (settle the favourites data first),
   [#26](https://github.com/combwizard/ZOrbit/issues/26) last. Keep new IPC code out of `win32.py` and `radiald.py`.

Parked for now: [#29](https://github.com/combwizard/ZOrbit/issues/29) (Keep, Remove and Hide need more
detailing).

[#116](https://github.com/combwizard/ZOrbit/issues/116), [#94](https://github.com/combwizard/ZOrbit/issues/94)
and [#39](https://github.com/combwizard/ZOrbit/issues/39) all edit `studio_ui/app.js`, so merge them one at a
time.
