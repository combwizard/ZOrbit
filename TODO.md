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

Worked out on 6 Nov 2026. A new issue goes on the board straight away and joins this order the next time it is
worked out.

1. **Before 1.0:** nothing left to build. The 1.0 milestone is empty since 0.20.0, and the test pass of 6 Nov 2026
   (the suite, a test Studio and browser driven over the debug port, ZBrush 2026 and 2022 on this PC, a clean install
   and update on the VM, the docs against the code) found only small things, fixed since. 1.0.0 waits for 0.19 and
   0.20 to be used for a while; it ships with no new feature. Two decisions go with it: whether the "experimental"
   note on themes and the "under heavy development" note on the docs index stay, and whether
   [#181](https://github.com/combwizard/ZOrbit/issues/181) (the library follows the running ZBrush, not the newest
   install) goes in before or after.
2. **Next:** [#39](https://github.com/combwizard/ZOrbit/issues/39), the drag to reorder. Tags may already cover its
   named lists, so settle that before building them. [#40](https://github.com/combwizard/ZOrbit/issues/40) waits for
   it, since the strip needs the favourites data settled.
3. **Ring look, back to back, if wanted:** [#35](https://github.com/combwizard/ZOrbit/issues/35) (`Item.colors`; slots
   that are not round are the hard part), then [#37](https://github.com/combwizard/ZOrbit/issues/37) (a large fan has
   two staggered rows, so no one arc runs through its slots) and
   [#36](https://github.com/combwizard/ZOrbit/issues/36), the least useful. Retake the ring pictures once at the end.
4. **When someone asks:** [#98](https://github.com/combwizard/ZOrbit/issues/98) (design first) and
   [#26](https://github.com/combwizard/ZOrbit/issues/26). Keep new IPC code out of `win32.py` and `radiald.py`.

Parked for now: [#29](https://github.com/combwizard/ZOrbit/issues/29) (Keep, Remove and Hide need more
detailing); [#94](https://github.com/combwizard/ZOrbit/issues/94) (the window title only ever says ZBrush, so the
plugin would have to report what is open); [#156](https://github.com/combwizard/ZOrbit/issues/156) (an untested
workaround over WebView2, for a small gain).
