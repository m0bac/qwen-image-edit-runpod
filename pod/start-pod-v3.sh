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
  "Qwen image model" 0 8
download_model "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "Qwen text encoder" 1 8
download_model "$MODEL_ROOT/vae/qwen_image_vae.safetensors" \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
  "Qwen image VAE" 2 8
download_model "$MODEL_ROOT/loras/HRP_20.safetensors" \
  "https://huggingface.co/prithivMLmods/Qwen-Image-Edit-2511-Hyper-Realistic-Portrait/resolve/main/HRP_20.safetensors" \
  "Portrait realism LoRA" 3 8
download_model "$MODEL_ROOT/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" \
  "https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" \
  "Lightning 4-Step LoRA" 4 8
download_model "$MODEL_ROOT/loras/qwen-image-edit-2511-multiple-angles-lora.safetensors" \
  "https://huggingface.co/AdversaLLC/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors" \
  "Multiple angles LoRA" 5 8
download_model "$MODEL_ROOT/loras/AnythingtoRealCharacters2511_20.safetensors" \
  "https://huggingface.co/WarmBloodAban/Anything_to_Real_Characters_2511/resolve/main/AnythingtoRealCharacters2511_20.safetensors" \
  "Anything to Real LoRA" 6 8
if ! download_model "$MODEL_ROOT/loras/Qwen-MysticXXX-v1.safetensors" \
  "https://civitai.com/api/download/models/2195978?type=Model&format=SafeTensor" \
  "Mystic XXX Qwen LoRA" 7 8; then
  echo "Mystic XXX could not be downloaded. Add CIVITAI_API_TOKEN to the Pod if this model requires CivitAI authentication."
  rm -f "$MODEL_ROOT/loras/Qwen-MysticXXX-v1.safetensors.part"
  write_progress "optional_skipped" "Mystic XXX skipped; continuing startup" 90
fi

mkdir -p /comfyui/models/diffusion_models /comfyui/models/text_encoders /comfyui/models/vae /comfyui/models/loras
ln -sf "$MODEL_ROOT/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors" /comfyui/models/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors
ln -sf "$MODEL_ROOT/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" /comfyui/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
ln -sf "$MODEL_ROOT/vae/qwen_image_vae.safetensors" /comfyui/models/vae/qwen_image_vae.safetensors
ln -sf "$MODEL_ROOT/loras/HRP_20.safetensors" /comfyui/models/loras/HRP_20.safetensors
ln -sf "$MODEL_ROOT/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" /comfyui/models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
ln -sf "$MODEL_ROOT/loras/qwen-image-edit-2511-multiple-angles-lora.safetensors" /comfyui/models/loras/qwen-image-edit-2511-multiple-angles-lora.safetensors
ln -sf "$MODEL_ROOT/loras/AnythingtoRealCharacters2511_20.safetensors" /comfyui/models/loras/AnythingtoRealCharacters2511_20.safetensors
if [ -s "$MODEL_ROOT/loras/Qwen-MysticXXX-v1.safetensors" ]; then
  ln -sf "$MODEL_ROOT/loras/Qwen-MysticXXX-v1.safetensors" /comfyui/models/loras/Qwen-MysticXXX-v1.safetensors
fi

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
