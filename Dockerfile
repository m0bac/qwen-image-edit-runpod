FROM runpod/worker-comfyui:5.8.6-base

# Keep the version-matched handler in this repo so RunPod's GitHub validator
# can detect the serverless entrypoint, then replace the identical base copy.
COPY handler.py /handler.py

RUN comfy model download \
  --url https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors \
  --relative-path models/diffusion_models \
  --filename qwen_image_edit_2511_fp8mixed.safetensors

RUN comfy model download \
  --url https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors \
  --relative-path models/text_encoders \
  --filename qwen_2.5_vl_7b_fp8_scaled.safetensors

RUN comfy model download \
  --url https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors \
  --relative-path models/vae \
  --filename qwen_image_vae.safetensors
