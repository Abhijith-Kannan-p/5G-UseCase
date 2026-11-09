"""Laptop controller: for every frame decide LOCAL (small model on this laptop) or MEC (send JPEG over 5G).

Examples
  python controller.py --source images --server http://VM_IP:8000 --dash http://VM_IP:8501
  python controller.py --source video.mp4 ...        (video file, loops)
  python controller.py --source 0 ...                (laptop webcam)
  CAM_URL=rtsp://user:pass@ip:554/path python controller.py --source "$CAM_URL" ...
  python controller.py --calibrate ...               (measure local vs MEC latency, then exit)
  python controller.py --mode local|mec ...          (fixed baselines for the comparison graph)
"""
import argparse
import csv
import glob
import os
import queue
import threading
import time
from statistics import median

import cv2
import requests


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="images", help="folder of images | video file | webcam index | rtsp url")
    p.add_argument("--server", default=os.environ.get("MEC_URL", "http://127.0.0.1:8000"))
    p.add_argument("--dash", default=os.environ.get("DASH_URL", "http://127.0.0.1:8501"))
    p.add_argument("--mode", choices=["auto", "local", "mec"], default="auto")
    p.add_argument("--fps", type=float, default=4.0, help="frames processed per second")
    p.add_argument("--width", type=int, default=640, help="frame width sent/processed (task size knob)")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality for upload")
    p.add_argument("--local-model", default="resnet18", help="resnet18 | resnet50 | mobilenet_v3_small | fake")
    p.add_argument("--threads", type=int, default=1, help="CPU threads for local model (low = weaker device)")
    p.add_argument("--probe-every", type=int, default=8, help="in LOCAL state, test MEC every N frames")
    p.add_argument("--margin", type=float, default=0.10, help="hysteresis margin for switching")
    p.add_argument("--timeout", type=float, default=2.0, help="seconds before an offload counts as failed")
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--max-frames", type=int, default=0)
    p.add_argument("--log", default="log.csv")
    return p.parse_args()


# ---------------------------------------------------------------- frame sources
class Source:
    def __init__(self, src):
        self.folder = os.path.isdir(src)
        if self.folder:
            exts = ("*.jpg", "*.jpeg", "*.png")
            self.files = sorted(f for e in exts for f in glob.glob(os.path.join(src, e)))
            if not self.files:
                raise SystemExit(f"No images in {src}")
            self.i = 0
            return
        self.live = src.isdigit() or src.startswith("rtsp")
        self.src = int(src) if src.isdigit() else src
        self.cap = cv2.VideoCapture(self.src)
        if not self.cap.isOpened():
            raise SystemExit(f"Cannot open source: {src.split('@')[-1]}")
        self.latest = None
        self.lock = threading.Lock()
        if self.live:  # keep only the newest frame so RTSP buffering never adds lag
            threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            ok, fr = self.cap.read()
            if not ok:
                time.sleep(0.5)
                self.cap.release()
                self.cap = cv2.VideoCapture(self.src)
                continue
            with self.lock:
                self.latest = fr

    def read(self):
        if self.folder:
            fr = cv2.imread(self.files[self.i % len(self.files)])
            self.i += 1
            return fr
        if self.live:
            while True:
                with self.lock:
                    fr = self.latest
                if fr is not None:
                    return fr.copy()
                time.sleep(0.05)
        ok, fr = self.cap.read()
        if not ok:  # video file: loop
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, fr = self.cap.read()
            if not ok:
                raise SystemExit("Video file has no readable frames")
        return fr


# ---------------------------------------------------------------- local model
class LocalModel:
    def __init__(self, name, threads):
        self.name = name
        if name == "fake":
            return
        import torch
        import torchvision as tv

        torch.set_num_threads(threads)
        self.torch = torch
        table = {
            "resnet18": (tv.models.resnet18, tv.models.ResNet18_Weights.DEFAULT),
            "resnet50": (tv.models.resnet50, tv.models.ResNet50_Weights.DEFAULT),
            "mobilenet_v3_small": (tv.models.mobilenet_v3_small, tv.models.MobileNet_V3_Small_Weights.DEFAULT),
        }
        ctor, w = table[name]
        self.model = ctor(weights=w).eval()
        self.prep = w.transforms()
        self.labels = w.meta["categories"]
        self.predict(__import__("numpy").zeros((240, 320, 3), "uint8"))  # warm-up

    def predict(self, bgr):
        if self.name == "fake":
            time.sleep(0.09)
            return "fake", 0.5
        from PIL import Image

        img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        with self.torch.no_grad():
            probs = self.model(self.prep(img).unsqueeze(0)).softmax(1)[0]
            conf, idx = probs.max(0)
        return self.labels[int(idx)], float(conf)


# ---------------------------------------------------------------- helpers
def resize(fr, width):
    h, w = fr.shape[:2]
    return fr if w <= width else cv2.resize(fr, (width, int(h * width / w)))


def ping(server, timeout=1.0):
    t = time.perf_counter()
    try:
        r = requests.get(f"{server}/ping", timeout=timeout)
        return (time.perf_counter() - t) * 1000, r.json().get("cpu")
    except requests.RequestException:
        return None, None


def offload(server, jpg, timeout):
    t = time.perf_counter()
    r = requests.post(f"{server}/classify", files={"file": ("f.jpg", jpg, "image/jpeg")}, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    return (time.perf_counter() - t) * 1000, d


class Reporter(threading.Thread):
    """Sends per-frame records to the dashboard in the background; retries if the link is congested."""

    def __init__(self, url):
        super().__init__(daemon=True)
        self.url, self.q = url, queue.Queue(maxsize=2000)

    def run(self):
        while True:
            rec = self.q.get()
            while True:
                try:
                    requests.post(f"{self.url}/report", json=rec, timeout=3)
                    break
                except requests.RequestException:
                    time.sleep(1)


def ema(old, new, a=0.3):
    return new if old is None else (1 - a) * old + a * new


# ---------------------------------------------------------------- main
def main():
    a = parse()
    local = LocalModel(a.local_model, a.threads)
    src = Source(a.source)

    if a.calibrate:
        L, M = [], []
        for i in range(20):
            fr = resize(src.read(), a.width)
            t = time.perf_counter(); local.predict(fr); L.append((time.perf_counter() - t) * 1000)
            jpg = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, a.quality])[1].tobytes()
            M.append(offload(a.server, jpg, a.timeout)[0])
        rtt, cpu = ping(a.server)
        print(f"local  median: {median(L[2:]):.0f} ms  ({a.local_model}, {a.threads} thread(s))")
        print(f"offload median: {median(M[2:]):.0f} ms  (RTT {rtt:.0f} ms, jpeg {len(jpg)/1024:.0f} KB)")
        print("MEC should win on a clean network and lose under congestion. If it never wins, "
              "use --threads 1, a bigger --local-model, or a larger --width.")
        return

    rep = Reporter(a.dash)
    rep.start()
    f = open(a.log, "w", newline="")
    w = csv.writer(f)
    w.writerow(["ts", "frame", "mode", "path", "latency_ms", "rtt_ms", "server_ms", "label", "conf", "bytes", "ema_local", "ema_mec"])

    ema_local = ema_mec = None
    path = "LOCAL"
    n = 0
    period = 1.0 / a.fps
    print("running; Ctrl+C to stop")
    try:
        while a.max_frames == 0 or n < a.max_frames:
            t_start = time.perf_counter()
            fr = resize(src.read(), a.width)
            jpg = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, a.quality])[1].tobytes()
            rtt, cpu = ping(a.server)

            # ---- decide
            note = ""
            if a.mode == "local":
                want = "LOCAL"
            elif a.mode == "mec":
                want = "MEC"
            elif ema_local is None:
                want, note = "LOCAL", "warm-up: measuring local"
            elif ema_mec is None:
                want, note = "MEC", "warm-up: measuring MEC"
            else:
                m = a.margin
                if path == "MEC":
                    want = "LOCAL" if ema_mec > ema_local * (1 + m) else "MEC"
                else:
                    want = "MEC" if ema_mec < ema_local * (1 - m) else "LOCAL"
                note = f"est MEC {ema_mec:.0f} ms vs local {ema_local:.0f} ms"
                if want == "LOCAL" and n % a.probe_every == 0:
                    want, note = "MEC", note + " (probe)"
            if want == "MEC" and rtt is None and a.mode == "auto":
                want, note = "LOCAL", "MEC unreachable"

            # ---- execute
            label = conf = server_ms = None
            used = want
            if want == "MEC":
                try:
                    lat, d = offload(a.server, jpg, a.timeout)
                    label, conf, server_ms = d["label"], d["conf"], d["server_ms"]
                    ema_mec = ema(ema_mec, lat)
                except requests.RequestException:
                    t0 = time.perf_counter()
                    label, conf = local.predict(fr)
                    lat = a.timeout * 1000 + (time.perf_counter() - t0) * 1000
                    ema_mec = max(ema_mec or 0, a.timeout * 1000)
                    used, note = "LOCAL", "offload timed out, fell back to local"
            else:
                t0 = time.perf_counter()
                label, conf = local.predict(fr)
                lat = (time.perf_counter() - t0) * 1000
                ema_local = ema(ema_local, lat)
            path = used

            rec = {"ts": time.time(), "frame": n, "mode": a.mode, "path": used, "latency_ms": lat, "rtt_ms": rtt,
                   "server_ms": server_ms, "cpu": cpu, "label": label, "conf": conf,
                   "bytes": len(jpg) if used == "MEC" else 0, "note": note}
            rep.q.put(rec)
            w.writerow([f"{rec['ts']:.3f}", n, a.mode, used, f"{lat:.1f}", f"{rtt:.1f}" if rtt else "",
                        f"{server_ms:.1f}" if server_ms else "", label, f"{conf:.3f}",
                        rec["bytes"], f"{ema_local:.1f}" if ema_local else "", f"{ema_mec:.1f}" if ema_mec else ""])
            f.flush()
            print(f"#{n:04d} {used:5s} {lat:6.0f} ms  rtt={rtt if rtt is None else round(rtt)}  {label}  {note}")
            n += 1
            time.sleep(max(0, period - (time.perf_counter() - t_start)))
    except KeyboardInterrupt:
        pass
    f.close()


if __name__ == "__main__":
    main()
