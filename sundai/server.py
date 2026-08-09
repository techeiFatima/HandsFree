"""Web UI. Big, legible, Zoom-screenshare-friendly. Pushes every record over
a websocket to a live dashboard."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

UI = Path(__file__).parent / "ui.html"


def make_app(pipeline, title: str = "Sundai"):
    app = FastAPI(title=title)
    clients: set[asyncio.Queue] = set()
    loop_holder: dict = {}

    def broadcast(rec: dict):
        loop = loop_holder.get("loop")
        if loop is None:
            return
        payload = json.dumps(rec)
        for q in list(clients):
            loop.call_soon_threadsafe(_put, q, payload)

    def _put(q: asyncio.Queue, payload: str):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    app.state.broadcast = broadcast

    @app.on_event("startup")
    async def _startup():
        loop_holder["loop"] = asyncio.get_running_loop()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(UI.read_text(encoding="utf-8").replace("{{TITLE}}", title))

    @app.get("/status")
    async def status():
        return JSONResponse(pipeline.status())

    @app.get("/latest")
    async def latest():
        return JSONResponse(pipeline.latest)

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        clients.add(q)
        try:
            if pipeline.latest:
                await sock.send_text(json.dumps(pipeline.latest))
            while True:
                await sock.send_text(await q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            clients.discard(q)

    return app
