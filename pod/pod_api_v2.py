import base64
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import websocket
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

COMFY = "http://127.0.0.1:8188"
COMFY_WS = "ws://127.0.0.1:8188/ws"
INPUT_DIR = Path("/comfyui/input")
ACCESS_TOKEN = os.environ.get("POD_ACCESS_TOKEN", "")
PROGRESS_FILE = Path("/workspace/qwen-image-edit-models/startup-progress.json")
JOB_PROGRESS: dict[str, int] = {}
JOB_ERRORS: dict[str, str] = {}
PROGRESS_LOCK = threading.Lock()

app = FastAPI(title="Private Photo and Video ComfyUI Pod API")


def require_token(authorization: str | None = Header(default=None)):
    if not ACCESS_TOKEN:
        raise HTTPException(503, "POD_ACCESS_TOKEN is not configured")
    if authorization != f"Bearer {ACCESS_TOKEN}":
        raise HTTPException(401, "Invalid Pod access token")


def comfy_json(path: str, method: str = "GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def startup_status():
    try:
        return json.loads(PROGRESS_FILE.read_text())
    except Exception:
        return {"stage": "initializing", "label": "Starting the Pod", "percent": 0}


def track_progress(socket: websocket.WebSocket, prompt_id: str):
    try:
        socket.settimeout(600)
        while True:
            message = socket.recv()
            if not isinstance(message, str):
                continue
            event = json.loads(message)
            event_type = event.get("type")
            data = event.get("data", {})
            event_prompt = data.get("prompt_id")
            if event_prompt and event_prompt != prompt_id:
                continue
            if event_type == "execution_start":
                with PROGRESS_LOCK:
                    JOB_PROGRESS[prompt_id] = max(1, JOB_PROGRESS.get(prompt_id, 0))
            elif event_type == "progress":
                maximum = max(1, int(data.get("max") or 1))
                value = max(0, int(data.get("value") or 0))
                percent = min(99, round(value / maximum * 100))
                with PROGRESS_LOCK:
                    JOB_PROGRESS[prompt_id] = percent
            elif event_type == "execution_error":
                with PROGRESS_LOCK:
                    JOB_ERRORS[prompt_id] = str(data.get("exception_message") or "ComfyUI execution failed")[:500]
                break
            elif event_type == "executing" and data.get("node") is None:
                with PROGRESS_LOCK:
                    JOB_PROGRESS[prompt_id] = 100
                break
    except Exception:
        pass
    finally:
        try:
            socket.close()
        except Exception:
            pass


class InputImage(BaseModel):
    name: str
    image: str


class JobRequest(BaseModel):
    workflow: dict
    images: list[InputImage]


@app.get("/health", dependencies=[Depends(require_token)])
def health():
    progress = startup_status()
    return {"ready": progress.get("stage") == "ready", "startup": progress}


@app.get("/startup", dependencies=[Depends(require_token)])
def startup():
    return startup_status()


@app.post("/jobs", dependencies=[Depends(require_token)])
def create_job(request: JobRequest):
    if startup_status().get("stage") != "ready":
        raise HTTPException(503, "Models are still loading")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in request.images:
        name = Path(item.name).name
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise HTTPException(400, "Invalid image filename")
        encoded = item.image.split(",", 1)[-1]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as error:
            raise HTTPException(400, "Invalid base64 image") from error
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(413, "Image exceeds 20 MB")
        (INPUT_DIR / name).write_bytes(raw)

    client_id = str(uuid.uuid4())
    socket = None
    try:
        socket = websocket.WebSocket()
        socket.connect(f"{COMFY_WS}?clientId={client_id}", timeout=10)
    except Exception:
        socket = None

    result = comfy_json(
        "/prompt",
        method="POST",
        payload={"prompt": request.workflow, "client_id": client_id},
    )
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        if socket:
            socket.close()
        raise HTTPException(502, result.get("error", "ComfyUI rejected the workflow"))

    with PROGRESS_LOCK:
        JOB_PROGRESS[prompt_id] = 0
    if socket:
        threading.Thread(target=track_progress, args=(socket, prompt_id), daemon=True).start()
    return {"id": prompt_id, "status": "queued", "progress": 0}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise HTTPException(400, "Invalid job ID")

    with PROGRESS_LOCK:
        progress = JOB_PROGRESS.get(job_id, 0)
        live_error = JOB_ERRORS.get(job_id)
    if live_error:
        return {"status": "failed", "error": live_error, "progress": progress}

    history = comfy_json(f"/history/{job_id}")
    job = history.get(job_id)
    if job:
        status = job.get("status", {})
        if status.get("status_str") == "error":
            messages = status.get("messages", [])
            return {"status": "failed", "error": str(messages[-1] if messages else "ComfyUI job failed")[:500], "progress": progress}
        for output in job.get("outputs", {}).values():
            for media_key in ("videos", "video", "gifs", "images", "files"):
                media_items = output.get(media_key, [])
                if isinstance(media_items, dict):
                    media_items = [media_items]
                if not media_items:
                    continue
                media = media_items[0]
                if not isinstance(media, dict) or not media.get("filename"):
                    continue
                query = urllib.parse.urlencode({
                    "filename": media["filename"],
                    "subfolder": media.get("subfolder", ""),
                    "type": media.get("type", "output"),
                })
                with urllib.request.urlopen(f"{COMFY}/view?{query}", timeout=60) as response:
                    raw = response.read()
                    encoded = base64.b64encode(raw).decode()
                    mime = response.headers.get_content_type()
                if not mime or mime == "application/octet-stream":
                    suffix = Path(media["filename"]).suffix.lower()
                    mime = {".mp4": "video/mp4", ".webm": "video/webm", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")
                kind = "video" if mime.startswith("video/") else "image"
                return {"status": "completed", "result": f"data:{mime};base64,{encoded}", "mediaType": kind, "filename": media["filename"], "progress": 100}

    queue = comfy_json("/queue")
    if any(job_id in json.dumps(item) for item in queue.get("queue_running", [])):
        return {"status": "running", "progress": progress}
    if any(job_id in json.dumps(item) for item in queue.get("queue_pending", [])):
        return {"status": "queued", "progress": 0}
    return {"status": "running", "progress": progress}
