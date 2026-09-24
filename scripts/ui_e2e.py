"""Browser end-to-end check of the Schematic Studio using Chrome DevTools Protocol.

Drives the real UI with real mouse/keyboard events (no test hooks in the app):
select → edit parameter → delete (validation error appears) → undo → wire tool connect →
drag-move → open another example → validation & explain tabs. Screenshots are saved.

    python -m cli.main studio serve          # in one terminal (frontend built into frontend/dist)
    python scripts/ui_e2e.py [--url http://127.0.0.1:8765] [--out scratch/ui]
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class Browser:
    def __init__(self, port: int = 9333):
        self.profile = tempfile.mkdtemp(prefix="studio-e2e-")
        self.proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.profile}", "--window-size=1600,950", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                ws = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        self.ws = connect(ws, max_size=50_000_000)
        self.i = 0
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS error in {expr[:80]}: {r['exceptionDetails']}")
        return r["result"].get("value")

    def wait(self, expr: str, timeout: float = 15.0):
        t = time.time()
        while time.time() - t < timeout:
            if self.js(expr):
                return True
            time.sleep(0.15)
        raise TimeoutError(f"timed out waiting for: {expr}")

    def mouse(self, kind: str, x: float, y: float, button: str = "left", buttons: int = 1):
        self.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button=button, buttons=buttons, clickCount=1)

    def click(self, x: float, y: float):
        self.mouse("mouseMoved", x, y, buttons=0)
        self.mouse("mousePressed", x, y)
        self.mouse("mouseReleased", x, y, buttons=0)

    def key(self, key: str, code: str, vk: int, modifiers: int = 0):
        self.call("Input.dispatchKeyEvent", type="keyDown", key=key, code=code, windowsVirtualKeyCode=vk, modifiers=modifiers)
        self.call("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk, modifiers=modifiers)

    def center(self, selector_js: str):
        r = self.js(f"(() => {{ const e = {selector_js}; if (!e) return null; if (e.scrollIntoView && !(e instanceof SVGElement)) e.scrollIntoView({{block: 'center'}}); const b = e.getBoundingClientRect(); return [b.x + b.width/2, b.y + b.height/2]; }})()")
        if r is None:
            raise RuntimeError(f"element not found: {selector_js}")
        return r

    def shot(self, path: Path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        path.write_bytes(base64.b64decode(data))

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="scratch/ui")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    b = Browser()
    results = []

    def step(name: str, ok: bool, detail: str = ""):
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    try:
        b.call("Page.navigate", url=args.url)
        b.wait("document.querySelector('svg.canvas g.part') !== null")
        b.wait("document.querySelector('.badge') !== null")
        step("studio loads a starter design", True, b.js("document.querySelector('.docname').textContent"))
        b.shot(out / "01_loaded.png")

        part = lambda ref: f"[...document.querySelectorAll('svg.canvas g.part')].find(g => [...g.querySelectorAll('text.ref')].some(t => t.textContent === '{ref}'))"
        # 1. select R3 (LED resistor) by clicking its body
        x, y = b.center(part("R3") + ".querySelector('rect:not(.sel-box)')")
        b.click(x, y)
        b.wait("document.querySelector('.inspector h3')?.textContent === 'R3'")
        step("clicking a symbol selects it and opens the inspector", True)

        # 2. edit its resistance through the inspector (engineering op round trip)
        b.wait("document.querySelector('.inspector table.kv input') !== null")   # registry details loaded
        b.js("""(() => { const inp = [...document.querySelectorAll('.inspector table.kv input')][0];
                 const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                 set.call(inp, '1k'); inp.dispatchEvent(new Event('input', {bubbles: true})); inp.focus(); })()""")
        x, y = b.center("document.querySelector('.inspector h3')")
        b.click(x, y)  # blur commits
        b.wait(part("R3") + "?.querySelector('text.value')?.textContent === '1kΩ'")
        step("parameter edit updates the drawn value", True, "470Ω → 1kΩ")
        b.shot(out / "02_param_edit.png")

        # 3. delete R3 -> validator reports the LED has no current limiting resistor
        b.key("Delete", "Delete", 46)
        b.wait("document.querySelector('.badge.bad') !== null")
        badge = b.js("document.querySelector('.badge').textContent")
        errors = b.js("fetch('/api/health').then(() => [...document.querySelectorAll('.issue')].map(e => e.textContent))")
        b.wait("document.querySelector('.tabs button.on')?.textContent.startsWith('Validation') || true")
        x, y = b.center("[...document.querySelectorAll('aside.right .tabs button')].find(b => b.textContent.startsWith('Electrical'))")
        b.click(x, y)
        b.wait("document.querySelectorAll('.issue.error').length > 0")
        issues = b.js("[...document.querySelectorAll('.issue.error')].map(e => e.textContent)")
        step("deleting the LED resistor produces validation errors", any("E007" in i for i in issues) or any("E009" in i for i in issues),
             f"{badge} {issues[:3]}")
        b.shot(out / "03_after_delete.png")

        # 4. undo
        b.key("z", "KeyZ", 90, modifiers=2)
        b.wait("document.querySelector('.badge.ok') !== null")
        step("Ctrl+Z restores the valid design", True)

        # 5. wire tool: add a second LED+resistor via the library and connect it
        x, y = b.center("[...document.querySelectorAll('aside.left .tabs button')].find(b => b.textContent === 'Library')")
        b.click(x, y)
        b.wait("document.querySelector('.library .search') !== null")
        b.js("""(() => { const s = document.querySelector('.library .search');
                 const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                 set.call(s, 'buzzer'); s.dispatchEvent(new Event('input', {bubbles: true})); })()""")
        b.wait("document.querySelectorAll('.libitem').length >= 1")
        n_parts = b.js("document.querySelectorAll('svg.canvas g.part').length")
        x, y = b.center("document.querySelector('.libitem .add')")
        b.click(x, y)
        b.wait(f"document.querySelectorAll('svg.canvas g.part').length === {n_parts + 1}")
        step("library 'add' places a new part", True, "buzzer added (unconnected → E009 expected)")
        b.wait("document.querySelector('.badge.bad') !== null")   # new part is unconnected (E009)
        b.key("w", "KeyW", 87)
        pin = lambda ref, pin_id: f"[...document.querySelectorAll('svg.canvas circle.pin-hit')].find(c => c.querySelector('title')?.textContent.startsWith('{ref}.{pin_id}'))"
        bz = b.js("[...document.querySelectorAll('svg.canvas text.ref')].map(t => t.textContent).find(t => t.startsWith('BZ'))")
        # buzzer '-' to ground (Q1 emitter) and '+' to the 9 V rail (R3 top pin)
        for a, c in ((pin(bz, "GND"), pin("Q1", "E")), (pin(bz, "VCC"), pin("R3", "PIN1"))):
            x1, y1 = b.center(a)
            x2, y2 = b.center(c)
            b.click(x1, y1)
            b.wait("document.querySelector('.toolhint')?.textContent.includes('Wiring from') === true")
            b.click(x2, y2)
            b.wait("document.querySelector('.toolhint')?.textContent.includes('Wiring from') === false")
        b.wait("document.querySelector('.status span')?.textContent.includes('vbat') === true")
        issues = b.js("fetch('/api/health').then(() => [...document.querySelectorAll('.issue')].map(e => e.textContent))")
        step("wire tool connects pins through engineering ops", True, b.js("document.querySelector('.status span').textContent"))
        b.wait("[...document.querySelectorAll('.issue.error')].some(e => e.textContent.startsWith('E014'))")
        step("validator flags the 3.3-5 V buzzer on the 9 V rail (E014)", True,
             b.js("[...document.querySelectorAll('.issue.error')].map(e => e.textContent)[0]"))
        b.key("Escape", "Escape", 27)
        b.shot(out / "04_wired.png")
        for _ in range(3):   # undo the two connections and the added buzzer
            b.key("z", "KeyZ", 90, modifiers=2)
            time.sleep(0.4)
        b.wait("document.querySelector('.badge.ok') !== null")
        step("undo returns to the valid design", True)

        # 6. drag Q1 to a new place (presentation op), wires re-route, netlist unchanged
        before = b.js(part("Q1") + ".getBoundingClientRect().x")
        x, y = b.center(part("Q1") + ".querySelector('rect:not(.sel-box)')")
        b.mouse("mouseMoved", x, y, buttons=0)
        b.mouse("mousePressed", x, y)
        for k in range(1, 11):
            b.mouse("mouseMoved", x + 12 * k, y + 6 * k)
        b.mouse("mouseReleased", x + 120, y + 60, buttons=0)
        b.wait(part("Q1") + f".getBoundingClientRect().x > {before} + 40")
        verified = b.js("document.querySelector('.status .right').textContent")
        step("dragging a part moves it and the drawing still matches the netlist", "matches netlist" in verified, verified)
        b.shot(out / "05_dragged.png")

        # 7. open another example and inspect validation + explanation
        x, y = b.center("[...document.querySelectorAll('aside.left .tabs button')].find(b => b.textContent === 'Examples')")
        b.click(x, y)
        b.wait("document.querySelectorAll('.example').length > 5")
        x, y = b.center("[...document.querySelectorAll('.example')].find(e => e.textContent.includes('I2C ADC'))")
        b.click(x, y)
        b.wait("document.querySelector('.docname').textContent.includes('I2C ADC')")
        x, y = b.center("[...document.querySelectorAll('aside.right .tabs button')].find(b => b.textContent === 'Explain')")
        b.click(x, y)
        b.wait("document.querySelector('.explain h4') !== null")
        step("explain tab describes parts, rails and checks", True, b.js("document.querySelectorAll('.explain table.parts tr').length + ' parts'"))
        b.shot(out / "06_example_explain.png")

        # 8. hover a wire highlights its net; clicking selects the net in the inspector
        x, y = b.center("[...document.querySelectorAll('svg.canvas g.wire line:nth-child(2)')].sort((a, c) => (Math.abs(c.x2.baseVal.value - c.x1.baseVal.value) + Math.abs(c.y2.baseVal.value - c.y1.baseVal.value)) - (Math.abs(a.x2.baseVal.value - a.x1.baseVal.value) + Math.abs(a.y2.baseVal.value - a.y1.baseVal.value)))[0]")
        b.click(x, y)
        b.wait("document.querySelector('.inspector h3')?.textContent === 'Net'")
        step("clicking a wire selects its net", True, b.js("document.querySelector('.inspector input').value"))
        b.shot(out / "07_net_selected.png")

        # 9. functional validation: temperature alarm does what was asked; breaking the buzzer drive is caught
        x, y = b.center("[...document.querySelectorAll('.example')].find(e => e.textContent.includes('Temperature Alarm'))")
        b.click(x, y)
        b.wait("document.querySelector('.docname').textContent.includes('Temperature Alarm')")
        x, y = b.center("[...document.querySelectorAll('aside.right .tabs button')].find(b => b.textContent.startsWith('Function'))")
        b.click(x, y)
        b.wait("document.querySelector('.fstatus.pass') !== null")
        step("temperature alarm: functional check PASS with explanation", True,
             b.js("[...document.querySelectorAll('.behavior li')].map(l => l.textContent).slice(0, 3).join(' | ')"))
        x, y = b.center("document.querySelector('.behavior')")
        b.click(x, y)
        b.wait("document.querySelectorAll('svg.canvas .hl-box').length >= 4")
        step("clicking a behaviour highlights its functional path", True,
             f"{b.js('document.querySelectorAll(`svg.canvas .hl-box`).length')} parts highlighted")
        b.shot(out / "08_function_pass.png")
        x, y = b.center(part("BZ1") + ".querySelector('rect:not(.sel-box):not(.hl-box)')")
        b.click(x, y)
        b.wait("document.querySelector('.inspector h3')?.textContent === 'BZ1'")
        x, y = b.center("[...document.querySelectorAll('.inspector table.pins tr')].find(r => r.textContent.startsWith('GND')).querySelector('button.icon')")
        b.click(x, y)
        b.wait("document.querySelector('.badge.bad')?.textContent.includes('function') === true")
        x, y = b.center("[...document.querySelectorAll('aside.right .tabs button')].find(b => b.textContent.startsWith('Function'))")
        b.click(x, y)
        b.wait("[...document.querySelectorAll('.function .issue.error')].some(e => e.textContent.startsWith('F004'))")
        elec = b.js("document.querySelector('.badge').textContent")
        step("disconnecting the buzzer's drive: electrically still valid, functionally FAIL (F004)", "valid" in elec,
             b.js("[...document.querySelectorAll('.function .issue.error')].map(e => e.textContent)[0].slice(0, 110)"))
        b.shot(out / "09_function_fail.png")
        b.key("z", "KeyZ", 90, modifiers=2)
        b.wait("document.querySelector('.fstatus.pass') !== null")
        step("undo restores the functional PASS", True)
    except Exception as e:
        step("unexpected failure", False, f"{type(e).__name__}: {e}")
        b.shot(out / "zz_failure.png")
    finally:
        b.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} UI checks passed; screenshots in {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
