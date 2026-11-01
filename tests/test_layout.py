"""layout.py: how much room a ring needs, how many slots fit, and the plan of seats. Pure maths, no Pillow."""
import math

import pytest

import layout


def old_needed(slot, n):
    """What ring.py computed before slots had sizes of their own."""
    return layout.SLOT_GAP * slot / (2 * math.sin(math.pi / n))


@pytest.mark.parametrize("slot", [72.0, 40.0, 108.0, 72 * 1.5, 33.3])
@pytest.mark.parametrize("n", [2, 3, 4, 7, 12, 24, 60])
def test_equal_sizes_need_exactly_the_old_radius(slot, n):
    assert layout.needed_radius([slot] * n) == old_needed(slot, n)


def test_fewer_than_two_slots_need_nothing():
    assert layout.needed_radius([]) == 0.0
    assert layout.needed_radius([72.0]) == 0.0


def test_mixed_sizes_use_the_neighbouring_pair_that_needs_the_most():
    sizes = [72.0, 72.0, 90.0, 72.0, 72.0, 72.0]           # the 90 slot and its two neighbours
    assert layout.needed_radius(sizes) == layout.SLOT_GAP * ((72 + 90) / 2) / (2 * math.sin(math.pi / 6))
    # two big slots side by side need more than the same two apart
    near = [90.0, 90.0, 72.0, 72.0, 72.0, 72.0]
    far = [90.0, 72.0, 72.0, 90.0, 72.0, 72.0]
    assert layout.needed_radius(near) > layout.needed_radius(sizes) > old_needed(72.0, 6)
    assert layout.needed_radius(far) == layout.needed_radius(sizes)


def test_the_last_and_first_slot_are_neighbours_too():
    assert layout.needed_radius([90.0, 72.0, 72.0, 90.0]) == layout.SLOT_GAP * 90 / (2 * math.sin(math.pi / 4))


@pytest.mark.parametrize("slot,radius", [(72, 145), (72, 100), (40, 300), (160, 60), (72, 400)])
def test_fit_count_with_equal_sizes_is_the_old_floor(slot, radius):
    x = layout.SLOT_GAP * slot / (2 * radius)
    old = max(1, math.floor(math.pi / math.asin(x) + 1e-6)) if x < 1 else 1
    assert layout.fit_count([float(slot)] * 100, radius) == old


def test_fit_count_boundaries():
    sizes = [72.0] * 30
    assert layout.fit_count(sizes, 145) == 9                     # 10 would need 145.6
    need9, need10 = layout.needed_radius(sizes[:9]), layout.needed_radius(sizes[:10])
    assert need9 < 145 < need10
    assert layout.fit_count(sizes, need10) == 10                 # exactly enough
    assert layout.fit_count(sizes, need10 * (1 - 1e-7)) == 10     # a rounding-sized shortfall still fits
    assert layout.fit_count(sizes, need10 * (1 - 1e-3)) == 9
    assert layout.fit_count(sizes, 1.0) == 1                     # one slot always fits
    assert layout.fit_count([], 145) == 0
    assert layout.fit_count([72.0] * 3, 1000) == 3               # never more than there are


def test_fit_count_counts_the_first_slots_so_big_ones_early_cost_more_room():
    big_first = [100.0] * 4 + [72.0] * 20
    assert layout.fit_count(big_first, 145) < layout.fit_count([72.0] * 24, 145)
    assert layout.needed_radius(big_first[:layout.fit_count(big_first, 145)]) <= 145 * (1 + 1e-6)


def test_plan_grows_the_ring_and_keeps_the_angles_even():
    p = layout.plan([72.0] * 12, 145)
    assert p.grown and p.capacity == 9 and p.mode == "grow" and p.more_slot is None
    assert p.needed == old_needed(72.0, 12) and p.rings[0].radius == p.needed
    assert [s.angle for s in p.seats] == [30.0 * i for i in range(12)]
    assert all(s.ring == 0 and s.radius == p.needed for s in p.seats)
    assert (p.rings[0].first, p.rings[0].n, p.rings[0].offset, p.rings[0].step) == (0, 12, 0.0, 30.0)


def test_plan_keeps_a_big_enough_radius_and_a_single_slot():
    p = layout.plan([72.0] * 4, 145)
    assert not p.grown and p.rings[0].radius == 145 and p.capacity == 4
    one = layout.plan([72.0], 145)
    assert one.rings[0].radius == 145 and [s.angle for s in one.seats] == [0.0] and not one.grown


def test_plan_treats_more_as_grow_and_an_empty_menu_as_nothing():
    base = layout.plan([72.0] * 12, 145, "grow")
    assert layout.plan([72.0] * 12, 145, "more") == base
    assert layout.plan([72.0] * 12, 145, "rings") != base
    assert layout.plan([], 145).seats == [] and layout.plan([], 145, "rings").rings == []


# --- when_full "rings" ---------------------------------------------------------------------------
@pytest.mark.parametrize("n", [1, 2, 8, 9])
def test_rings_is_a_single_ring_while_everything_fits(n):
    p = layout.plan([72.0] * n, 145, "rings")
    assert p == layout.plan([72.0] * n, 145, "grow") and len(p.rings) == 1 and p.mode == "grow"


def test_rings_splits_a_full_menu_into_an_inner_and_an_outer_ring():
    p = layout.plan([72.0] * 14, 145, "rings")
    assert p.mode == "rings" and p.capacity == 9 and not p.grown and p.more_slot is None
    inner, outer = p.rings
    assert (inner.first, inner.n, inner.radius, inner.offset, inner.rmin) == (0, 9, 145, 0.0, 0.0)
    assert inner.step == 40.0
    assert (outer.first, outer.n, outer.step, outer.offset) == (9, 5, 72.0, 36.0)
    assert outer.radius >= inner.radius + layout.SLOT_GAP * 72 - 1e-9
    assert outer.rmin == (inner.radius + outer.radius) / 2
    assert p.needed == layout.needed_radius([72.0] * 14)
    assert [s.ring for s in p.seats] == [0] * 9 + [1] * 5                  # menu order, inner then outer
    assert [s.angle for s in p.seats[:9]] == [40.0 * i for i in range(9)]
    assert [s.angle for s in p.seats[9:]] == [36.0 + 72.0 * j for j in range(5)]
    assert [(s.ring, s.k) for s in p.seats[8:11]] == [(0, 8), (1, 0), (1, 1)]


def test_the_outer_ring_keeps_its_neighbours_apart_and_grows_for_many_slots():
    sizes = [72.0] * 30
    p = layout.plan(sizes, 145, "rings")
    assert [r.n for r in p.rings] == [9, 21]
    for rp in p.rings:
        sep = 2 * rp.radius * math.sin(math.pi / rp.n)
        assert sep >= layout.SLOT_GAP * 72 - 1e-6
    assert p.rings[1].radius == layout.needed_radius(sizes[9:]) > p.rings[0].radius + layout.SLOT_GAP * 72
    assert len(layout.plan([72.0] * 80, 145, "rings").rings) == 2               # never a third ring


def test_rings_uses_the_sizes_of_each_ring():
    sizes = [72.0] * 9 + [100.0] * 4
    p = layout.plan(sizes, 145, "rings")
    inner, outer = p.rings
    assert inner.n == 9 and outer.n == 4
    assert outer.radius >= inner.radius + layout.SLOT_GAP * (72 + 100) / 2 - 1e-9
    big = layout.plan([100.0] * 14, 145, "rings")                              # fewer fit, a bigger gap between rings
    assert big.rings[0].n == layout.fit_count([100.0] * 14, 145) < 9


def test_rings_grows_when_fewer_than_three_slots_would_fit():
    sizes = [72.0] * 6
    assert layout.fit_count(sizes, 50) < layout.MIN_INNER
    p = layout.plan(sizes, 50, "rings")
    assert p == layout.plan(sizes, 50, "grow") and p.mode == "grow" and len(p.rings) == 1
    three = layout.plan(sizes, 60, "rings")                                     # exactly three fit: it splits 3 + 3
    assert layout.fit_count(sizes, 60) == 3 and three.mode == "rings" and [r.n for r in three.rings] == [3, 3]


def test_rings_boundary_is_where_the_next_slot_no_longer_fits():
    sizes = [72.0] * 20
    need10 = layout.needed_radius(sizes[:10])
    assert [r.n for r in layout.plan(sizes, need10, "rings").rings][0] == 10
    assert [r.n for r in layout.plan(sizes, need10 * (1 - 1e-3), "rings").rings][0] == 9


def test_names_add_room_between_the_rings_and_no_names_keeps_the_tight_gap():
    sizes = [72.0] * 14
    named, bare = layout.plan(sizes, 145, "rings"), layout.plan(sizes, 145, "rings", labels=False)
    assert layout.plan(sizes, 145, "rings", True) == named
    tight = 145 + layout.SLOT_GAP * 72
    assert bare.rings[1].radius == pytest.approx(tight)
    assert named.rings[1].radius == pytest.approx(tight + layout.LABEL_ROOM * 72)
    assert [r.n for r in named.rings] == [r.n for r in bare.rings] == [9, 5]
    assert named.rings[1].rmin == pytest.approx((145 + named.rings[1].radius) / 2)
    one = layout.plan([72.0] * 5, 145, "rings", labels=False)                 # labels only matter with two rings
    assert one == layout.plan([72.0] * 5, 145, "rings", labels=True)
    many = layout.plan([72.0] * 30, 145, "rings")                              # a crowded outer ring is set by its own need
    assert many.rings[1].radius == layout.needed_radius([72.0] * 21)
