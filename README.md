# Qwen Image Edit 2511 — RunPod Serverless

Private RunPod worker for `Qwen/Qwen-Image-Edit-2511`, using the official
RunPod ComfyUI worker and ComfyUI's native Qwen image-edit nodes.

## Deploy from GitHub

1. In RunPod, open **Serverless → New Endpoint → Start from GitHub Repo**.
2. Select this repository and the `main` branch.
3. Set **Context Path** to `/` and **Dockerfile Path** to `Dockerfile`.
4. Choose one 48 GB GPU, set **Active Workers** to `0`, and **Max Workers** to `1` while testing.
5. Enable Flash Boot and deploy.

The first build is large because the Qwen diffusion model, text encoder, and VAE
are baked into the container. No Hugging Face token is required for these public files.

## Request format

The worker accepts the standard `worker-comfyui` request contract:

```json
{
  "input": {
    "workflow": { "...": "API workflow from workflows/qwen_image_edit_2511_api.json" },
    "images": [
      {
        "name": "input_image_1.png",
        "image": "data:image/png;base64,..."
      }
    ]
  }
}
```

Before submitting, replace `__PROMPT__` in node `9`. Optional controls are node
`13`: `seed`, `steps`, and `cfg`. The defaults match ComfyUI's official non-Lightning
Qwen 2511 workflow: 40 steps, CFG 4, Euler, simple scheduler.

If S3 output is not configured, the worker returns the edited image as base64.

## Model sources

- Qwen Image Edit 2511 diffusion model: Comfy-Org/Qwen-Image-Edit_ComfyUI
- Qwen 2.5 VL text encoder: Comfy-Org/HunyuanVideo_1.5_repackaged
- Qwen Image VAE: Comfy-Org/Qwen-Image_ComfyUI

Qwen-Image-Edit-2511 is released under Apache-2.0. Check the upstream model cards
and licenses before changing or redistributing model files.
