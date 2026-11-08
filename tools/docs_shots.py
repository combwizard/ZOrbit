"""Takes the Studio and browser screenshots in docs/images from the mock UI (studio_ui/index.html?mock), so they can be
retaken whenever the UI changes. Drives a headless Microsoft Edge over the DevTools protocol.

The pictures should show a fresh install, not the developer's own setup, so the script records its own mock data
(build/docs-shots/mock_data.js, git-ignored) with tools/make_mock.py and an empty %APPDATA% and %LOCALAPPDATA%: the
starter menus, no logs, and only ZBrush's own brushes, alphas, materials and textures (it copies just the
installpath.txt files from %APPDATA%\\Maxon so ZBrush is found). Your own dev/mock_data.js is not touched. Still look
the pictures over before committing.

Run: python tools/docs_shots.py                         (every shot; records the mock data the first time)
     python tools/docs_shots.py setup browser           (only those)
     python tools/docs_shots.py --record ...            (record the mock data again, after a UI or API change)
     python tools/docs_shots.py --out DIR ...           (somewhere else than docs/images, to look first)
"""
import asyncio
import base64
import functools
import glob
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import websockets
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "zorbit", "studio_ui")
OUT = os.path.join(ROOT, "docs", "images")
MOCK = os.path.join(ROOT, "build", "docs-shots", "mock_data.js")
EDGE = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
]
# A fresh profile in plain Edge signs in with the Windows account by itself, then syncs logins, bookmarks and extensions
# into the temp folder (over 200 MB in 20 s, on every shot). --guest and --inprivate do not stop that; these do.
EDGE_FLAGS = ["--headless=new", "--no-first-run", "--hide-scrollbars", "--force-color-profile=srgb",
              "--disable-features=msImplicitSignin", "--disable-sync", "--disable-extensions",
              "--disable-background-networking", "--disable-component-update"]
PARALLEL = 6                                            # shots taken at the same time, each in its own Edge

# Steps can use these: click(text) clicks the innermost visible element whose text starts with it (the click bubbles
# to whatever handles it), card(name) is a Settings card by its title, alone at the top of the screen, and
# lookGroup(name) is the same for a group on the Look screen (Slots, Hub, Labels, Colours, Tag colours, Opening); it opens the group if it starts folded.
HELPERS = """
window.typeTarget = t => { const i = document.querySelector('[data-focus=target]'); i.focus(); i.value = t;
  i.dispatchEvent(new Event('input', {bubbles: true})); return true; };
window.click = t => new Promise((ok, fail) => { const t0 = Date.now(); (function poll() {
  const hits = [...document.querySelectorAll('body *')].filter(e => e.offsetParent && e.textContent.trim().startsWith(t));
  const b = hits[hits.length - 1];
  if (b) { b.click(); return ok(true); }
  if (Date.now() - t0 > 5000) return fail(new Error('nothing says ' + t));
  setTimeout(poll, 100); })(); });
window.card = n => { const c = document.getElementById('set-' + n.toLowerCase().replace(/[^a-z0-9]+/g, '-')); if (!c) throw new Error('no card ' + n);
  // The other cards are hidden instead of scrolling to this one: a card scrolled far down came out of the capture
  // with the wrong colours.
  for (const o of c.parentElement.children) if (o !== c) o.hidden = true;
  c.closest('.settings-scroll').scrollTop = 0; return c; };
window.lookGroup = n => { const c = document.getElementById('look-g-' + ({'Tag colours': 'tags'}[n] || n.toLowerCase())); if (!c) throw new Error('no Look group ' + n);
  const f = c.querySelector('.fold-head[aria-expanded="false"]'); if (f) f.click();     // a group the Look screen starts folded
  for (const o of c.parentElement.children) if (o !== c) o.hidden = true;
  c.closest('.look-scroll').scrollTop = 0; return c; };
// A mouse drag of card number `from` that stops, not released, at the gap before card number `to`.
window.dragCard = (from, to) => { const cards = [...document.querySelectorAll('.bgrid .bcard[data-name]')], a = cards[from].getBoundingClientRect(),
    b = cards[to].getBoundingClientRect(), ev = (type, x, y) => (type === 'pointerdown' ? cards[from] : window).dispatchEvent(new PointerEvent(type,
      {bubbles: true, cancelable: true, button: 0, buttons: 1, clientX: x, clientY: y, pointerId: 1, isPrimary: true}));
  ev('pointerdown', a.left + a.width / 2, a.top + a.height / 2);
  ev('pointermove', a.left + a.width / 2 + 12, a.top + a.height / 2 + 12);
  ev('pointermove', b.left + 6, b.top + b.height / 2); return true; };
"""

# name -> page (default index.html), URL switches (see dev/mock.js; Studio itself reads screen, menu, item, tab,
# kind, q), window size, JS steps to run once the page is ready (each may return a promise), and clip: a JS
# expression for the element to crop to. Crops are taken at 2x, whole windows at 1x.
# studio-strays waits for the dialog Studio opens on its own after start (?strays) and crops to it.
# studio-profiles crops the top-left of the window (the brand, the profile button and its open picker) with an object
# that answers getBoundingClientRect like an element, since the picker is not inside the top bar.
SHOTS = {
    # Whole windows
    "studio": dict(q="screen=menus"),
    "studio-item": dict(q="screen=menus&menu=tools&item=8"),
    "studio-look": dict(q="screen=look"),
    # look-presets: the Look screen with the gallery of looks under the preview scrolled into view.
    "look-presets": dict(q="screen=look", steps=["document.querySelector('.lk-gallery').scrollIntoView({block: 'start'})"]),
    # look-menu: the menu level, after the Tiles look is used for the menu on show (badges say Look: Tiles and This menu).
    "look-menu": dict(q="screen=look", steps=["document.querySelector('[data-level=\"menu\"]').click()", "document.querySelector('[data-fk=\"look:card/tiles/use\"]').click()"]),
    # look-slot: the slot level for the first slot of the menu, with the hover glow switched on so the picture shows it on that slot.
    "look-slot": dict(q="screen=look", steps=["document.querySelector('[data-level=\"slot\"]').click()", "document.querySelector('.look-glowsw input').click()"]),
    # look-full: a menu with more items than its ring holds at its radius, so the note above the items says what the ring does.
    "look-full": dict(q="screen=menus&menu=tools"),
    "studio-library": dict(q="screen=library"),
    # fav-order: Favourites in the Library part way through a drag: the card dimmed, the marker in the gap, the chip at the pointer.
    "fav-order": dict(q="screen=library&favs=16", size=(1180, 760), steps=["click('Favourites')", "dragCard(1, 6)"]),
    # pack-names: the browser on an added folder, whose first files have names another pack took first, so they say which pack they are from.
    "pack-names": dict(page="popout.html", q="kind=alpha&packs", size=(980, 560), steps=["click('Rock Pack')"]),
    "studio-settings": dict(q="screen=settings"),
    "studio-settings-simple": dict(q="screen=settings&mode=simple"),
    "studio-light": dict(q="screen=settings&theme=light"),
    # studio-tour opens the guided tour, waits for its card and clicks Next once: stop 2 of 6, The ring, lit.
    "studio-tour": dict(q="screen=menus", steps=[
        "startTour()",
        "new Promise(r => { const t0 = Date.now(); (function w() {"
        " if (document.querySelector('.tour.in') || Date.now() - t0 > 5000) r(); else setTimeout(w, 100); })(); })",
        "document.querySelector('.tour-card .btn.primary').click()",
    ]),
    # setup: all three steps done; the first stays open because a ZBrush 2022 still needs the plugin, so the picture shows both an open step and folded ones.
    "setup": dict(q="screen=setup&zb=both&ringtried=done"),
    # setup-done: what Setup looks like on a later visit, with every step done and folded to one line.
    "setup-done": dict(q="screen=setup&zb=2026&ringtried=done"),
    "setup-restart": dict(q="screen=setup&zb=2026&zbstale"),
    "browser": dict(page="popout.html", q="kind=brush", size=(980, 680)),
    "browser-light": dict(page="popout.html", q="kind=brush&theme=light", size=(980, 680)),
    "library-tag": dict(q="screen=library", steps=["click('Blocking')"]),
    # strip: the favourites strip, vertical, with 12 favourites (6 fit on this small screen, so a +6 button holds the rest), the third one picked just now (the accent rim).
    # strip-horizontal: lying down, with +4 pressed so the rest of the favourites sit in a second row.
    # strip-menu: the strip's menu, open in place of the thumbnails. A strip is cropped to its own box; the window around it is not drawn.
    "strip": dict(page="popout.html", q="strip&favs=12", size=(400, 800), clip="document.querySelector('.strip')",
                  steps=["document.querySelectorAll('.strip-cell')[2].click()"]),
    "strip-horizontal": dict(page="popout.html", q="strip=horizontal&favs=14", size=(1000, 400), clip="document.querySelector('.strip')",
                             steps=["click('+4')"]),
    "strip-menu": dict(page="popout.html", q="strip&favs=12", size=(400, 800), clip="document.querySelector('.strip')",
                       steps=["document.querySelector('.strip-menu').click()"]),
    # Details
    "settings-theme": dict(q="screen=settings&theme=zbrush", clip="card('Theme')"),
    # menu-look: the Look section of the Menu tab (under More, which the first step opens), with the Tiles look chosen for the menu.
    "menu-look": dict(q="screen=menus&tab=menu", steps=["document.querySelector('#menu-more .fold-head').click()", "(() => { const s = document.querySelector('select[aria-label=\"Look for this menu\"]'); s.value = 'tiles'; s.dispatchEvent(new Event('change')); })()",
                       "document.querySelector('select[aria-label=\"Look for this menu\"]').scrollIntoView({block: 'center'})"],
                      clip="({getBoundingClientRect: () => { const f = document.querySelector('select[aria-label=\"Look for this menu\"]').closest('.field'); const t = f.previousElementSibling;"
                           " const a = t.getBoundingClientRect(), b = f.getBoundingClientRect(); return {left: a.left - 10, top: a.top - 10, right: b.right + 10, bottom: b.bottom + 10}; }})"),
    "look-colours": dict(q="screen=look", clip="lookGroup('Colours')"),
    # look-opening: the Opening group of the Look screen (the open animation tiles and the Play button).
    "look-opening": dict(q="screen=look", clip="lookGroup('Opening')"),
    "settings-behaviour": dict(q="screen=settings", clip="card('Behaviour')"),
    "settings-bridge": dict(q="screen=settings", clip="card('ZBrush bridge')"),
    "settings-older-zbrush": dict(q="screen=settings&zb=both", clip="card('Older ZBrush')"),
    "settings-import-export": dict(q="screen=settings", clip="card('Import and export')"),
    # settings-library-folders: the Library folders card with a found brush folder and an alpha folder that cannot be found (?libfolders=two),
    # taken once the lists have been read.
    "settings-library-folders": dict(q="screen=settings&libfolders=two", steps=["new Promise(r => { const t0 = Date.now(); (function w() {"
                                       " if (document.querySelector('.lf-kinds .zrow') || Date.now() - t0 > 5000) r(); else setTimeout(w, 100); })(); })"],
                                     clip="card('Library folders')"),
    "studio-strays": dict(q="strays", steps=["new Promise(r => { const t0 = Date.now(); (function w() {"
                                           " if (document.querySelector('.modal') || Date.now() - t0 > 5000) r(); else setTimeout(w, 100); })(); })"],
                          clip="document.querySelector('.modal')"),
    # studio-update: the update dialog, opened from the version chip (?update: a newer release Studio can install).
    "studio-update": dict(q="screen=menus&update", steps=[
        "new Promise(r => { const t0 = Date.now(); (function w() {"
        " if (document.querySelector('#versionChip.has-update') || Date.now() - t0 > 5000) r(); else setTimeout(w, 100); })(); })",
        "document.getElementById('versionChip').click()",
    ], clip="document.querySelector('.modal')"),
    # macro-suggest: what a Press slot suggests. It types as far as Macro:Misc:Toggle because the suggestions also list the
    # macros in the developer's own folder, and only the ones that come with ZBrush may be in a picture.
    "macro-suggest": dict(q="screen=menus&menu=tools&item=0", steps=["typeTarget('Macro:Misc:Toggle')",
        # The list is see-through, and the panel behind it would show in the crop.
        "(() => { const t = document.querySelector('[data-focus=target]');"
        " document.querySelectorAll('.insp *').forEach(e => { if (!e.contains(t)) e.style.visibility = 'hidden'; }); return true; })()"],
                          clip="({getBoundingClientRect: () => { const a = document.querySelector('[data-focus=target]').getBoundingClientRect(),"
                               " b = document.querySelector('.combo-list').getBoundingClientRect();"
                               " return {left: Math.min(a.left, b.left) - 12, top: Math.min(a.top, b.top) - 8,"
                               " right: Math.max(a.right, b.right) + 12, bottom: Math.max(a.bottom, b.bottom) + 2}; }})"),
    # status-report: the log card on Status with Copy report and Report a bug (?calmlog: no made-up failures in the log).
    "status-report": dict(q="screen=status&calmlog", clip="document.querySelector('.logbox').closest('.card')"),
    "studio-profiles": dict(q="screen=menus&profiles=3", steps=["document.getElementById('profileBtn').click()"],
                            clip="({getBoundingClientRect: () => { const p = document.querySelector('.popover').getBoundingClientRect();"
                                 " return {left: 0, top: 0, right: Math.max(p.right + 24, 520), bottom: p.bottom + 12}; }})"),
}

WAIT_READY = """new Promise((ok, fail) => {
  const t0 = Date.now();
  (function poll() {
    const ready = location.pathname.endsWith('popout.html') ? document.querySelector('img') : (document.querySelector('#saveBtn') && !document.querySelector('#saveBtn').disabled);
    if (ready) return ok(true);
    if (Date.now() - t0 > 15000) return fail(new Error('page never became ready'));
    setTimeout(poll, 100);
  })();
})"""


def record():
    """Records MOCK from a fresh install: make_mock.py with an empty %APPDATA% and %LOCALAPPDATA%."""
    tmp = tempfile.mkdtemp(prefix="zorbit-fresh-")
    roam, local = os.path.join(tmp, "Roaming"), os.path.join(tmp, "Local")
    for f in glob.glob(os.path.expandvars(r"%APPDATA%\Maxon\*\installpath.txt")):
        dest = os.path.join(roam, "Maxon", os.path.basename(os.path.dirname(f)))
        os.makedirs(dest, exist_ok=True)
        shutil.copy(f, dest)
    os.makedirs(local)
    os.makedirs(os.path.dirname(MOCK), exist_ok=True)
    print("recording mock data from a fresh install (thumbnails take a while) ...")
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_mock.py"), MOCK], check=True,
                       env=dict(os.environ, APPDATA=roam, LOCALAPPDATA=local))
        # The temporary folders stand in for the real ones; show them as a made-up user's (the title bar shows the
        # menus file, laid out right to left, so a %APPDATA% there would come out garbled).
        text = open(MOCK, encoding="utf-8").read()
        for path, real in ((roam, r"C:\Users\you\AppData\Roaming"), (local, r"C:\Users\you\AppData\Local")):
            for form in (json.dumps(path)[1:-1], path.replace("\\", "/")):
                text = text.replace(form, json.dumps(real)[1:-1])
        open(MOCK, "w", encoding="utf-8").write(text)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves studio_ui, with dev/mock_data.js swapped for the fresh-install recording."""

    def translate_path(self, path):
        if path.split("?")[0] == "/dev/mock_data.js":
            return MOCK
        return super().translate_path(path)

    def log_message(self, *a):
        pass


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 64                             # six Edges asking at once overflow the default backlog of 5

    def handle_error(self, request, client_address):
        pass                                            # Edge dropping a connection on exit is not news


def serve():
    httpd = Server(("127.0.0.1", 0), functools.partial(Handler, directory=UI))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def stop_edge(proc, profile):
    """Ends Edge with all its child processes and removes its profile. proc.kill() alone ends only the first process: the
    others run on and hold the profile's files, so it could not be removed."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    proc.wait()
    for _ in range(50):                                 # the last of its files are let go a moment later
        shutil.rmtree(profile, ignore_errors=True)
        if not os.path.exists(profile):
            return
        time.sleep(0.1)
    print(f"could not remove {profile}", file=sys.stderr)


def start_edge(profile):
    exe = next((p for p in EDGE if os.path.exists(p)), None)
    if not exe:
        sys.exit("Microsoft Edge not found")
    proc = subprocess.Popen([exe, *EDGE_FLAGS, "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_file = os.path.join(profile, "DevToolsActivePort")
    for _ in range(100):
        try:
            port = open(port_file).read().split()
        except OSError:
            port = None                                 # not there yet, or Edge has it open to write
        if port:
            return proc, int(port[0])
        time.sleep(0.1)
    stop_edge(proc, profile)
    sys.exit("Edge did not open its DevTools port")


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        my = self.n
        await self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']['message']}")
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"]["text"])
        return r["result"].get("value")


async def shoot(page, base, name, spec):
    w, h = spec.get("size", (1360, 860))
    clip = spec.get("clip")
    scale = spec.get("scale", 2 if clip else 1)
    await page.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=scale, mobile=False)
    # A fresh origin state for every shot: the mock keeps tags, prefs and usage in localStorage.
    await page.send("Page.navigate", url=base + "/blank.html")
    await page.js("localStorage.clear(), true")
    await page.send("Page.navigate", url=f"{base}/{spec.get('page', 'index.html')}?mock&{spec.get('q', '')}")
    await asyncio.sleep(0.3)
    await page.js(WAIT_READY)
    await page.js(HELPERS + "true")
    await asyncio.sleep(0.8)                            # thumbnails and the ring preview arrive after ready
    for step in spec.get("steps", []):
        await page.js(step)
        await asyncio.sleep(0.5)
    # No version in a picture: the chip at the top would change every picture at every release.
    await page.js("(() => { const c = document.getElementById('versionChip'); if (c) c.remove(); return true; })()")
    box = None
    if clip:
        # The clip expression may change the page (card() hides the other cards), so it runs once, and the capture
        # waits for the page to settle: a capture taken straight after a change drew it with the wrong colours.
        box = await page.js(f"(() => {{ const el = {clip}; if (!el) throw new Error('nothing to crop to');"
                            " window.__clip = el; return true; })()")
        await asyncio.sleep(1.0)
        box = await page.js("(() => { const r = window.__clip.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })()")
    # The whole window, cropped here rather than by Edge.
    data = base64.b64decode((await page.send("Page.captureScreenshot", format="png"))["data"])
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if box:
        im = im.crop(tuple(round(v * scale) for v in box))
    path = os.path.join(OUT, name + ".png")
    im.save(path, optimize=True)
    print(f"{name}.png  {im.size[0]}x{im.size[1]}  {os.path.getsize(path) // 1024} KB")


async def take(sem, base, name):
    """One shot in its own Edge, once a place is free."""
    async with sem:
        profile = tempfile.mkdtemp(prefix="zorbit-shots-")
        proc, port = await asyncio.to_thread(start_edge, profile)       # it polls for the port, so not on the loop
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            target = json.load(urllib.request.urlopen(req))
            async with websockets.connect(target["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
                page = Page(ws)
                await page.send("Page.enable")
                # Still pictures: no open animations or transitions half way.
                await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
                await shoot(page, base, name, SHOTS[name])
        finally:
            await asyncio.to_thread(stop_edge, proc, profile)   # it waits for the files, so not on the loop


async def run(names):
    if not os.path.exists(MOCK):
        record()
    httpd = serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        # A fresh Edge for every shot: after a few shots one Edge started drawing pages without their colours
        # (orange buttons came out grey), although the page's styles were right.
        sem = asyncio.Semaphore(PARALLEL)
        await asyncio.gather(*(take(sem, base, name) for name in names))
    finally:
        httpd.shutdown()


def main():
    global OUT
    args = sys.argv[1:]
    if "--record" in args:
        args.remove("--record")
        record()
    if args[:1] == ["--out"]:
        OUT, args = os.path.abspath(args[1]), args[2:]
        os.makedirs(OUT, exist_ok=True)
    names = args or list(SHOTS)
    unknown = [n for n in names if n not in SHOTS]
    if unknown:
        sys.exit("Unknown shot(s): " + ", ".join(unknown) + ". Known: " + ", ".join(SHOTS))
    asyncio.run(run(names))


if __name__ == "__main__":
    main()
