"""Where the slots of a ring sit: how far out, at what angle, and how many fit. Pure maths, no Pillow and no win32,
so config, the expander and the renderer can all import it.

Angles are uniform (360 / n degrees apart, 0 at 12 o'clock, clockwise) whatever the slot sizes. The radius is a
minimum: a ring grows until the two neighbouring slots that need the most room are SLOT_GAP slot widths apart.
With equal sizes that is exactly the old SLOT_GAP * slot / (2 sin(pi / n)).
"""
import math
from typing import NamedTuple

SLOT_GAP = 1.25             # neighbouring slot centres are at least this many slot widths apart (app.js copies it)
MAX_SECTOR = 90.0           # widest angle (degrees) a single slot answers to (app.js copies it)
WHEN_FULL = ("grow", "rings", "more")
_EPS = 1e-6                 # fit_count leaves this much room for rounding (a ring that needs 145.0000001 fits 145)


class Seat(NamedTuple):
    """One slot's place: ring (index into Plan.rings), k (its number inside that ring), radius (distance from the
    centre) and angle (degrees clockwise from 12 o'clock)."""
    ring: int
    k: int
    radius: float
    angle: float


class RingPlan(NamedTuple):
    """One ring of slots: its radius, the index of its first slot in the menu, how many it holds, the angle of its
    first slot (offset), the angle between slots (step) and the inner edge of the band it is picked in (rmin;
    0.0 means "from the dead zone")."""
    radius: float
    first: int
    n: int
    offset: float
    step: float
    rmin: float


class Plan(NamedTuple):
    """The layout of a menu's slots. seats has one Seat per slot in menu order; rings lists the rings (one, today);
    radius is the ring radius asked for; needed the radius the slots need; capacity how many slots fit at the radius
    asked for; grown whether the ring had to grow past it; mode what was done about a full ring (always "grow"
    for now: "rings" and "more" are planned the same way until they are built); more_slot the index of a More slot
    or None."""
    seats: list
    rings: list
    radius: float
    needed: float
    capacity: int
    grown: bool
    mode: str
    more_slot: object


def needed_radius(sizes):
    """The smallest ring radius that gives every pair of neighbouring slots (the last and the first included) SLOT_GAP
    times the mean of their widths between their centres. sizes: slot widths in pixels. Fewer than two slots need
    nothing (0.0)."""
    n = len(sizes)
    if n < 2:
        return 0.0
    widest = max((sizes[i] + sizes[(i + 1) % n]) / 2 for i in range(n))
    return SLOT_GAP * widest / (2 * math.sin(math.pi / n))


def fit_count(sizes, radius):
    """How many of the first slots in sizes fit on a ring of this radius without it growing: the largest k whose
    needed_radius is no more than radius (a millionth over counts as fitting). With equal sizes that is
    floor(pi / asin(SLOT_GAP * slot / (2 radius))), and at least 1 for a menu with any slot at all."""
    limit = radius * (1 + _EPS)
    for k in range(len(sizes), 0, -1):
        if needed_radius(sizes[:k]) <= limit:
            return k
    return 0


def plan(sizes, radius, when_full="grow"):
    """The Plan for slots of these widths on a ring of at least this radius. when_full: "grow", "rings" or "more".
    Only "grow" is built: the ring grows to hold every slot. The others are accepted and planned as "grow" until the
    rings phase turns them on (a plan then has more than one entry in rings, and each Seat names its ring)."""
    n = len(sizes)
    needed = needed_radius(sizes)
    r = max(radius, needed) if n >= 2 else radius
    step = 360.0 / n if n else 0.0
    seats = [Seat(0, i, r, step * i) for i in range(n)]
    rings = [RingPlan(r, 0, n, 0.0, step, 0.0)] if n else []
    return Plan(seats, rings, radius, needed, fit_count(sizes, radius), needed > radius, "grow", None)
