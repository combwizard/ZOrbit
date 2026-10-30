# Menus and items

## Menus

A menu is a named list of items shown as one ring. Menus live in one file, `%APPDATA%\ZOrbit\radial.json`. Each has an id (its key in the file), a title, a list of items, and optionally a hotkey.

- A menu **with a hotkey** can be opened from ZBrush.
- A menu **without a hotkey** is a submenu: it opens when you pick an item of type `menu` in another ring.
- Rings work best with 4 to 12 items. They are spread evenly around the circle.
- At least one menu needs a hotkey, otherwise nothing can open the ring.
- A menu can have its own open animation (`"animation": "spiral"`, or pick one in the menu settings in Studio). Without one it uses `ring.animation`. See [Open animations](appearance.md#open-animations).
- A menu can **fan out** when it is opened as a submenu (`"fan": true`, or switch on **Fan out when opened from another menu** in the menu settings in Studio). See [Submenu](#submenu).

Starter menus ship with ZOrbit: **Brushes** (Q), with submenus **More Brushes**, **Tools** (masking, symmetry, PolyFrame, LazyMouse and other switches, a **Browser** slot that opens the [browser](browser.md), and a **Favourites** slot) and **SubDivide** (a row of stroke subdivide sizes). They use only brushes that come with ZBrush. New installs get the **Favourites** slot in **Tools**; existing menus are not changed.

## Item types

Every item does exactly one thing. Besides the action, an item can have a `label` (the text under the slot; if you leave it out, one is made from the action) and an `icon`.

| Type | What it does |
|---|---|
| `brush` | Selects a brush. If it is not loaded yet, it is loaded from its `.zbp` file first. |
| `alpha` | Selects an alpha. If it is not loaded yet, it is imported from its file first. |
| `material` | Selects a material. If it is not loaded yet, it is loaded from its file first. |
| `texture` | Selects a texture. If it is not loaded yet, it is imported from its file first. |
| `press` | Presses any ZBrush button, by its interface path. |
| `set` | Sets a slider or value. Needs a `value`. |
| `toggle` | Flips a switch on or off. |
| `steps` | Runs a list of the actions above, in order. |
| `menu` | Opens another ring in place of this one. |
| `tag` | Opens a fan of every installed item that carries a tag, or the Favourites tag: brushes first, most used first, then alphas, materials and textures. |
| `browser` | Opens the [browser](browser.md) on one of its tabs, optionally on one tag. |

### Brush

```json
{"brush": "ClayBuildup"}
{"brush": "Inflat", "label": "Inflate"}
```

The name is the brush's name in ZBrush (the file name without `.zbp`). Spaces and capitals do not matter when ZOrbit looks the file up. The slot's icon is the brush's own thumbnail. If ZBrush already has the brush loaded, it is simply selected. If not, ZOrbit looks for a `.zbp` in your ZBrush brush folders and loads it. If it finds none, the pick is logged as "NOT loaded in ZBrush and no file known".

### Alpha, material and texture

```json
{"alpha": "Alpha 058"}
{"material": "SkinShade4", "label": "Skin"}
{"texture": "Txtr01"}
```

The name is the file's name without its extension. Spaces and capitals do not matter when ZOrbit looks the file up. If
two folders hold a file with the same name, the first folder searched wins. ZOrbit searches these folders, in order:

- **ZBrush 2026 and newer:** `ZStartup\Alphas`, `ZStartup\Materials` and `ZStartup\Textures` in your user folder (shown
  as **My Alphas**, **My Materials** and **My Textures**), then the installation's `ZData\Alphas`, `ZData\Materials` and
  `ZData\Textures` (shown as **ZBrush**), then its `Lightbox\Alphas`, `Lightbox\Materials` and `Lightbox\Textures`
  (shown as **Lightbox**).
- **ZBrush 2022 to 2025:** `ZStartup\Alphas`, `ZStartup\Materials` and `ZStartup\Textures`, then the installation's
  `ZData\...` folders, then its `ZAlphas`, `ZMaterials` and `ZTextures` folders.

Alphas can be `.psd`, `.bmp`, `.jpg`, `.png` or `.tif` files. Materials are `.zmt` files. Textures can be `.psd`, `.jpg`,
`.png`, `.bmp`, `.tif` or `.exr` files.

If ZBrush already has the item loaded, it is simply selected. ZOrbit looks for a button with its name (`Alpha:<name>`,
`Material:<name>` or `Texture:<name>`). If there is none, ZOrbit loads the file with **Alpha > Import**, **Material > Load**
or **Texture > Import**, then selects the item.

**Material > Load** replaces the material in the currently selected material slot, the same as ZBrush does when you load
one yourself. Select the slot you do not mind overwriting before you pick a material that is not loaded yet.

Thumbnails: a material uses the icon stored in its `.zmt` file. A few old MatCap files have none, and they show the
placeholder. An alpha or texture uses its image file. EXR textures have no thumbnail, so they show the placeholder too.
Thumbnails are cached in `%LOCALAPPDATA%\ZOrbit\thumbs`.

ZBrush 2022 to 2025 get these through the [ZScript plugin](install.md#zbrush-2022-to-2025). Until you update it in **Studio > Settings > Older ZBrush >
Update**, the old plugin skips them.

### Press

```json
{"press": "Tool:Masking:Clear", "label": "Clear Mask"}
```

An interface path is the chain of palette and button names, joined with colons, as ZBrush shows them. Capitals do not matter. Studio suggests common paths as you type.

### Set

```json
{"set": "Draw:Draw Size", "value": 64}
{"set": "Stroke:SubDivide Size", "value": 1.25, "label": "1.25"}
```

`value` is a number.

### Toggle

```json
{"toggle": "Transform:Activate Symmetry", "label": "Symmetry"}
{"toggle": "Stroke:LazyMouse"}
```

### Steps

```json
{"steps": [{"press": "Tool:Masking:Clear"}, {"brush": "Standard"}],
 "label": "Fresh Start", "icon": "Standard"}
```

Steps run in order. Each step is a `brush`, `alpha`, `material`, `texture`, `press`, `set` or `toggle`. Steps cannot open menus, cannot contain more steps, and cannot hold `tag` or `browser` items. Without an `icon`, a `steps` item uses the thumbnail of its first brush, alpha, material or texture step, or a placeholder if it has none.

### Submenu

```json
{"menu": "more", "label": "More Brushes"}
```

`"more"` is the id of another menu in the file. Moving the cursor onto the submenu's slot (or flicking past it) opens the new ring centred on that slot. If you are still holding the hotkey, it stays in hold-and-release mode. Releasing or clicking on the submenu's direction before you reach the slot opens it centred on your cursor, in tap-and-click mode. See [Pick modes](hotkeys.md#pick-modes).

A submenu can open another way. Give its menu `"fan": true` (or switch on **Fan out when opened from another menu** in the menu settings in Studio) and its items spread out in an arc beyond its slot, joined to it by dashed lines, instead of a new ring opening on the slot. The ring you came from stays visible. An item of a fan can itself be a submenu of a fan, and it fans out further (up to three deep). The option only matters when the menu is opened as a submenu. A menu with a hotkey still opens as a normal ring when you press it. See [Pick modes](hotkeys.md#pick-modes) for how to pick from a fan.

![More Brushes fanned out from the Brushes ring, with ClayTubes hovered](images/fan.png)

### Tag

```json
{"tag": "blocking"}
{"tag": "detailing", "label": "Detail"}
{"tag": "favourite"}
```

The name is the tag's key, not its label. The key is made once, from the label, when the tag is created (`Blocking` becomes `blocking`), and it stays the same when you rename the tag, so slots keep working. In Studio you pick the tag from a list and never need to type the key. See [Tags](tags.md).

The slot opens a fan of every installed item with that tag. The brushes come first, most used first (the same count that fills auto slots, so their order can shift after you pick). Then come the alphas, materials and textures with that tag, by name. A fan holds up to 12 slots. If the tag has more items, the last slot is **More...**, which opens the [browser](browser.md) on the tab of the first item in the fan, on that tag. Picking a brush from the fan works like any brush pick and counts towards auto slots. Picking an alpha, material or texture works as it does from the browser. If there is no room for a fan, the tag's items open as a normal ring. The slot is a disc in the tag's colour with a tag symbol and a submenu badge. Without a `label`, it is named after the tag.

A tag that has no installed items is a faint tag symbol, and picking it does nothing. So is a key that is not in `tags.json`, which is also listed as a problem ("tag 'x' does not exist; the slot stays empty").

The `favourite` key is the built-in Favourites tag (see [Tags](tags.md)). A `{"tag": "favourite"}` slot opens a fan of
your starred items, in the same order as any tag, with the same 12-slot cap and **More...** slot. It is drawn with a
star instead of the tag symbol. New installs have one in the starter **Tools** menu.

### Browser

```json
{"browser": ""}
{"browser": "blocking", "label": "Blocking"}
{"browser": "", "kind": "alpha", "label": "Alphas"}
```

Opens the [browser window](browser.md). `kind` chooses the tab it opens on: `brush` (the default), `alpha`, `material` or `texture`. Nothing is sent to ZBrush until you pick an item in it. `""` shows every item of that kind; a tag key opens it on that tag. A key that is not in `tags.json` is listed as a problem and the browser opens unfiltered. Without a `label`, the slot is called **Browser**, or the tag's name when it filters. In Studio, the **Shows** select in the inspector sets `kind`, and the **Tag filter** field lists your tags.

### Labels and icons

- `label`: text shown under the slot. Long labels are shortened with an ellipsis.
- `icon`: a brush name, the path to a `.zbp`, or the path to a `.png` file. Without one, brush, alpha, material and texture items use the item's own thumbnail, and a `steps` item uses the thumbnail of its first asset step. Other items show a round placeholder with a short text.
