"""The look of the ring as data: the keys a look can hold, their ranges and defaults, the built-in looks, the checks
that read a look out of radial.json, and the layering that turns them into the values the ring draws.

A look is a flat dict of look keys (see LOOK_KEYS). It lives at five levels, each one over the one before:

    defaults, then the theme's colours, then the ring.look preset, then the ring's own keys, then the menu's
    preset, then the menu's own keys, then (for one slot) the item's style.

Colours are a theme role (ROLES) or a fixed #rrggbb. Roles are resolved after the layers are merged, so a menu that
sets colors.accent recolours a hub whose colour is the role "accent". The five palette colours in "colors" are
#rrggbb only.

This module imports only the standard library and theme. config.py reads radial.json with it and re-exports the old
names; the ring and Studio take the resolved dicts config.py builds.
"""
import difflib
import re

import theme as T

ROLES = ("bg", "accent", "highlight", "text", "lines")

ANIMATIONS = ("smooth", "bounce", "pop", "zoom", "fade", "drift", "fancy", "spiral", "ripple", "breath", "mist",
              "snappy")
LABEL_MODES = ("name", "none")
TAG_COLOR_MODES = ("none", "tint", "glow", "both")
TAG_BANDS = ("none", "hairline", "narrow", "medium", "wide")
TINT_STYLES = ("flat", "gradient")
TINT_BLENDS = ("multiply", "overlay")
SLOT_SHAPES = ("circle", "rounded", "squircle", "hexagon", "octagon", "diamond")
HUB_STYLES = ("dot", "disc", "ring", "icon")          # a hub of 0 is no hub at all
WHEN_FULL = ("grow", "rings", "more")

# the names a JavaScript object already has; Studio holds menus (and looks) in one, so such a name would break it
RESERVED_MENU_IDS = frozenset({"__proto__", "constructor", "hasOwnProperty", "isPrototypeOf", "propertyIsEnumerable",
                               "toLocaleString", "toString", "valueOf", "__defineGetter__", "__defineSetter__",
                               "__lookupGetter__", "__lookupSetter__"})

LOOK_KEYS = ("radius", "slot", "dead_zone", "slot_shape", "slot_corner", "border_width", "icon_scale", "hub",
             "hub_style", "hub_color", "hub_glow", "glow_color", "glow_opacity", "labels", "label_color", "colors",
             "tag_colors", "tag_band", "tag_band_opacity", "tag_glow_opacity", "tag_tint_opacity", "tag_tint_style",
             "tag_tint_blend", "when_full")
BEHAVIOUR_KEYS = ("tap_ms", "timeout_s", "flick", "hover_submenus", "hint", "tag_limit", "animation")
RING_ONLY_KEYS = BEHAVIOUR_KEYS + ("look",)           # in "ring" only: not part of a look
RING_KEYS = LOOK_KEYS + BEHAVIOUR_KEYS + ("look",)
STYLE_KEYS = ("slot_shape", "slot_corner", "border_width", "icon_scale", "label_color", "glow_color", "size",
              "fill_color", "border_color")
COLOUR_KEYS = ("hub_color", "glow_color", "label_color", "fill_color", "border_color")
EMPTY_COLOUR_KEYS = ("glow_color", "fill_color", "border_color")      # "" = none chosen

RANGES = {"radius": (60, 400), "slot": (32, 160), "dead_zone": (10, 120), "slot_corner": (0, 0.5),
          "border_width": (0, 6), "icon_scale": (0.5, 1), "hub": (0, 64), "hub_glow": (0, 1),
          "glow_opacity": (0, 1), "tag_band_opacity": (0, 1), "tag_glow_opacity": (0, 1),
          "tag_tint_opacity": (0, 1), "tap_ms": (0, 1000), "timeout_s": (2, 120), "tag_limit": (4, 24),
          "size": (0.75, 1.25)}
CHOICES = {"slot_shape": SLOT_SHAPES, "hub_style": HUB_STYLES, "labels": LABEL_MODES, "tag_colors": TAG_COLOR_MODES,
           "tag_band": TAG_BANDS, "tag_tint_style": TINT_STYLES, "tag_tint_blend": TINT_BLENDS,
           "when_full": WHEN_FULL, "animation": ANIMATIONS}
SWITCHES = ("flick", "hover_submenus", "hint")
WHOLE_NUMBERS = ("tag_limit",)                         # ranges that take whole numbers only

LOOK_DEFAULTS = {"radius": 145, "slot": 72, "dead_zone": 38, "slot_shape": "circle", "slot_corner": 0.28,
                 "border_width": 2, "icon_scale": 1.0, "hub": 10, "hub_style": "dot", "hub_color": "accent",
                 "hub_glow": 1.0, "glow_color": "", "glow_opacity": 0.55, "labels": "name", "label_color": "text",
                 "tag_colors": "tint", "tag_band": "medium", "tag_band_opacity": 0.45, "tag_glow_opacity": 0.4,
                 "tag_tint_opacity": 0.3, "tag_tint_style": "gradient", "tag_tint_blend": "multiply",
                 "when_full": "grow"}
BEHAVIOUR_DEFAULTS = {"tap_ms": 250, "timeout_s": 20, "flick": True, "hover_submenus": True, "hint": True,
                      "tag_limit": 12, "animation": "smooth"}
STYLE_DEFAULTS = {"size": 1.0, "fill_color": "", "border_color": ""}     # the slot-only keys, when a style sets them

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_NAME = re.compile(r"\w(?:[\w -]{0,30}\w)?")

# built-in looks: style only (no geometry, colours or tag_*), theme roles only
BUILTIN = {
    "classic": {"label": "Classic", "blurb": "Round slots with an accent dot: the look ZOrbit starts with.",
                "look": {}},
    "soft": {"label": "Soft", "blurb": "Rounder, softer slots with a quiet disc in the middle.",
             "look": {"slot_shape": "squircle", "border_width": 1, "icon_scale": 0.92, "glow_opacity": 0.7,
                      "hub_style": "disc", "hub_glow": 0.6}},
    "tiles": {"label": "Tiles", "blurb": "Square tiles with rounded corners and a ring in the middle.",
              "look": {"slot_shape": "rounded", "slot_corner": 0.22, "icon_scale": 0.9, "glow_opacity": 0.45,
                       "hub_style": "ring", "hub": 14}},
    "crystal": {"label": "Crystal", "blurb": "Hexagons with a bright highlight glow.",
                "look": {"slot_shape": "hexagon", "icon_scale": 0.85, "glow_opacity": 0.8,
                         "glow_color": "highlight", "hub_style": "ring", "hub": 16, "hub_color": "highlight"}},
    "circuit": {"label": "Circuit", "blurb": "Thin-rimmed octagons in the line colour.",
                "look": {"slot_shape": "octagon", "border_width": 1, "label_color": "highlight",
                         "glow_color": "lines", "glow_opacity": 0.4, "hub_style": "ring", "hub": 12,
                         "hub_color": "lines"}},
    "diamonds": {"label": "Diamonds", "blurb": "Diamond slots with small icons.",
                 "look": {"slot_shape": "diamond", "icon_scale": 0.7, "border_width": 2, "hub_style": "disc",
                          "hub": 12}},
    "minimal": {"label": "Minimal", "blurb": "No rim, a faint glow and a tiny dot.",
                "look": {"border_width": 0, "glow_opacity": 0.3, "hub": 6, "hub_glow": 0}},
}


def did_you_mean(key, known) -> str:
    near = difflib.get_close_matches(str(key), list(known), n=1)
    return f" (did you mean {near[0]}?)" if near else ""


def is_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def colour(value, colors) -> str:
    """A role as the #rrggbb it has in colors, a #rrggbb as it is, "" as "". Anything else comes back unchanged."""
    if value in ROLES and isinstance(value, str):
        return colors.get(value, value)
    return value


def _fold(layers):
    """layers: [(origin, name, look dict)]. Returns (values, origins) with the colours merged per key."""
    vals, org = {}, {}
    for src, name, layer in layers:
        for k, v in (layer or {}).items():
            if k == "colors":
                got = vals.setdefault("colors", {})
                for ck, cv in v.items():
                    got[ck] = cv
                    org["colors." + ck] = {"from": src, "name": name}
            else:
                vals[k] = v
                org[k] = {"from": src, "name": name}
    return vals, org


def merge(*layers) -> dict:
    """The look dicts laid over each other, later ones winning key by key (colors per colour). Roles stay roles."""
    return _fold([("", "", layer) for layer in layers])[0]


def resolve_colours(look) -> dict:
    """A copy of the look with the roles in hub_color, glow_color, label_color (and a slot's fill_color and
    border_color) turned into the #rrggbb they have in look["colors"]."""
    out = dict(look)
    out["colors"] = dict(look.get("colors") or {})
    for k in COLOUR_KEYS:
        if k in out:
            out[k] = colour(out[k], out["colors"])
    return out


def tag_colours_on(look) -> bool:
    """Slots carry their tag colour unless every way of showing it is off."""
    return look.get("tag_colors", "tint") != "none" or look.get("tag_band", "medium") != "none"


# --- reading a look out of radial.json -----------------------------------------------------------------
def check_look(raw, errors, prefix, allow) -> dict:
    """The valid values of a raw look dict, as a dict (colors as a partial dict). Anything else is reported in
    errors as f"{prefix}{key}: ..." and left out. allow: the keys the level may hold. The key "look" of a ring
    is the caller's to check."""
    out = {}
    for k, v in raw.items():
        if k not in allow:
            if k in RING_ONLY_KEYS:
                errors.append(f"{prefix}{k}: is a ring setting, not part of a look; ignored")
            else:
                errors.append(f"{prefix}{k}: unknown setting" + did_you_mean(k, allow))
        elif k == "look":
            continue
        elif k == "colors":
            if not isinstance(v, dict):
                errors.append(f'{prefix}colors: must be an object like {{"accent": "#f86b33"}}')
                continue
            got = {}
            for ck, cv in v.items():
                if ck in ROLES:
                    if is_hex(cv):
                        got[ck] = cv
                    else:
                        errors.append(f"{prefix}colors.{ck}: {cv!r} is not a #rrggbb colour")
                else:
                    errors.append(f"{prefix}colors.{ck}: unknown colour" + did_you_mean(ck, ROLES))
            if got:
                out["colors"] = got
        elif k in COLOUR_KEYS:
            if (isinstance(v, str) and v in ROLES) or is_hex(v) or (v == "" and k in EMPTY_COLOUR_KEYS):
                out[k] = v
            else:
                errors.append(f"{prefix}{k}: {v!r} is not a #rrggbb colour or a theme colour ({', '.join(ROLES)})")
        elif k in RANGES:
            lo, hi = RANGES[k]
            whole = k in WHOLE_NUMBERS
            if (not isinstance(v, bool) and isinstance(v, (int, float)) and lo <= v <= hi
                    and (not whole or v == int(v))):
                out[k] = int(v) if whole else v
            else:
                errors.append(f"{prefix}{k}: {v!r} must be a {'whole number' if whole else 'number'} from {lo} to {hi}")
        elif k in SWITCHES:
            if isinstance(v, bool):
                out[k] = v
            else:
                errors.append(f"{prefix}{k}: {v!r} must be true or false")
        elif k in CHOICES:
            if isinstance(v, str) and v in CHOICES[k]:
                out[k] = v
            else:
                errors.append(f"{prefix}{k}: {v!r} unknown; one of {', '.join(CHOICES[k])}")
    return out


def check_style(raw, errors, where) -> dict:
    """The valid values of an item's style. where: "menu <id> item <n>"."""
    if not isinstance(raw, dict):
        errors.append(f'{where}: style must be an object like {{"slot_shape": "hexagon"}}; ignored')
        return {}
    return check_look(raw, errors, f"{where}: style.", STYLE_KEYS)


def valid_name(name) -> str:
    """"" if this can be the name of a user look, else what is wrong with it."""
    if not isinstance(name, str) or not _NAME.fullmatch(name) or len(name) > 32:
        return "name must be 1 to 32 letters, digits, spaces, - or _"
    if name.casefold() in BUILTIN or name in RESERVED_MENU_IDS:
        return "that name is a built-in look or is reserved, give it another"
    return ""


def check_presets(raw_looks, errors) -> dict:
    """The user looks of radial.json's "looks" object: {name: valid look dict}. A look that cannot be used is
    reported and left out; a bad value in one is left out of that look alone."""
    if raw_looks is None:
        return {}
    if not isinstance(raw_looks, dict):
        errors.append('looks: must be an object like {"My look": {"slot_shape": "hexagon"}}; ignored')
        return {}
    out, seen = {}, {}
    for name, raw in raw_looks.items():
        problem = valid_name(name)
        if problem:
            errors.append(f"looks.{name}: {problem}; ignored")
            continue
        if name.casefold() in seen:
            errors.append(f"looks.{name}: same name as {seen[name.casefold()]!r} apart from capitals; ignored")
            continue
        seen[name.casefold()] = name
        if not isinstance(raw, dict):
            errors.append(f"looks.{name}: not an object; ignored")
            del seen[name.casefold()]
            continue
        if "preset" in raw:
            errors.append(f"looks.{name}.preset: a look cannot be based on another look; ignored")
            raw = {k: v for k, v in raw.items() if k != "preset"}
        out[name] = check_look(raw, errors, f"looks.{name}.", LOOK_KEYS)
    return out


# --- the layers ----------------------------------------------------------------------------------------
def _defaults() -> dict:
    return {**BEHAVIOUR_DEFAULTS, **LOOK_DEFAULTS, "colors": T.ring_colors("dark")}


class LookSet:
    """The looks of one radial.json: the user's presets, the ring's own values (valid look and behaviour keys, and
    "look" for its preset) and the theme in force. Every method returns a fresh dict."""

    def __init__(self, user=None, ring=None, theme="dark"):
        self.user = user or {}
        self.ring = ring or {}
        self.theme = T.effective(theme)

    def preset(self, name):
        """The look dict of a user or built-in look, or None."""
        if not isinstance(name, str) or not name:
            return None
        if name in self.user:
            return self.user[name]
        return BUILTIN[name]["look"] if name in BUILTIN else None

    def names(self) -> list:
        return list(BUILTIN) + list(self.user)

    def _global_layers(self):
        layers = [("default", "", _defaults())]
        if self.theme != "dark":
            layers.append(("theme", "", {"colors": T.ring_colors(self.theme)}))
        name = self.ring.get("look")
        if self.preset(name) is not None:
            layers.append(("global-preset", name, self.preset(name)))
        layers.append(("global", "", {k: v for k, v in self.ring.items() if k != "look"}))
        return layers

    def _menu_layers(self, spec):
        layers = self._global_layers()
        spec = spec or {}
        name = spec.get("preset") or ""
        if self.preset(name) is not None:
            layers.append(("menu-preset", name, self.preset(name)))
        layers.append(("menu", "", {k: v for k, v in spec.items() if k != "preset"}))
        return layers

    def _finish(self, vals) -> dict:
        out = resolve_colours(vals)
        if self.theme != "dark":
            out["theme"] = self.theme
        return out

    def global_look(self) -> dict:
        """The ring's look as the renderer takes it: every look and behaviour key, roles resolved to #rrggbb. A
        theme other than dark is stamped as "theme" (for the ring's neutrals)."""
        return self._finish(_fold(self._global_layers())[0])

    def menu_look(self, spec=None) -> dict:
        """The global look with a menu's look_spec ({"preset": name or "", overrides}) laid over it."""
        return self._finish(_fold(self._menu_layers(spec))[0])

    def slot_look(self, menu_look, style=None) -> dict:
        """A menu's resolved look with one item's style over it (its roles resolved by the menu's colours)."""
        style = resolve_colours({**(style or {}), "colors": menu_look.get("colors") or {}})
        style.pop("colors")
        return {**menu_look, **style}

    def origins(self, spec=None, style=None) -> dict:
        """{key: {"from": ..., "name": ...}} for every key of the look at that level, the colours as
        "colors.accent" and so on. "from" is default, theme, global-preset, global, menu-preset, menu or slot;
        "name" is the preset's name for the two preset origins, else ""."""
        org = _fold(self._menu_layers(spec) if spec is not None else self._global_layers())[1]
        for k in style or {}:
            org[k] = {"from": "slot", "name": ""}
        return org

    def explain(self, spec=None, style=None) -> dict:
        """{"values", "origins"} at the level asked for: the slot's when style is given, else the menu's, else the
        global look. For comparing another resolver against this one."""
        look = self.menu_look(spec) if spec is not None else self.global_look()
        if style is not None:
            look = self.slot_look(look, style)
        return {"values": look, "origins": self.origins(spec, style)}
