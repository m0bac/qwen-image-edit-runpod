import os
for key in ("NO_PROXY", "no_proxy"):
    os.environ[key] = ",".join(dict.fromkeys(filter(None, os.environ.get(key, "").split(",") + ["127.0.0.1", "localhost"])))

import re, threading, urllib.parse, urllib.request, uuid
from pathlib import Path
import websocket
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from pod_api_base import app, require_token

connect = websocket.WebSocket.connect
def local_connect(self, url, *args, **kwargs):
    if url.startswith(("ws://127.0.0.1", "ws://localhost")):
        kwargs.update(http_no_proxy=["127.0.0.1", "localhost"], suppress_origin=True)
    return connect(self, url, *args, **kwargs)
websocket.WebSocket.connect = local_connect

ROOT = Path("/workspace/qwen-image-edit-models/loras")
COMFY = Path("/comfyui/models/loras")
TASKS, LOCK = {}, threading.Lock()

class Install(BaseModel):
    url: str

def safe_name(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ("huggingface.co", "civitai.com")):
        raise HTTPException(400, "Use an HTTPS Hugging Face or CivitAI download URL")
    name = urllib.parse.parse_qs(parsed.query).get("filename", [""])[0] or Path(urllib.parse.unquote(parsed.path)).name
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    return ((name or "custom_lora") + ("" if name.lower().endswith(".safetensors") else ".safetensors"))[:180]

def download(task, url, name):
    ROOT.mkdir(parents=True, exist_ok=True); COMFY.mkdir(parents=True, exist_ok=True)
    target, part = ROOT / name, ROOT / (name + ".part")
    try:
        headers = {"User-Agent": "ComfyUI-Photo-Runner/1.0"}
        if os.environ.get("CIVITAI_API_TOKEN") and (urllib.parse.urlparse(url).hostname or "").endswith("civitai.com"):
            headers["Authorization"] = "Bearer " + os.environ["CIVITAI_API_TOKEN"]
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as source, open(part, "wb") as output:
            total, current = int(source.headers.get("Content-Length") or 0), 0
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk: break
                current += len(chunk)
                if current > 6 * 1024**3: raise ValueError("LoRA exceeds 6 GB")
                output.write(chunk)
                with LOCK: TASKS[task].update(status="downloading", progress=round(current / total * 100) if total else 0)
        if part.stat().st_size < 1024: raise ValueError("Downloaded file is not a valid LoRA")
        os.replace(part, target)
        link = COMFY / name
        if link.is_symlink() or link.exists(): link.unlink()
        link.symlink_to(target)
        with LOCK: TASKS[task].update(status="completed", progress=100)
    except Exception as error:
        part.unlink(missing_ok=True)
        with LOCK: TASKS[task].update(status="failed", error=str(error)[:300])

@app.get("/loras", dependencies=[Depends(require_token)])
def list_loras():
    ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK: tasks = list(TASKS.values())
    return {"loras": [{"name": p.name, "size": p.stat().st_size} for p in sorted(ROOT.glob("*.safetensors"))], "installs": tasks}

@app.post("/loras", dependencies=[Depends(require_token)])
def add_lora(request: Install):
    name = safe_name(request.url)
    if (ROOT / name).exists(): raise HTTPException(409, "That LoRA is already installed")
    task = uuid.uuid4().hex
    with LOCK: TASKS[task] = {"id": task, "name": name, "status": "starting", "progress": 0}
    threading.Thread(target=download, args=(task, request.url, name), daemon=True).start()
    return TASKS[task]

@app.delete("/loras/{name}", dependencies=[Depends(require_token)])
def remove_lora(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.safetensors", name) or name == "HRP_20.safetensors": raise HTTPException(400, "This LoRA cannot be removed")
    target = ROOT / name
    if not target.exists(): raise HTTPException(404, "LoRA not found")
    target.unlink()
    link = COMFY / name
    if link.is_symlink() or link.exists(): link.unlink()
    return {"ok": True}
