"""
FastAPI app for the optional Web2MP3 GUI.

Serves one static page, drives submissions via runner.py (a fresh
`python src/main.py --sync <url>` per submission, attached to a PTY), and
streams output live over a WebSocket. See GUI_PLAN.md for the full design.

Auth: if GUI_PASSWORD is set, every route (including the WebSocket upgrade)
requires HTTP Basic Auth matching it. Unset (default) -> no auth at all.
"""
import asyncio
import base64
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

import cookie_check  # noqa: E402
import runner  # noqa: E402
import sessions  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _password_ok(authorization: str | None) -> bool:
    expected = os.environ.get("GUI_PASSWORD")
    if not expected:
        return True
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[len("Basic "):]).decode("utf-8")
    except Exception:
        return False
    _, _, password = decoded.partition(":")
    return secrets.compare_digest(password, expected)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not _password_ok(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner.reconcile_after_restart()
    yield


app = FastAPI(title="Web2MP3", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/static/app.js", dependencies=[Depends(require_auth)])
def static_app_js() -> PlainTextResponse:
    return PlainTextResponse(
        (STATIC_DIR / "app.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
    )


@app.get("/static/style.css", dependencies=[Depends(require_auth)])
def static_style_css() -> PlainTextResponse:
    return PlainTextResponse(
        (STATIC_DIR / "style.css").read_text(encoding="utf-8"),
        media_type="text/css",
    )


class SubmitRequest(BaseModel):
    url: str


@app.post("/api/submit", dependencies=[Depends(require_auth)])
def submit(req: SubmitRequest) -> dict:
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    sid = runner.start(url)
    return {"id": sid}


@app.get("/api/cookies", dependencies=[Depends(require_auth)])
def cookie_status() -> dict:
    status = cookie_check.assess_installed()
    return {"ok": status.ok, "message": status.message}


@app.post("/api/cookies", dependencies=[Depends(require_auth)])
async def upload_cookies(file: UploadFile = File(...)) -> JSONResponse:
    raw = await file.read(cookie_check.MAX_COOKIE_BYTES + 1)
    if len(raw) > cookie_check.MAX_COOKIE_BYTES:
        return JSONResponse(
            {"ok": False, "message": "Cookie file is larger than 1 MB."},
            status_code=400,
        )
    content = raw.decode("utf-8", errors="replace")
    status = cookie_check.assess_upload(content)
    if not status.ok:
        return JSONResponse(
            {"ok": False, "message": status.message},
            status_code=400,
        )
    try:
        saved = cookie_check.save_cookie_text(content)
    except OSError as exc:
        return JSONResponse(
            {"ok": False, "message": f"Could not save cookie file: {exc.strerror or exc}"},
            status_code=500,
        )
    return JSONResponse({"ok": True, "message": saved.message})


@app.get("/api/sessions", dependencies=[Depends(require_auth)])
def list_sessions() -> list:
    return sessions.list_all()


@app.get("/api/sessions/{sid}/transcript", dependencies=[Depends(require_auth)])
def get_transcript(sid: str) -> dict:
    entry = sessions.get(sid)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown submission")
    return {"entry": entry, "transcript": sessions.read_transcript(sid)}


@app.websocket("/ws/{sid}")
async def ws_endpoint(websocket: WebSocket, sid: str) -> None:
    if not _password_ok(websocket.headers.get("authorization")):
        await websocket.close(code=4401)
        return

    entry = sessions.get(sid)
    if entry is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    if not runner.subscribe(sid, loop, queue):
        # Submission already finished before the client connected here --
        # nothing live to stream; the client falls back to the transcript
        # REST endpoint for the final output.
        await websocket.send_json({"type": "status", "status": entry["status"]})
        await websocket.close()
        return

    async def _forward_incoming() -> None:
        try:
            while True:
                data = await websocket.receive_json()
                runner.send_input(sid, data.get("input", ""))
        except WebSocketDisconnect:
            pass

    forward_task = asyncio.create_task(_forward_incoming())
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
            if message.get("type") == "status" and message.get("status") in ("done", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        runner.unsubscribe(sid, queue)
