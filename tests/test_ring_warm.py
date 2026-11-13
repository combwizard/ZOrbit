"""radiald.App draws the ring's pictures ahead of the first open (the ring warm-up), on its own thread, in steps.

No window, hook or timer is made: SetTimer and KillTimer are recorded, the monitor is a made-up 1920x1080 one, and an
open is played the way open_menu and Ring.show set a ring up, without the window.
"""
import ctypes.wintypes as w
import json
import threading
import time

import pytest
from PIL import Image

import radiald
import recent
import ring
import usage
import win32 as W

REAL_PREFETCH = radiald.App._prefetch        # the env fixture puts a no-op in its place
WORK = w.RECT(0, 0, 1920, 1040)
RECENT = ["D:/Projects/One.zpr", "D:/Models/Two.ztl", "D:/Projects/Three.zpr"]
MENUS = {
    "a": {"title": "A", "hotkey": "Q", "items": [{"brush": "Move"}, {"brush": "Clay"}, {"auto": "brush"},
                                                  {"menu": "f", "label": "Fan"}, {"menu": "s", "label": "Sub"},
                                                  {"recent": "any", "label": "Recent"}]},
    "b": {"title": "B", "hotkey": "W", "items": [{"brush": "Pinch"}, {"brush": "Flatten"}, {"menu": "f", "label": "Fan"},
                                                  {"menu": "t", "label": "Autos"}]},
    "f": {"title": "F", "fan": True, "items": [{"brush": "Layer"}, {"brush": "Standard"},
                                               {"menu": "g", "label": "Deeper"}]},
    "g": {"title": "G", "fan": True, "items": [{"brush": "Slash3"}, {"brush": "Inflat"}]},
    "s": {"title": "S", "items": [{"brush": "ClayTubes"}, {"brush": "SnakeHook"}, {"brush": "Move Topological"}]},
    "t": {"title": "T", "items": [{"auto": "brush"}, {"auto": "brush"}, {"auto": "brush"}, {"brush": "Dam"}]},
}


class Counts:
    """How many pictures the ring code draws, by kind."""

    def __init__(self, monkeypatch):
        self.n = {"slot": 0, "menu": 0, "static": 0, "lines": 0}
        for kind, owner, name in (("slot", ring.Ring, "_slot_sprites"), ("static", ring.Ring, "_draw_static"),
                                  ("lines", ring.Ring, "_draw_fan_lines"), ("menu", ring, "_sprite_put")):
            real = getattr(owner, name)

            def counted(*a, real=real, kind=kind, **k):
                self.n[kind] += 1
                return real(*a, **k)
            monkeypatch.setattr(owner, name, counted)

    def take(self):
        out, self.n = self.n, dict.fromkeys(self.n, 0)
        return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    for c in (ring._sprite_cache, ring._slot_cache, ring._static_layers, ring._fan_line_cache):
        c.clear()
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    icons = {}

    def icon_for(self, item):                 # one picture per brush, the same object each time, as App.icon_for keeps
        name = item.data.get("brush") or item.icon
        if not name:
            return None
        if name not in icons:
            icons[name] = Image.new("RGBA", (32, 32), (len(name) * 20 % 256, 90, 160, 255))
        return icons[name]
    monkeypatch.setattr(radiald.App, "icon_for", icon_for)
    timers, lines = {}, []
    monkeypatch.setattr(W, "SetTimer", lambda hwnd, tid, ms, cb: timers.__setitem__(tid, ms))
    monkeypatch.setattr(W, "KillTimer", lambda hwnd, tid: timers.pop(tid, None))
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 0)
    monkeypatch.setattr(W, "monitor_for_point", lambda x, y: (WORK, 1.0))
    monkeypatch.setattr(W, "monitor_for_window", lambda hwnd: (WORK, 1.5))
    monkeypatch.setattr(radiald, "log", lines.append)
    listed = list(RECENT)
    monkeypatch.setattr(recent, "entries", lambda kind, limit, install=None, log=None: listed[:limit])
    monkeypatch.setattr(recent, "prefetch", lambda *a, **k: None)     # never the real list
    monkeypatch.setattr(recent, "known", lambda kind, limit, install=None: True)
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": MENUS}), encoding="utf-8")
    app = radiald.App(str(radial))
    app.usage = usage.Usage(str(tmp_path / "usage.json"))
    app.ctrl = 1
    app.load_config(force=True, balloon=False)
    return app, timers, lines, Counts(monkeypatch), listed, radial


def run_warm(app, timers, limit=5000):
    ticks = 0
    while radiald.TIMER_RING_WARM in timers and ticks < limit:
        app._warm_tick()
        ticks += 1
    return ticks


def opened(app, menu, held=True, nested=False):
    """A ring set up as open_menu and show() set it up (centred on the monitor), without the window."""
    r = ring.Ring(app.expander.menu(menu), app.cfg.ring, app.icon_for, lambda *a: None, lambda m: None, held=held,
                  nested=nested, submenus=app.expander.resolve)
    work, scale = W.monitor_for_point(960, 520)
    r._place(960, 520, work, scale)
    r._prepare()
    r._static()
    return r


def open_fans(r):
    todo = [(i,) for i in range(r.n)]
    while todo:
        path = todo.pop(0)
        if r._fannable(path):
            fan = r._fan(path)
            todo += [path + (k,) for k in range(len(fan.items))]


def tap(r):
    r._stay_open("tap")
    r.mode = "click"
    r._static_cache = None
    r._static()


def open_everything(app):
    """Every open warm-up plans for: the hotkey menus, their fans, the rings their slots open, and a tap on each."""
    rings = []
    for m in app.slots:
        r = opened(app, m)
        open_fans(r)
        rings.append(r)
    for mid in ("s", "t"):
        rings.append(opened(app, app.expander.resolve(mid), nested=True))
    for r in rings:
        tap(r)


def test_after_the_warm_up_the_first_opens_draw_nothing(env):
    app, timers, lines, counts, *_ = env
    assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS
    run_warm(app, timers)
    drawn = counts.take()
    assert drawn["slot"] >= 15 and drawn["static"] >= 4 and drawn["lines"] >= 3 and drawn["menu"] >= 3
    open_everything(app)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_without_the_warm_up_the_same_opens_draw_everything(env):
    app, timers, lines, counts, *_ = env
    open_everything(app)
    drawn = counts.take()
    assert drawn["slot"] >= 15 and drawn["static"] >= 4 and drawn["lines"] >= 3


def test_one_picture_per_step_and_one_log_line_at_the_end(env):
    app, timers, lines, counts, *_ = env
    lines.clear()
    app._warm_tick()                                       # the plan
    while radiald.TIMER_RING_WARM in timers:
        before = sum(counts.n.values())
        app._warm_tick()
        assert sum(counts.n.values()) - before <= 1
    assert len(lines) == 1 and lines[0].startswith("ring warm-up (menus loaded): ") and "pictures drawn" in lines[0]


def test_a_step_does_nothing_while_a_ring_is_open_and_carries_on_after(env):
    app, timers, lines, counts, *_ = env
    app._warm_tick()
    app._warm_tick()
    counts.take()
    app.ring = object()
    for _ in range(5):
        app._warm_tick()
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}
    assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_HOLD_MS
    app.ring = None
    run_warm(app, timers)
    assert sum(counts.take().values()) > 0                 # it carried on where it was
    open_everything(app)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


@pytest.mark.parametrize("busy", ["held_vk", "_ack", "_browser_pick", "_commands", "_apply_watch", "_prefetch_threads"])
def test_a_step_waits_for_a_hotkey_a_pick_or_the_thumbnails(env, busy):
    app, timers, lines, counts, *_ = env
    app._warm_tick()
    counts.take()
    value = {"held_vk": 0x51, "_commands": [1],
             "_prefetch_threads": [type("T", (), {"is_alive": lambda self: True})()]}
    setattr(app, busy, value.get(busy, object()))
    app._warm_tick()
    assert sum(counts.take().values()) == 0 and timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_HOLD_MS


def test_a_step_waits_for_an_older_thumbnail_thread_when_a_newer_one_is_done(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    reading, release, calls = threading.Event(), threading.Event(), []

    def prefetch(pairs, size):                 # the first load's thread reads until it is let go, the second ends at once
        calls.append(size)
        if len(calls) == 1:
            reading.set()
            release.wait(10)
    monkeypatch.setattr(radiald.assets, "prefetch", prefetch)
    REAL_PREFETCH(app)
    assert reading.wait(5)
    REAL_PREFETCH(app)
    first, second = app._prefetch_threads
    second.join(5)
    assert first.is_alive() and not second.is_alive()
    app._warm_tick()
    counts.take()
    app._warm_tick()
    assert sum(counts.take().values()) == 0 and timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_HOLD_MS
    release.set()
    first.join(5)
    run_warm(app, timers)
    assert sum(counts.take().values()) > 0
    REAL_PREFETCH(app)                         # the threads that have ended are not kept
    assert len(app._prefetch_threads) == 1
    app._prefetch_threads[0].join(5)


def test_a_change_mid_way_drops_the_old_plan_and_the_new_one_completes(env):
    app, timers, lines, counts, listed, radial = env
    for _ in range(4):
        app._warm_tick()
    old = app._warm
    assert old is not None
    menus = json.loads(json.dumps(MENUS))
    menus["a"]["title"] = "A again"
    menus["b"]["items"].append({"brush": "Layer"})
    radial.write_text(json.dumps({"menus": menus}), encoding="utf-8")
    app.load_config(force=True, balloon=False)
    assert app._warm is None and timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS
    run_warm(app, timers)
    assert app._warm is None and radiald.TIMER_RING_WARM not in timers
    counts.take()
    open_everything(app)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_a_burst_of_changes_starts_one_warm_up(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    plans = []
    real = radiald.App._warm_jobs
    monkeypatch.setattr(radiald.App, "_warm_jobs", lambda self, *a: plans.append(1) or real(self, *a))
    for _ in range(6):                                     # Studio saving on every step of a slider drag
        app._warm_soon("menus loaded")
        assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS   # the wait starts again each time
    run_warm(app, timers)
    assert plans == [1]


def test_the_timer_is_gone_when_the_plan_is_done_and_nothing_runs_again(env):
    app, timers, lines, counts, *_ = env
    run_warm(app, timers)
    assert radiald.TIMER_RING_WARM not in timers
    lines.clear()
    counts.take()
    app._warm_soon("menus loaded")                         # everything is there already
    ticks = run_warm(app, timers)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}
    assert lines == [] and radiald.TIMER_RING_WARM not in timers and ticks < 10


def test_with_no_hotkey_menus_there_is_nothing_to_do(env):
    app, timers, lines, counts, *_ = env
    app._set_slots([], None)
    app._warm_soon("menus loaded")
    assert run_warm(app, timers) == 1 and radiald.TIMER_RING_WARM not in timers
    assert sum(counts.take().values()) == 0 and lines[-1].startswith("config loaded")


def test_the_warm_up_stays_inside_every_cache_bound_and_keeps_what_it_drew(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    monkeypatch.setattr(ring, "SLOT_SPRITES", 16)          # room for the two hotkey menus' slots, not their fans
    monkeypatch.setattr(ring, "SPRITE_MENUS", 4)
    run_warm(app, timers)
    limits = app._warm_limits()
    assert len(ring._slot_cache) <= limits["slot"][0] == 12 and len(ring._sprite_cache) <= limits["menu"][0]
    assert len(ring._static_layers) <= limits["static"][0] and ring._static_layers.bytes <= limits["static"][1]
    assert len(ring._fan_line_cache) <= limits["lines"][0] and ring._fan_line_cache.bytes <= limits["lines"][1]
    assert "stopped where the ring caches would hold no more" in lines[-1]
    counts.take()
    opened(app, app.slots[0])                              # what it drew is still there
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_the_warm_up_uses_the_bounds_of_each_cache():
    limits = radiald.App._warm_limits()
    assert limits["slot"] == (int(ring.SLOT_SPRITES * 0.75), float("inf"))
    assert limits["static"] == (36, 24 * 2**20) and limits["lines"] == (24, 3 * 2**20) and limits["menu"] == (6, float("inf"))


def test_a_pick_that_fills_an_auto_slot_draws_only_that_slot(env):
    app, timers, lines, counts, *_ = env
    run_warm(app, timers)
    counts.take()
    app._record_pick(radiald.C.Item(label="Smooth", kind="brush", data={"brush": "Smooth"}))
    assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_PICK_MS
    run_warm(app, timers)
    assert counts.take() == {"slot": 1, "menu": 2, "static": 0, "lines": 0}     # the new slot, a's and t's sprites
    open_everything(app)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_a_pick_that_changes_no_auto_slot_does_not_warm_again(env):
    app, timers, lines, counts, *_ = env
    run_warm(app, timers)
    app._record_pick(radiald.C.Item(label="Smooth", kind="brush", data={"brush": "Smooth"}))
    run_warm(app, timers)
    app._record_pick(radiald.C.Item(label="Smooth", kind="brush", data={"brush": "Smooth"}))  # Smooth is in the slot already
    assert radiald.TIMER_RING_WARM not in timers


def test_a_new_recent_file_warms_nothing_and_the_open_draws_only_what_is_new(env):
    app, timers, lines, counts, listed, _ = env
    run_warm(app, timers)
    counts.take()
    listed.insert(0, "D:/Models/Four.ztl")                 # ZBrush opened another file
    assert radiald.TIMER_RING_WARM not in timers
    r = opened(app, app.slots[0])
    open_fans(r)
    drawn = counts.take()
    assert drawn["slot"] == 1 and drawn["lines"] == 1 and drawn["static"] == 0


def test_the_scale_is_zbrushs_monitor_when_it_is_in_front_else_the_primary(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    assert app._warm_target() == (WORK, 1.0)
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 7)
    monkeypatch.setattr(radiald.App, "target_in_front", lambda self, on_hook=False: True)
    assert app._warm_target() == (WORK, 1.5)


def test_zbrush_on_a_monitor_of_another_scale_warms_again_and_focus_elsewhere_does_not(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    run_warm(app, timers)
    assert app._warm_scale == 1.0
    app._check_warm_scale()
    assert radiald.TIMER_RING_WARM not in timers           # ZBrush is not in front: no change
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 7)
    monkeypatch.setattr(radiald.App, "target_in_front", lambda self, on_hook=False: True)
    app._check_warm_scale()
    assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS and app._warm_scale == 1.5
    timers.clear()
    app._check_warm_scale()
    assert timers == {}                                    # the same scale again: nothing


def test_the_warm_up_leaves_a_submenus_auto_slots_where_they_are(env):
    app, timers, lines, counts, *_ = env
    run_warm(app, timers)
    now = time.time()
    # Saved in an order that is not the ranking (Beta scores higher, Alpha holds the first slot), with one slot empty.
    raw = {"brushes": {"alpha": {"name": "Alpha", "score": 1.0, "t": now - 3600},
                       "beta": {"name": "Beta", "score": 3.0, "t": now}},
           "menus": {"t": {"slots": ["Alpha", "Beta", None], "pending": []}}}
    with open(app.usage.path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    app.usage.load()
    before = json.loads(json.dumps(app.usage.menus["t"]))
    shown = [it.label for it in app.expander.resolve("t").items]
    assert shown == ["Alpha", "Beta", "Auto", "Dam"]
    app._warm_soon("menus loaded")
    run_warm(app, timers)
    assert app.usage.menus["t"] == before
    assert [it.label for it in app.expander.resolve("t").items] == shown

def warm_lines(lines):
    return [ln for ln in lines if ln.startswith("ring warm-up")]


def test_a_job_that_raises_is_said_once_and_the_plan_goes(env, monkeypatch):
    app, timers, lines, counts, *_ = env

    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(ring.Ring, "warm_jobs", lambda self, part: iter([("slot", ("k",), 0, boom)]))
    lines.clear()
    assert run_warm(app, timers) == 1
    said = warm_lines(lines)
    assert len(said) == 1 and "error" in said[0] and "boom" in said[0]
    assert radiald.TIMER_RING_WARM not in timers and app._warm is None


def test_a_plan_that_raises_is_said_once_and_the_timer_goes(env, monkeypatch):
    app, timers, lines, counts, *_ = env

    def boom(self):
        raise OSError("no monitor")
    monkeypatch.setattr(radiald.App, "_warm_target", boom)
    lines.clear()
    assert run_warm(app, timers) == 1
    said = warm_lines(lines)
    assert len(said) == 1 and "no monitor" in said[0]
    assert radiald.TIMER_RING_WARM not in timers and app._warm is None and sum(counts.take().values()) == 0


def test_a_menus_file_that_cannot_be_read_at_start_leaves_nothing_to_warm(env, tmp_path):
    app, timers, lines, counts, *_ = env
    timers.clear()
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    other = radiald.App(str(bad))
    other.ctrl = 1
    other.load_config(force=True, balloon=False)            # nothing loaded yet: the app runs with no menus
    assert other.slots == [] and timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS
    assert run_warm(other, timers) == 1 and radiald.TIMER_RING_WARM not in timers
    assert sum(counts.take().values()) == 0 and warm_lines(lines) == []


def test_before_the_control_window_there_is_no_timer_and_start_makes_one(env):
    app, timers, lines, counts, *_ = env
    timers.clear()
    app.ctrl = None
    gen = app._warm_gen
    app.load_config(force=True, balloon=False)             # _serve loads the menus before the window exists
    assert timers == {} and app._warm_gen == gen + 1
    app.ctrl = 1
    app._warm_soon("start")                                # ... and asks again once it does
    assert timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_WAIT_MS
    run_warm(app, timers)
    counts.take()
    open_everything(app)
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_pictures_already_there_are_found_not_drawn_and_kept(env):
    app, timers, lines, counts, *_ = env
    r = opened(app, app.slots[0])                          # the user opened ring a before warm-up ran
    open_fans(r)
    by_hand = counts.take()
    lines.clear()
    run_warm(app, timers)
    said = warm_lines(lines)[0]
    found = int(said.split(" already there")[0].rsplit(", ", 1)[1])
    assert found >= by_hand["slot"] + by_hand["static"] + by_hand["lines"]
    counts.take()
    open_everything(app)                                   # what was there before is still there
    assert counts.take() == {"slot": 0, "menu": 0, "static": 0, "lines": 0}


def test_zbrushs_monitor_is_kept_while_another_program_is_in_front(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    timers.clear()
    front = {"zbrush": True}
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 7)
    monkeypatch.setattr(radiald.App, "target_in_front", lambda self, on_hook=False: front["zbrush"])
    app._check_warm_scale()                                # the config tick sees ZBrush in front, on a 150% monitor
    front["zbrush"] = False                                # Studio comes to the front and saves
    app._warm_soon("menus loaded")
    run_warm(app, timers)
    assert app._warm_scale == 1.5 and "at scale 1.50" in warm_lines(lines)[-1]
    front["zbrush"] = True                                 # back in ZBrush: nothing to plan again
    app._check_warm_scale()
    assert radiald.TIMER_RING_WARM not in timers


def test_before_zbrush_is_seen_the_primary_monitor_is_used(env):
    app, timers, lines, counts, *_ = env
    assert app._zb_monitor is None and app._warm_target() == (WORK, 1.0)


def test_a_plan_with_recent_slots_waits_for_the_first_answer_until_its_deadline(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    answered = {"yet": False}
    monkeypatch.setattr(recent, "known", lambda kind, limit, install=None: answered["yet"])
    app._warm_tick()                                       # planned, and waiting
    for _ in range(3):
        app._warm_tick()
    assert sum(counts.take().values()) == 0 and timers[radiald.TIMER_RING_WARM] == radiald.RING_WARM_HOLD_MS
    answered["yet"] = True                                 # the worker answered
    app._warm_tick()
    assert sum(counts.take().values()) == 1
    app._warm_soon("menus loaded")
    answered["yet"] = False
    app._warm_tick()
    app._warm["recent_until"] = 0.0                        # a read that never answers holds it only so long
    run_warm(app, timers)
    assert radiald.TIMER_RING_WARM not in timers and app._warm is None


def test_a_plan_without_recent_slots_does_not_wait_for_them(env, monkeypatch):
    app, timers, lines, counts, *_ = env
    monkeypatch.setattr(recent, "known", lambda kind, limit, install=None: False)
    for m in app.cfg.menus.values():
        m.items = [it for it in m.items if it.kind != "recent"]
    app._warm_soon("menus loaded")
    app._warm_tick()
    assert app._warm["recent"] == [] and sum(counts.take().values()) == 1