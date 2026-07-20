import json
import os
import sys
import time
import urllib.request


target, url, label, index, total, progress_path = sys.argv[1:]
index, total = int(index), int(total)


def report(stage: str, file_percent: float):
    overall = round(((index + file_percent / 100) / total) * 90)
    payload = {
        "stage": stage,
        "label": label,
        "percent": overall,
        "filePercent": round(file_percent),
        "current": index + 1,
        "total": total,
    }
    temporary = f"{progress_path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(payload, handle)
    os.replace(temporary, progress_path)


if os.path.exists(target) and os.path.getsize(target) > 0:
    report("cached", 100)
    print(f"Using cached {label}.")
    raise SystemExit(0)

print(f"Downloading {label} to persistent storage...")
part = f"{target}.part"
headers = {"User-Agent": "qwen-pod/1.0"}
if "civitai.com" in url or "civitai.red" in url:
    token = os.environ.get("CIVITAI_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
request = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as output:
    expected = int(response.headers.get("Content-Length") or 0)
    downloaded = 0
    last_report = 0.0
    while True:
        chunk = response.read(8 * 1024 * 1024)
        if not chunk:
            break
        output.write(chunk)
        downloaded += len(chunk)
        now = time.monotonic()
        if now - last_report >= 0.5:
            report("downloading", (downloaded / expected * 100) if expected else 0)
            last_report = now

os.replace(part, target)
report("downloaded", 100)
