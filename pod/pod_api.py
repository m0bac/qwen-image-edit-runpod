import base64
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

COMFY = "http://127.0.0.1:8188"
INPUT_DIR = Path("/comfyui/input")
ACCESS_TOKEN = os.environ.get("POD_ACCESS_TOKEN", "")

app = FastAPI(title="Private Qwen ComfyUI Pod API")


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


class InputImage(BaseModel):
    name: str
    image: str


class JobRequest(BaseModel):
    workflow: dict
    images: list[InputImage]


@app.get("/health", dependencies=[Depends(require_token)])
def health():
    stats = comfy_json("/system_stats")
    return {"ready": True, "comfy": bool(stats)}


@app.post("/jobs", dependencies=[Depends(require_token)])
def create_job(request: JobRequest):
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

    result = comfy_json(
        "/prompt",
        method="POST",
        payload={"prompt": request.workflow, "client_id": str(uuid.uuid4())},
    )
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise HTTPException(502, result.get("error", "ComfyUI rejected the workflow"))
    return {"id": prompt_id, "status": "queued"}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise HTTPException(400, "Invalid job ID")

    history = comfy_json(f"/history/{job_id}")
    job = history.get(job_id)
    if job:
        status = job.get("status", {})
        if status.get("status_str") == "error":
            messages = status.get("messages", [])
            return {"status": "failed", "error": str(messages[-1] if messages else "ComfyUI job failed")[:500]}
        for output in job.get("outputs", {}).values():
            images = output.get("images", [])
            if images:
                image = images[0]
                query = urllib.parse.urlencode({
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                })
                with urllib.request.urlopen(f"{COMFY}/view?{query}", timeout=60) as response:
                    encoded = base64.b64encode(response.read()).decode()
                    mime = response.headers.get_content_type() or "image/png"
                return {"status": "completed", "result": f"data:{mime};base64,{encoded}"}

    queue = comfy_json("/queue")
    if any(job_id in json.dumps(item) for item in queue.get("queue_running", [])):
        return {"status": "running"}
    if any(job_id in json.dumps(item) for item in queue.get("queue_pending", [])):
        return {"status": "queued"}
    return {"status": "running"}
