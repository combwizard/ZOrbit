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


def test_plan_takes_when_full_and_treats_every_mode_as_grow_for_now():
    base = layout.plan([72.0] * 12, 145, "grow")
    for mode in layout.WHEN_FULL:
        assert layout.plan([72.0] * 12, 145, mode) == base
    assert layout.plan([], 145).seats == []
