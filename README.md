# 5G Adaptive Computation Offloading demo

Laptop (camera/video frames + small local model + controller) decides per frame:
LOCAL (run on laptop) or MEC (send JPEG over 5G to ResNet50 on the lab VM).
The dashboard container on the VM shows the decisions, latency and RTT live.

```
camera/video --> laptop controller --(5G, JPEG)--> VM: inference :8000
                        |                                  
                        +--(5G, tiny JSON report)--> VM: dashboard :8501
```

## A. Do now, on your laptop (needs internet)
```bash
cd client && pip install -r requirements.txt
mkdir images   # put ~20 jpgs here (any photos: people, objects, vehicles)
docker compose up --build          # in the project root; first build downloads weights
python controller.py --source images --local-model resnet18 --threads 1
```
Open http://localhost:8501 . You should see decisions and latency.

## B. Ship to the lab VM (VM probably has no internet)
```bash
docker compose build
docker save offload-inference offload-dashboard | gzip > images.tar.gz
scp images.tar.gz docker-compose.yml USER@VM_IP:~
ssh USER@VM_IP
docker load < images.tar.gz
docker compose up -d --no-build
```
If `docker compose` is missing on the VM, run the two containers with
`docker run -d -p 8000:8000 offload-inference` and `docker run -d -p 8501:8501 offload-dashboard`.

## C. Lab checklist, in this order (stop and ask the staff at the first failure)
1. Lab Wi-Fi: can you reach the VM? `ping VM_IP`, `ssh USER@VM_IP`.
2. Docker works on the VM: `docker --version`, `docker ps`.
3. Containers up: from the laptop, `curl http://VM_IP:8000/ping` and open `http://VM_IP:8501`.
4. **Turn Wi-Fi off. Tether to the 5G phone.** Repeat step 3. If it fails, the 5G side cannot reach the VM: ask the lab.
5. Calibrate: `python controller.py --calibrate --server http://VM_IP:8000 --source images`
   MEC should be clearly faster than local on a clean network. If not: `--threads 1`, bigger `--local-model resnet50`, or larger `--width 1024`.
6. Find the congestion level: run iperf2 UDP from another phone, uplink to the lab's iperf VM, raising `-b` (20m, 40m, 80m, 150m ...)
   until your MEC latency/RTT visibly rises. (Their slides: server `iperf -s -u -i 1 -p 6001`, phone `iperf -c IP -l 1400 -i 1 -p 6001 -b 40m -t 999999 -u`.)
7. Camera (optional): test the RTSP URL in VLC from the tethered laptop first; then `CAM_URL=rtsp://... python controller.py --source "$CAM_URL"`.
   Keep a video file as backup: `--source clip.mp4`.

## D. Demo run
```bash
python controller.py --source images --server http://VM_IP:8000 --dash http://VM_IP:8501 --local-model resnet18 --threads 1
```
1. Clean network: path = MEC (green).
2. Start iperf congestion from the second phone: RTT rises, path flips to LOCAL (orange), latency stays bounded.
3. Stop iperf: path returns to MEC. Bigger `--width` simulates a heavier task.
Occasional single green dots while in LOCAL are deliberate probes (every `--probe-every` frames) that re-test the MEC.

## E. Results for the report (baselines)
Run the same ~2 minutes with the same congestion pattern three times and compare the logs:
`--mode local --log local.csv`, `--mode mec --log mec.csv`, `--mode auto --log auto.csv`.
Compare mean and p95 of latency_ms. Show the dashboard screenshot next to Niral controller throughput.

## Flags worth knowing
`--source` folder | video | webcam index | rtsp url, `--fps`, `--width`, `--mode auto|local|mec`,
`--margin` (switch hysteresis), `--timeout` (offload counted failed), `--log`.
Server env: `FAKE=1` skips PyTorch for wiring tests. Do not put camera passwords in files; use `CAM_URL`.
