#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT=/workspace/qwen-image-edit-models
mkdir -p "$MODEL_ROOT/diffusion_models" "$MODEL_ROOT/text_encoders" "$MODEL_ROOT/vae" "$MODEL_ROOT/loras"

download_model() {
  local target="$1"
  local url="$2"
  if [ ! -s "$target" ]; then
    echo "Downloading $(basename "$target") to persistent storage..."
    wget --progress=dot:giga -O "$target.part" "$url"
    mv "$target.part" "$target"
  fi
}

download_model "$MODEL_ROOT/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" \
  "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors"
download_model "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
download_model "$MODEL_ROOT/vae/qwen_image_vae.safetensors" \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"
download_model "$MODEL_ROOT/loras/HRP_20.safetensors" \
  "https://huggingface.co/prithivMLmods/Qwen-Image-Edit-2511-Hyper-Realistic-Portrait/resolve/main/HRP_20.safetensors"

mkdir -p /comfyui/models/diffusion_models /comfyui/models/text_encoders /comfyui/models/vae /comfyui/models/loras
ln -sf "$MODEL_ROOT/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" /comfyui/models/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors
ln -sf "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" /comfyui/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
ln -sf "$MODEL_ROOT/vae/qwen_image_vae.safetensors" /comfyui/models/vae/qwen_image_vae.safetensors
ln -sf "$MODEL_ROOT/loras/HRP_20.safetensors" /comfyui/models/loras/HRP_20.safetensors

cd /comfyui
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

cd /
exec uvicorn pod_api:app --host 0.0.0.0 --port 8000
