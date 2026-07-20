#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT=/workspace/qwen-image-edit-models
PROGRESS_FILE="$MODEL_ROOT/startup-progress.json"
mkdir -p "$MODEL_ROOT/diffusion_models" "$MODEL_ROOT/text_encoders" "$MODEL_ROOT/vae" "$MODEL_ROOT/loras"

write_progress() {
  python - "$PROGRESS_FILE" "$1" "$2" "$3" <<'PY'
import json, os, sys
path, stage, label, percent = sys.argv[1:]
temporary = f"{path}.tmp"
with open(temporary, "w") as handle:
    json.dump({"stage": stage, "label": label, "percent": int(percent)}, handle)
os.replace(temporary, path)
PY
}

write_progress "initializing" "Starting the Pod API" 1
cd /
uvicorn pod_api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

download_model() {
  python /download_models.py "$1" "$2" "$3" "$4" "$5" "$PROGRESS_FILE"
}

download_model "$MODEL_ROOT/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" \
  "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" \
  "Qwen image model" 0 4
download_model "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "Qwen text encoder" 1 4
download_model "$MODEL_ROOT/vae/qwen_image_vae.safetensors" \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
  "Qwen image VAE" 2 4
download_model "$MODEL_ROOT/loras/HRP_20.safetensors" \
  "https://huggingface.co/prithivMLmods/Qwen-Image-Edit-2511-Hyper-Realistic-Portrait/resolve/main/HRP_20.safetensors" \
  "Portrait realism LoRA" 3 4

mkdir -p /comfyui/models/diffusion_models /comfyui/models/text_encoders /comfyui/models/vae /comfyui/models/loras
ln -sf "$MODEL_ROOT/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" /comfyui/models/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors
ln -sf "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" /comfyui/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
ln -sf "$MODEL_ROOT/vae/qwen_image_vae.safetensors" /comfyui/models/vae/qwen_image_vae.safetensors
ln -sf "$MODEL_ROOT/loras/HRP_20.safetensors" /comfyui/models/loras/HRP_20.safetensors

cd /comfyui
write_progress "starting_comfy" "Loading ComfyUI and models" 94
python main.py --listen 127.0.0.1 --port 8188 &

python - <<'PY'
import time
import urllib.request

for _ in range(300):
    try:
        urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=2)
        print("ComfyUI is ready.")
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("ComfyUI did not become ready within 5 minutes")
PY

write_progress "ready" "Ready for edits" 100
wait "$API_PID"
