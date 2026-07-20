FROM runpod/worker-comfyui:5.8.6-base-cuda12.8.1

# Use RunPod's CUDA 12.8.1 worker variant so the bundled PyTorch runtime
# matches the CUDA 12.8 driver level exposed by current Serverless hosts.
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

RUN comfy model download \
  --url https://huggingface.co/prithivMLmods/Qwen-Image-Edit-2511-Hyper-Realistic-Portrait/resolve/main/HRP_20.safetensors \
  --relative-path models/loras \
  --filename HRP_20.safetensors

# Fail the image build instead of deploying a worker whose workflow cannot load
# one of its required models. This specifically prevents the HRP_20 error seen
# in the RunPod worker logs.
RUN test -s /comfyui/models/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors \
  && test -s /comfyui/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors \
  && test -s /comfyui/models/vae/qwen_image_vae.safetensors \
  && test -s /comfyui/models/loras/HRP_20.safetensors
