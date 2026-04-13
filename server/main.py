# entry — python ws server for the fake monitor
import asyncio
import errno
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websockets

from sim_stuff import (
    TOPOLOGY,
    apply_command,
    create_sim_state,
    snapshot_for_wire,
    tick_sim,
)

PORT = int(os.environ.get("PORT", "3333"))
HTTP_DEV_PORT = int(os.environ.get("HTTP_DEV_PORT", "8088"))

state = create_sim_state()
clients = set()


async def broadcast_tick():
    while True:
        tick_sim(state)
        payload = snapshot_for_wire(state)
        raw = json.dumps(payload)
        dead = []
        for ws in list(clients):
            try:
                await ws.send(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)
        await asyncio.sleep(0.9)


async def handler(ws):
    clients.add(ws)
    try:
        hello = {
            "type": "hello",
            "topology": TOPOLOGY,
            "services": state["services"],
            "events": state["recentEvents"],
            "runId": state["runId"],
        }
        await ws.send(json.dumps(hello))
        async for message in ws:
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                continue
            apply_command(state, msg)
    finally:
        clients.discard(ws)


def _maybe_dev_http():
    # so you dont paste ws:// in the browser bar (that sends wrong headers)
    if os.environ.get("DEV_HTTP", "1") == "0":
        return
    root = os.path.dirname(os.path.abspath(__file__))

    class _H(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    class _Srv(ThreadingHTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    def run():
        os.chdir(root)
        try:
            httpd = _Srv(("0.0.0.0", HTTP_DEV_PORT), _H)
        except OSError as e:
            print("dev http skipped (port busy?):", e, flush=True)
            return
        httpd.serve_forever()

    threading.Thread(target=run, name="dev-http", daemon=True).start()
    print(
        f"dev page (open in browser): http://127.0.0.1:{HTTP_DEV_PORT}/dev_client.html",
        flush=True,
    )
    print("  (set DEV_HTTP=0 to turn this off)", flush=True)


def _port_in_use(err):
    if getattr(err, "winerror", None) == 10048:
        return True
    if err.errno in (getattr(errno, "EADDRINUSE", 98), 10048):
        return True
    return False


async def main():
    _maybe_dev_http()
    asyncio.create_task(broadcast_tick())
    try:
        async with websockets.serve(handler, "0.0.0.0", PORT):
            print("ws server up on", PORT, flush=True)
            await asyncio.Future()
    except OSError as e:
        if _port_in_use(e):
            print(
                f"port {PORT} already in use (another python main.py, docker, etc).\n"
                f"  fix: stop that process, or pick another port:\n"
                f"    PowerShell:  $env:PORT=3334; python main.py\n"
                f"    cmd.exe:     set PORT=3334&& python main.py\n"
                f"  who owns it:  netstat -ano | findstr :{PORT}",
                file=sys.stderr,
                flush=True,
            )
        raise


if __name__ == "__main__":
    asyncio.run(main())
