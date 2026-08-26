"""CV probe: measure decode cost and brightest-blob centroid stability.

Runs on the Raspberry Pi against the local MJPEG stream (127.0.0.1:8080)
using the SYSTEM python3 (numpy + cv2 are installed there, not in the
stdlib-only skyshutter venv). Read-only: consumes frames, moves nothing.

Usage (on the Pi):  python3 /tmp/hw_cvprobe.py
Deploy:            scp -P 2222 tools/hw/hw_cvprobe.py thomas@192.168.1.143:/tmp/
"""

import time
import urllib.request

import cv2
import numpy as np


def emit(label: str, obj) -> None:
    print(f"{label}: {obj}", flush=True)


def main() -> None:
    req = urllib.request.Request(
        "http://127.0.0.1:8080/stream.mjpg", headers={"User-Agent": "cvprobe"}
    )
    frames: list[bytes] = []
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=10) as resp:
        buf = b""
        while len(frames) < 30 and time.time() - t0 < 45:
            chunk = resp.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                s = buf.find(b"\xff\xd8")
                e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                if s < 0 or e < 0:
                    buf = buf[-4:] if s < 0 else buf[s:]
                    break
                frames.append(buf[s : e + 2])
                buf = buf[e + 2 :]
    emit("frames_recv", (len(frames), round(time.time() - t0, 1)))

    cpu0 = time.process_time()
    dec_ms, cents, blobs, maxes = [], [], [], []
    img = None
    for f in frames:
        td = time.time()
        img = cv2.imdecode(np.frombuffer(f, np.uint8), cv2.IMREAD_GRAYSCALE)
        dec_ms.append(round((time.time() - td) * 1000, 1))
        if img is None:
            continue
        thr = max(180, int(np.percentile(img, 99.5)))
        mask = (img > thr).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        comps = [(stats[i, cv2.CC_STAT_AREA], i) for i in range(1, n)]
        if comps:
            area, idx = max(comps)
            m = cv2.moments((labels == idx).astype(np.uint8))
            cents.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))
            blobs.append((int(area), int(thr)))
        maxes.append(int(img.max()))
    cpu = time.process_time() - cpu0

    emit("decode_ms", {"avg": round(sum(dec_ms) / len(dec_ms), 1), "max": max(dec_ms)})
    emit("cpu_ms_per_frame", round(cpu * 1000 / max(1, len(frames)), 1))
    emit("blobs_top5", sorted(blobs, reverse=True)[:5])
    emit("max_brightness", maxes[:10])
    if len(cents) >= 10:
        arr = np.array(cents[5:])
        emit(
            "centroid",
            {
                "n": len(cents),
                "mean": [round(v, 2) for v in arr.mean(axis=0)],
                "std_px": [round(v, 3) for v in arr.std(axis=0)],
            },
        )
    emit("dims", img.shape if img is not None else None)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
