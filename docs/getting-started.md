# Getting started

## The basics

ZOrbit is two things that work together:

- a small **app** that watches for your hotkeys and draws the ring, and
- a **plugin inside ZBrush** (the bridge, see [How ZOrbit talks to ZBrush](bridge.md)) that carries out what you picked.

You do not start either by hand. ZBrush loads the plugin when it starts, the plugin starts the app, and the app quits when ZBrush closes. The app has an icon in the notification area: left-click it to open Studio ([The tray icon](studio.md#the-tray-icon) lists its other commands).

With ZBrush in front, press **Q**. The ring opens centred on your cursor. Pick a slot (see [Pick modes](hotkeys.md#pick-modes)) and ZBrush does what the slot says.

![The Brushes menu](images/ring.png)

Slots are laid out clockwise starting at the top. A slot with a small arrow badge opens another ring. A small fan badge means its items fan out from that slot instead. The menu's title and a short hint sit in the middle.

**What ZOrbit takes over.** **Q** is ZBrush's own key for Draw mode. The starter menu lets it through, so ZBrush switches to Draw mode when the ring opens, and **Q** still types in ZBrush's own text fields. To hide a key from ZBrush instead, switch on **Swallow hotkey** in the menu settings on the **Menus** screen (see [Hotkeys](hotkeys.md)). **Alt+B** opens the [browser](browser.md); change it on the **Settings** screen (see [Browser hotkey](appearance.md#browser-hotkey)). ZBrush 2022 to 2025 also use **F9** for the plugin; change that on the **Settings** screen under **ZBrush bridge** (see [ZBrush 2022 to 2025](bridge.md#zbrush-2022-to-2025)).

## First steps

1. Open **ZOrbit Studio** from the Start menu (or from ZBrush: **Zplugin > ZOrbit > Studio**).
2. On the **Menus** screen, pick a menu on the left. The ring preview in the middle is drawn by the same code that draws it inside ZBrush.
3. Drag brushes from the **Library** onto the ring, or use **Add item** to add a brush, alpha, material, texture or submenu. Studio starts in **Simple** mode, which shows the everyday controls. Press **Full** in the top bar for buttons, sliders, switches and the rest (see [Simple and Full mode](studio.md#simple-and-full-mode)).
4. Click **Save** (Ctrl+S). The next time you open the ring in ZBrush it uses your changes. There is no need to restart anything.

<p align="center">
  <img src="images/studio.png" alt="ZOrbit Studio on the Menus screen: the menu list, the ring preview of the Brushes menu, its item list and the Menu settings panel">
</p>

Next: [ZOrbit Studio](studio.md) covers the editor, [Menus and items](menus.md) every item type, and [Appearance](appearance.md) every setting.
