"""MEC inference service: receives a JPEG frame, classifies it with ResNet50, returns label + timing.

Set FAKE=1 to skip PyTorch (sleeps ~40 ms) for wiring tests.
"""
import io
import os
import time

import psutil
from fastapi import FastAPI, File, UploadFile
from PIL import Image

FAKE = os.environ.get("FAKE") == "1"
EXTRA_DELAY_MS = float(os.environ.get("EXTRA_DELAY_MS", "0"))  # test knob only

if not FAKE:
    import torch
    import torchvision

    weights = torchvision.models.ResNet50_Weights.DEFAULT  # baked into the image at build time
    model = torchvision.models.resnet50(weights=weights).eval()
    prep = weights.transforms()
    labels = weights.meta["categories"]
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))

app = FastAPI()
psutil.cpu_percent()  # prime the counter


@app.get("/ping")
def ping():
    return {"ok": True, "cpu": psutil.cpu_percent(), "model": "fake" if FAKE else "resnet50"}


@app.post("/classify")
async def classify(file: UploadFile = File(...)):
    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    t0 = time.perf_counter()
    if FAKE:
        time.sleep(0.04)
        label, conf = "fake", 0.5
    else:
        with torch.no_grad():
            out = model(prep(img).unsqueeze(0))
            probs = out.softmax(1)[0]
            conf, idx = probs.max(0)
        label, conf = labels[int(idx)], float(conf)
    server_ms = (time.perf_counter() - t0) * 1000
    if EXTRA_DELAY_MS:
        time.sleep(EXTRA_DELAY_MS / 1000)
    return {"label": label, "conf": conf, "server_ms": server_ms, "cpu": psutil.cpu_percent()}
