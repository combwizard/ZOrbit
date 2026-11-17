---
date: 2026-11-17 19:00:00
authors:
  - combwizard
slug: zorbit-0-25-0
description: ZOrbit 0.25.0 lets the ring show what ZBrush is doing. A Toggle slot shows whether its switch is on, a Set slot shows where its slider is, and a slot ZBrush would ignore right now is dimmed.
---

# ZOrbit 0.25.0: the ring shows what ZBrush is doing

Until now the ring told ZBrush what you picked and never heard anything back. A **Toggle** slot for Symmetry looked the same with Symmetry on or off, and a slot that sets Draw Size to 64 couldn't tell you the size was 64 already.

In 0.25.0 it can, in ZBrush 2026 and newer. As a ring opens, ZOrbit asks ZBrush about the slots that work its controls, and marks them. The ring still opens as fast as before.

<!-- more -->

## What a slot shows

Three kinds of slot work ZBrush's own buttons, switches and sliders: [Press](../../menus.md#press), [Set](../../menus.md#set) and [Toggle](../../menus.md#toggle). Those are the ones that get marks.

![A ring of nine slots. Brush slots ClayBuildup and Move; Symmetry with a filled dot and an outline; PolyF with a hollow dot; Size 128 with the figures 64 on it; a row of presets 0.25, 0.5 and 1 with 0.5 filled and outlined; and Clear Mask faint. Move is hovered](../../images/state.png)

- A **Toggle** slot has a small dot. While the switch is on, the dot is filled and the slot has an outline. While it is off, the dot is hollow.
- A **Set** slot shows where the slider is now, in small figures inside the slot. If you keep a row of presets for one slider, the one that matches lights up instead.
- Any of the three is dimmed when ZBrush would ignore it right now. Everything under **Tool:Masking** is like that while no mesh is in Edit mode. Before, you found out after the pick, from the message near the cursor.

A dimmed slot can still be picked. What the ring knows can be up to half a minute old, and I'd rather it let you pick something that turns out to be greyed than refuse something that's there.

Fans get the marks too. Brush, alpha, material and texture slots stay as they were. [ZBrush's state on the ring](../../menus.md#zbrushs-state-on-the-ring) has the details.

## It asks as the ring opens

I wanted ZBrush to tell ZOrbit whenever something changed. It can't. The Python inside ZBrush 2026 and newer, where the plugin runs, has no events and no timers, and a background thread I started there ran once and never woke up again.

Asking is cheap, though. So ZOrbit asks at the moment the ring opens. Nothing changes in ZBrush while a ring is open, so an answer from that moment is as good as a live one. After every pick the plugin answers again without being asked, so the next ring already knows what the pick changed.

The ring never waits for the answer. It opens as it did in 0.24.0, and the marks appear when the answer arrives.

## How quickly the marks arrive

I measured it in ZBrush 2026 with my own menus. My Tools ring has eight slots that ZOrbit asks about.

| What | How long |
|---|---|
| Reading those eight in ZBrush | 2 ms |
| From the question to the answer, as the app logs it | 16 ms |
| From the ring on screen to its marks | about 19 ms |

With the default animation the slots take 120 ms to fade in, so the marks are there well before the ring has finished appearing.

There is a cap so a huge menu can't hold ZBrush up: ZOrbit asks about 128 buttons at most, and the plugin stops reading after 20 ms. A ring that big would still answer in about 35 ms.

## While you sculpt, and while ZBrush is busy

This was the part I wasn't sure of. You can open the ring in the middle of a stroke, and if ZBrush stopped listening while the pen was down, the ring would have nothing to show.

It keeps listening. I had a script ask every 30 ms while I held a stroke with the pen for almost six seconds. All 117 questions were answered, at the same speed as with the pen up. A stroke made with the mouse gave the same result.

A long DynaMesh is different. ZBrush can't answer until it's done, so I opened a ring in the middle of one. The ring was on screen at once. The answer came 0.8 seconds later, when ZBrush was free again, and the marks appeared then. A ring that already knew the state from earlier showed its marks from the start.

## After you update

Restart ZBrush once. ZBrush keeps running the plugin it loaded when it started, and the old one can't answer, so there are no marks until the new one is loaded. **Zplugin > ZOrbit > Status** then has a **State channel** line.

If you'd rather have no marks, switch off **Show ZBrush's state on the ring** in **Settings > ZBrush bridge** (Full mode). It's on by default and kept per profile.

ZBrush 2022 to 2025 don't get any of this. Their plugin is a ZScript that only runs at the moment a pick is carried out. It could report the state then, but not when you flip a switch in ZBrush yourself, so the ring would often be wrong, and I think that's worse than showing nothing.

## One that is always dimmed

While testing I found that ZBrush tells the plugin **Edit:Undo** and **Edit:Redo** are greyed, even with a stroke to undo. Pressing **Edit:Undo** through the plugin does nothing either. None of the starter menus has an Undo slot, but if yours does, it will look dimmed. Use **Ctrl+Z** in ZBrush for undo. [Troubleshooting](../../troubleshooting.md#a-slot-is-dimmed) has this and the other reasons a slot can be dimmed.

## What comes next

The [subtools fan](https://github.com/combwizard/zorbit/issues/193) builds on this: a slot that fans out the subtools of the active tool, with the current one marked. It's the one I want most. A mark on the brush you have selected would use the same answers.

If you'd use either, add a thumbs-up to its issue. I'd also like to hear which switches and sliders you put on a ring now that it can show them.

## How this release was tested

The test suite has over 3,000 tests now. Among other things, the new ones check that a ring with no marks draws exactly the picture 0.24.0 drew, pixel for pixel. Then I ran it in a real ZBrush 2026: the numbers above, a stroke with the mouse and one with the pen, a long DynaMesh, and a look at the ring to check the marks matched the switches in ZBrush.

The full list is in the [release notes](https://github.com/combwizard/zorbit/releases/tag/v0.25.0).
