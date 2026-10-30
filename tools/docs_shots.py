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

# Steps can use these: click(text) clicks the innermost visible element whose text starts with it (the click bubbles
# to whatever handles it), card(name) is a Settings card by its title, alone at the top of the screen.
HELPERS = """
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
"""

# name -> page (default index.html), URL switches (see dev/mock.js; Studio itself reads screen, menu, item, tab,
# kind, q), window size, JS steps to run once the page is ready (each may return a promise), and clip: a JS
# expression for the element to crop to. Crops are taken at 2x, whole windows at 1x.
SHOTS = {
    # Whole windows
    "studio": dict(q="screen=menus"),
    "studio-item": dict(q="screen=menus&menu=tools&item=8"),
    "studio-library": dict(q="screen=library"),
    "studio-settings": dict(q="screen=settings"),
    "setup": dict(q="screen=setup&zb=both&ringtried=done"),
    "setup-restart": dict(q="screen=setup&zb=2026&zbstale"),
    "browser": dict(page="popout.html", q="kind=brush", size=(980, 680)),
    "library-tag": dict(q="screen=library", steps=["click('Blocking')"]),
    # Details
    "settings-colours": dict(q="screen=settings", clip="card('Colours')"),
    "settings-behaviour": dict(q="screen=settings", clip="card('Behaviour')"),
    "settings-bridge": dict(q="screen=settings", clip="card('ZBrush bridge')"),
    "settings-older-zbrush": dict(q="screen=settings&zb=both", clip="card('Older ZBrush')"),
    "settings-import-export": dict(q="screen=settings", clip="card('Import and export')"),
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
    def handle_error(self, request, client_address):
        pass                                            # Edge dropping a connection on exit is not news


def serve():
    httpd = Server(("127.0.0.1", 0), functools.partial(Handler, directory=UI))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def start_edge(profile):
    exe = next((p for p in EDGE if os.path.exists(p)), None)
    if not exe:
        sys.exit("Microsoft Edge not found")
    proc = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile,
                             "--no-first-run", "--hide-scrollbars", "--force-color-profile=srgb", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_file = os.path.join(profile, "DevToolsActivePort")
    for _ in range(100):
        if os.path.exists(port_file) and open(port_file).read().strip():
            return proc, int(open(port_file).read().split()[0])
        time.sleep(0.1)
    proc.kill()
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


async def run(names):
    if not os.path.exists(MOCK):
        record()
    httpd = serve()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        # A fresh Edge for every shot: after a few shots one Edge started drawing pages without their colours
        # (orange buttons came out grey), although the page's styles were right.
        for name in names:
            profile = tempfile.mkdtemp(prefix="zorbit-shots-")
            proc, port = start_edge(profile)
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
                proc.kill()
                proc.wait()
                shutil.rmtree(profile, ignore_errors=True)
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
