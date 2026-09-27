# bridge3.py -- reads orders from notes-sync and hands them to SX765D
# put a GitHub token in token.txt (same folder) to get fast mode.
import asyncio
import base64
import json
import urllib.request
import urllib.error
from bleak import BleakScanner, BleakClient

NAME = "SX765D"
CHR  = "0000ffe1-0000-1000-8000-00805f9b34fb"
BOX  = "https://api.github.com/repos/csdrkhrbnn-jpg/notes-sync/contents/state.json?ref=main"

TOKEN = ""
try:
    with open("token.txt", "r", encoding="utf-8") as f:
        TOKEN = f.read().strip()
except Exception:
    TOKEN = ""

TICK = 1.5 if TOKEN else 60.0
print("token:", "yes" if TOKEN else "no -> slow mode (1/min)")

_etag = None
_state = None
_quiet = 0


def fetch():
    global _etag, _state, _quiet
    h = {"User-Agent": "sync", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = "Bearer " + TOKEN
    if _etag:
        h["If-None-Match"] = _etag
    req = urllib.request.Request(BOX, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _etag = r.headers.get("ETag")
            j = json.loads(r.read().decode())
            _state = json.loads(base64.b64decode(j["content"]).decode())
            _quiet = 0
    except urllib.error.HTTPError as e:
        if e.code != 304:
            if _quiet % 30 == 0:
                print("box error:", e, "(still trying)")
            _quiet += 1
    except Exception as e:
        if _quiet % 30 == 0:
            print("box error:", e, "(still trying)")
        _quiet += 1
    return _state


def packet(c, a, b):
    if c == 0:
        return bytes([0x55, 0x04, 0x00, 0x00, 0x00, 0x00, 0xAA])
    if c == 1:
        return bytes([0x55, 0x04, 0x00, 0x00, 0x01, a & 0xFF, 0xAA])
    if c == 2:
        return bytes([0x55, 0x03, 0x00, 0x00, a & 0xFF, b & 0xFF, 0x00])
    return None


async def run():
    print("scanning...")
    devs = await BleakScanner.discover(timeout=10.0)
    t = None
    for d in devs:
        if d.name and NAME in d.name:
            t = d
            break
    if t is None:
        print("NOT FOUND:", NAME)
        return
    print("found:", t.name, t.address)

    async with BleakClient(t) as c:
        print("connected:", c.is_connected)
        cur = (0, 0, 0)
        seen = None
        while c.is_connected:
            st = await asyncio.to_thread(fetch)
            if st is not None:
                if seen is None:
                    seen = st["n"]
                    print("box ok. n =", seen, "| standing by")
                elif st["n"] != seen:
                    seen = st["n"]
                    cur = (st["c"], st["a"], st["b"])
                    print(">>> order:", cur)
            p = packet(cur[0], cur[1], cur[2])
            if p:
                await c.write_gatt_char(CHR, p, response=False)
            await asyncio.sleep(TICK)


async def main():
    while True:
        try:
            await run()
        except Exception as e:
            print("lost:", e)
        print("reconnect in 3 s ...")
        await asyncio.sleep(3)


asyncio.run(main())
