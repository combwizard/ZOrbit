# Hotkeys and picking

## Hotkeys

A menu hotkey is written like this:

```
Q          Alt+G          Ctrl+Shift+1          F9          `
```

- Keys: letters, digits, F1 to F24, and `space tab enter backspace insert delete home end pageup pagedown` and the punctuation keys `` ` - = [ ] \ ; ' , . / ``.
- `~` is accepted for the backtick key.
- In Studio, the **Hotkey** field records the key you press. Numpad keys cannot be recorded (the app has no names for them): use the main row. Letters and digits are recorded as the key your layout gives them, so Dvorak and AZERTY record what you pressed. A punctuation key is recorded by its place on a US keyboard, so Studio accepts it only when your layout types the same character there; otherwise it says "This key is in a different place on your keyboard layout. Pick another."
- Modifiers: `Ctrl`, `Alt`, `Shift`, in any combination, joined with `+`. `Control` also works for `Ctrl`.
- Each hotkey can belong to only one menu. The menu that comes first in `radial.json` keeps the key. A later menu with the same key is reported as a problem and has no hotkey, so it works only as a submenu. A menu with no usable items does not count: it never takes the key.
- A hotkey only works while **ZBrush is the front window**. In every other program the key behaves normally. The browser hotkey is the one exception: it also works while the browser is in front, where it hands the keyboard back to ZBrush.
- Keys sent by a tablet driver (Wacom, Huion or XP-Pen key mappings, for example), a macro tool or a key remapper work like the real key. Only ZOrbit's own key presses are ignored.
- Press the hotkey again while its ring is open to close it. **Esc** also closes the ring.
- The browser has a hotkey of its own, `browser.hotkey`, written the same way (see [Browser hotkey](appearance.md#browser-hotkey)). It cannot be a key a menu already uses: the menu wins and the browser hotkey is reported as a problem. It is swallowed like a menu hotkey. Press it again while the browser is in front to hand the keyboard back to ZBrush; the browser stays open.

By default a menu **swallows** its hotkey: ZBrush never sees it, so it does not also run its own shortcut for that key. Set `"swallow": false` (or switch it off in the menu settings in Studio) if you want the key to keep working in ZBrush too. The starter **Brushes** menu has it off, because **Q** is ZBrush's Draw-mode key: ZBrush goes back to Draw mode as the ring opens, and **Q** still types in ZBrush's own text fields.

## Pick modes

There are two ways to pick, and the same hotkey does both.

**Hold and release.** Hold the hotkey, move the cursor toward a slot, and release. The slot under the cursor is picked. If the cursor is in the middle (the dead zone) when you release after the tap time, nothing is picked and the ring closes.

**Tap and click.** A release within the **tap time** (250 ms by default) counts as a tap only when no slot is under the cursor, that is, the cursor is still in the middle of the ring (the dead zone) or points where no slot is. The ring stays open. Move to a slot and click it. If a slot is under the cursor when you let go, that slot is picked, however fast the release. A release after the tap time with nothing under the cursor closes the ring without picking. The middle of the ring, a right-click, **Esc**, a click outside the ring, or the auto-close timer all cancel without picking.

**Flick.** In either mode, move the cursor out past a slot's outer edge and that slot is picked straight away. You don't have to release the hotkey or click. Press the hotkey, flick toward a slot, and it's done. Turn this off with **Flick to pick** in Settings (`"flick": false`). With flicking on, moving out of the ring toward a slot picks it, so a click outside the ring usually cannot cancel. It can in a ring of one to three slots, where each slot covers at most a quarter of the circle and the directions between them pick nothing, and past an empty auto or tag slot, which picks nothing either. The sure ways to cancel are the middle of the ring, a right-click and **Esc**.

**Submenus.** Move the cursor onto a submenu's slot and the submenu opens right away, centred on that slot. If you are still holding the hotkey, you stay in hold-and-release mode, so one movement can go into a submenu and on to one of its items:

- Release over an item, or flick past it, to pick it.
- Release in the middle (where the submenu slot was) to keep the submenu open and click an item.

Turn this off with **Open submenus on hover** in Settings, which needs [Full mode](studio.md#simple-and-full-mode) (`"hover_submenus": false`). Submenus then open when you release or click on them, as before.

![Settings > Behaviour in Full mode: switches for Flick to pick and Open submenus on hover, and sliders for Tap time at 250 ms and Auto-close at 20 s](images/settings-behaviour.png)

**Fans.** A submenu whose menu has `"fan": true` opens as a fan instead of a new ring: its items spread out beyond the submenu's slot with dashed lines to each one, and the ring you came from stays where it is. The rules are the same as above:

- Release over a fan item, click it, or flick past it to pick it.
- Release on the fan's own slot to keep the fan open and click an item.
- A fan item that is itself a fan submenu fans out further, up to three deep, and the earlier fans stay visible.
- Moving the cursor out of a fan closes it.
- If there is no room for the fan (the ring is near a screen edge), or the fan would lead back to a menu that is already open, the submenu opens as a normal ring instead.

Notes:

- A slot is chosen by the *direction* of the cursor from the centre, not by hitting the icon. You can point toward a slot and release without moving far. Within the **dead zone** radius no slot is chosen. Each slot covers at most a quarter of the circle, so in a ring with one to three slots, pointing away from all of them chooses nothing.
- The slot under the cursor grows slightly, gets an accent ring, and its label changes colour.
- The ring never takes keyboard focus, so ZBrush keeps working normally behind it.
- If the cursor is near a screen edge, the ring is moved onto the screen, so it opens with the cursor off-centre or even on a slot. Until the cursor has been inside the ring and off every slot, nothing is picked or opened by hover or flick, and the hint in the middle says **move into the ring**. If you let go of the hotkey before that, the ring stays open for a click instead of picking anything.
- With **Flick to pick** off, a click outside the ring cancels it, but that click also reaches ZBrush underneath, so it can land a stroke or press a button. **Esc** or a right-click is the safer way to cancel.
- A menu that swallows its hotkey swallows it in ZBrush's own text fields too, so a plain letter such as **Q** cannot be typed there while such a menu uses it. Pick a key you do not type in ZBrush (see [Pressing the hotkey does nothing](troubleshooting.md#pressing-the-hotkey-does-nothing)).
- Typing another key closes a ring that was opened by a tap and is waiting for a click. The key reaches ZBrush as normal. A modifier on its own, or another of your hotkeys, does not close it.
- The hotkey is ignored, and reaches the program as an ordinary key, while a native Windows dialog (Save As, Open, a message box) is in front or a Windows text box has the focus, so you can type it there. The browser hotkey follows the same rule. ZBrush's own text fields are not Windows text boxes, so there the ring still opens and the next letter you type closes it.
