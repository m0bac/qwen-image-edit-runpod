FROM runpod/worker-comfyui:5.8.6-base

RUN uv pip install --no-cache-dir fastapi uvicorn python-multipart

COPY pod/start-pod.sh /start-pod.sh
COPY pod/pod_api.py /pod_api.py
COPY pod/download_models.py /download_models.py
RUN chmod +x /start-pod.sh

EXPOSE 8000
CMD ["/start-pod.sh"]
