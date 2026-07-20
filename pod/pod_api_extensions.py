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


VIDEO_MODEL_ROOT = Path("/workspace/qwen-image-edit-models")
VIDEO_MODEL_TASKS, VIDEO_MODEL_LOCK = {}, threading.Lock()
WAN_MODEL_ID = "wan-2.2-ti2v-5b"
WAN_MODEL_FILES = (
    ("diffusion_models", "wan2.2_ti2v_5B_fp16.safetensors", "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"),
    ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    ("vae", "wan2.2_vae.safetensors", "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"),
)

def wan_model_ready():
    return all((VIDEO_MODEL_ROOT / folder / name).exists() and (VIDEO_MODEL_ROOT / folder / name).stat().st_size > 1024 for folder, name, _ in WAN_MODEL_FILES)

def link_video_model_files():
    for folder, name, _ in WAN_MODEL_FILES:
        source = VIDEO_MODEL_ROOT / folder / name
        destination_dir = Path("/comfyui/models") / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / name
        if destination.is_symlink() or destination.exists():
            destination.unlink()
        destination.symlink_to(source)

def download_video_model_bundle(task_id):
    try:
        count = len(WAN_MODEL_FILES)
        for index, (folder, name, url) in enumerate(WAN_MODEL_FILES):
            target_dir = VIDEO_MODEL_ROOT / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / name
            if target.exists() and target.stat().st_size > 1024:
                with VIDEO_MODEL_LOCK:
                    VIDEO_MODEL_TASKS[task_id].update(file=name, progress=round((index + 1) / count * 100))
                continue
            part = target.with_suffix(target.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-Photo-Runner/1.0"})
            with urllib.request.urlopen(request, timeout=90) as source, open(part, "wb") as output:
                total, current = int(source.headers.get("Content-Length") or 0), 0
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    current += len(chunk)
                    file_progress = (current / total * 100) if total else 0
                    overall = round((index + file_progress / 100) / count * 100)
                    with VIDEO_MODEL_LOCK:
                        VIDEO_MODEL_TASKS[task_id].update(status="downloading", file=name, progress=overall)
            if part.stat().st_size < 1024:
                raise ValueError(f"{name} did not download correctly")
            os.replace(part, target)
        link_video_model_files()
        with VIDEO_MODEL_LOCK:
            VIDEO_MODEL_TASKS[task_id].update(status="ready", file="", progress=100)
    except Exception as error:
        with VIDEO_MODEL_LOCK:
            VIDEO_MODEL_TASKS[task_id].update(status="failed", error=str(error)[:300])

@app.get("/models", dependencies=[Depends(require_token)])
def list_video_models():
    ready = wan_model_ready()
    if ready:
        link_video_model_files()
    with VIDEO_MODEL_LOCK:
        task = dict(VIDEO_MODEL_TASKS.get(WAN_MODEL_ID, {}))
    wan_status = task or {
        "id": WAN_MODEL_ID,
        "title": "Wan 2.2 TI2V-5B",
        "status": "ready" if ready else "not_installed",
        "progress": 100 if ready else 0,
        "file": "",
    }
    ltx_ready = (VIDEO_MODEL_ROOT / "checkpoints/ltx-2.3-22b-dev-fp8.safetensors").exists()
    return {"models": [
        {"id": "ltx-2.3", "title": "LTX 2.3", "status": "ready" if ltx_ready else "not_installed", "progress": 100 if ltx_ready else 0},
        wan_status,
    ]}

@app.post("/models/wan-2.2-ti2v-5b/install", dependencies=[Depends(require_token)])
def install_wan_video_model():
    if wan_model_ready():
        link_video_model_files()
        return {"id": WAN_MODEL_ID, "title": "Wan 2.2 TI2V-5B", "status": "ready", "progress": 100, "file": ""}
    with VIDEO_MODEL_LOCK:
        existing = VIDEO_MODEL_TASKS.get(WAN_MODEL_ID)
        if existing and existing.get("status") in ("starting", "downloading"):
            return existing
        task = {"id": WAN_MODEL_ID, "title": "Wan 2.2 TI2V-5B", "status": "starting", "progress": 0, "file": ""}
        VIDEO_MODEL_TASKS[WAN_MODEL_ID] = task
    threading.Thread(target=download_video_model_bundle, args=(WAN_MODEL_ID,), daemon=True).start()
    return task
