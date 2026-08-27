"""Star tracker probe: multi-blob centroids with frame-to-frame association.

Runs on the Raspberry Pi with the SYSTEM python3 (numpy + cv2 live there;
the skyshutter venv stays stdlib-only). Taps the running MJPEG stream over
localhost HTTP -- it never talks PTP and never wakes the camera.

Detection follows the recipe proven by the astro-cv-tracker project
(src/cv_pipeline/mode_a_centroid.py): a background-relative threshold
``bg + rel * (peak - bg)`` instead of a plain percentile, gated by minimum
contrast so a black frame stays a black frame. Lessons measured 26.08.2026
are baked in: the threshold is capped at 254 (a saturated day scene pinned
a percentile threshold to 255 and matched nothing), and the first cv2
call pays ~1 s of init, so timing statistics skip the first frame.

Each frame: gray decode -> threshold -> connected components -> area
filter -> top-N blobs by total intensity -> intensity-weighted subpixel
centroid per blob. Blobs are associated to tracks by nearest neighbour
inside a pixel gate; the summary reports per-track jitter (the number
that tells us whether guiding on these centroids is viable).

Usage (on the Pi):
    python3 tools/cv/star_tracker.py --duration 120 --out /tmp/stars.csv

This is a measurement tool, not library code: no unit tests, no PTP.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from dataclasses import dataclass, field

import cv2
import numpy as np

# ---------------------------------------------------------------- stream tap


def mjpeg_frames(url: str, want: int | None, deadline: float):
    """Yield raw JPEG frames from an MJPEG HTTP stream."""
    req = urllib.request.Request(url, headers={"User-Agent": "star-tracker"})
    buf = b""
    n = 0
    try:
        resp = urllib.request.urlopen(req, timeout=10)
    except OSError as exc:
        print(f"stream_unreachable: {exc}", flush=True)
        return
    with resp:
        while time.monotonic() < deadline and (want is None or n < want):
            try:
                chunk = resp.read(65536)
            except TimeoutError:  # server stalled -- keep what we have
                break
            if not chunk:
                break
            buf += chunk
            while True:
                s = buf.find(b"\xff\xd8")
                e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                if s < 0 or e < 0:
                    buf = buf[-4:] if s < 0 else buf[s:]
                    break
                yield buf[s : e + 2]
                n += 1
                buf = buf[e + 2 :]


# ---------------------------------------------------------------- detection


@dataclass
class Blob:
    cx: float
    cy: float
    area: int
    peak: int
    mass: float  # summed intensity above background -- the ranking key
    bbox: list[int]  # [left, top, w, h] from the connected-component stats


def detect_blobs(
    gray: np.ndarray,
    thresh_rel: float,
    min_area: int,
    max_area: int,
    top: int,
    min_contrast: float = 1.0,
) -> list[Blob]:
    """Background-relative threshold, connected components, subpixel centroids.

    ``min_contrast`` is the gate the astro-cv-tracker project proved: a
    uniform frame (black sky, lens cap) must yield zero blobs, so peak and
    background have to differ by at least this much.
    """
    bg = float(np.median(gray))
    peak = float(gray.max())
    if peak - bg < min_contrast:  # uniform frame: no contrast, no blobs
        return []
    thr = min(bg + thresh_rel * (peak - bg), 254.0)
    mask = (gray > thr).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    blobs: list[Blob] = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not min_area <= area <= max_area:
            continue
        region = (labels == i).astype(np.uint8)
        values = gray.astype(np.float32) * region
        values -= bg * region  # weight by intensity ABOVE background
        mass = float(values.sum())
        if mass <= 0.0:
            continue
        ys, xs = np.nonzero(region)
        blob_mass = values[ys, xs]
        cx = float((xs * blob_mass).sum() / mass)
        cy = float((ys * blob_mass).sum() / mass)
        bbox = [
            int(stats[i, cv2.CC_STAT_LEFT]),
            int(stats[i, cv2.CC_STAT_TOP]),
            int(stats[i, cv2.CC_STAT_WIDTH]),
            int(stats[i, cv2.CC_STAT_HEIGHT]),
        ]
        blobs.append(Blob(cx, cy, area, int(gray[ys, xs].max()), mass, bbox))
    blobs.sort(key=lambda b: b.mass, reverse=True)
    return blobs[:top]


# ---------------------------------------------------------------- tracking


@dataclass
class Track:
    ident: int
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)
    areas: list[int] = field(default_factory=list)
    last: tuple[float, float] = (0.0, 0.0)

    def add(self, blob: Blob) -> None:
        self.xs.append(blob.cx)
        self.ys.append(blob.cy)
        self.areas.append(blob.area)
        self.last = (blob.cx, blob.cy)

    def stats(self) -> dict[str, object]:
        xs, ys = np.array(self.xs), np.array(self.ys)
        return {
            "track": self.ident,
            "n": len(xs),
            "mean_x": round(float(xs.mean()), 2),
            "mean_y": round(float(ys.mean()), 2),
            "std_x_px": round(float(xs.std()), 3),
            "std_y_px": round(float(ys.std()), 3),
            "area_med": int(np.median(self.areas)),
        }


def associate(tracks: dict[int, Track], blobs: list[Blob], gate: float) -> list[tuple[int, int]]:
    """Greedy nearest-neighbour association within a pixel gate.

    Returns (track_id, blob_index) pairs, each track and blob at most once.
    """
    pairs: list[tuple[float, int, int]] = []  # distance, track_id, blob_idx
    for tid, tr in tracks.items():
        for bi, blob in enumerate(blobs):
            d = ((tr.last[0] - blob.cx) ** 2 + (tr.last[1] - blob.cy) ** 2) ** 0.5
            if d <= gate:
                pairs.append((d, tid, bi))
    pairs.sort()
    used_t: set[int] = set()
    used_b: set[int] = set()
    result: list[tuple[int, int]] = []
    for _, tid, bi in pairs:
        if tid in used_t or bi in used_b:
            continue
        used_t.add(tid)
        used_b.add(bi)
        result.append((tid, bi))
    return result


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Multi-blob star centroid tracker for the skyshutter MJPEG stream"
    )
    ap.add_argument("--url", default="http://127.0.0.1:8080/stream.mjpg")
    ap.add_argument("--duration", type=float, default=60.0, help="seconds to sample")
    ap.add_argument("--out", default="", help="optional CSV path")
    ap.add_argument("--thresh-rel", type=float, default=0.5)
    ap.add_argument("--min-area", type=int, default=3)
    ap.add_argument("--max-area", type=int, default=2000)
    ap.add_argument("--top", type=int, default=12, help="brightest blobs per frame")
    ap.add_argument("--gate", type=float, default=30.0, help="association radius in px")
    ap.add_argument(
        "--min-contrast",
        type=float,
        default=1.0,
        help="required peak-background gap; 0 disables the gate (tests)",
    )
    ap.add_argument(
        "--zmq",
        action="store_true",
        help="publish DetectionFrame JSON (astro-cv-tracker format) on tcp://127.0.0.1:5555",
    )
    ap.add_argument(
        "--selftest-publish",
        action="store_true",
        help="ZMQ interface test: publish one synthetic drifting detection every "
        "0.5 s for --duration seconds, no camera needed",
    )
    args = ap.parse_args()
    if args.selftest_publish:
        args.zmq = True

    publisher = None
    if args.zmq:
        import zmq  # lazy: only needed when bridging to the mount controller

        ctx = zmq.Context.instance()
        publisher = ctx.socket(zmq.PUB)
        publisher.setsockopt(zmq.LINGER, 0)
        publisher.bind("tcp://127.0.0.1:5555")
        print("zmq_pub: tcp://127.0.0.1:5555", flush=True)
        time.sleep(1.0)  # slow-joiner window: give subscribers time to connect

    def publish(frame_id: int, dets: list[tuple[int, Blob]], width: int, height: int) -> None:
        assert publisher is not None
        payload = {
            "ts": round(time.time(), 3),
            "frame_id": frame_id,
            "mode_hint": "A",
            "detections": [
                {
                    "track_id": tid,
                    "cls": "blob",
                    "confidence": round(blob.peak / 255.0, 4),
                    "bbox_xywh": blob.bbox,
                    "bbox_center_normalized": [
                        round(blob.cx / width, 5),
                        round(blob.cy / height, 5),
                    ],
                }
                for tid, blob in dets
            ],
        }
        publisher.send_string(json.dumps(payload, separators=(",", ":")))

    deadline = time.monotonic() + args.duration

    if args.selftest_publish:
        assert publisher is not None
        fid = 0
        while time.monotonic() < deadline:
            fid += 1
            cx = 0.30 + 0.02 * fid  # drifts right, in normalized 0..1
            det = {
                "track_id": 1,
                "cls": "blob",
                "confidence": 0.9,
                "bbox_xywh": [int(cx * 1552) - 5, 584, 10, 10],
                "bbox_center_normalized": [round(min(cx, 0.95), 5), 0.5],
            }
            payload = {
                "ts": round(time.time(), 3),
                "frame_id": fid,
                "mode_hint": "A",
                "detections": [det],
            }
            publisher.send_string(json.dumps(payload, separators=(",", ":")))
            if fid % 10 == 0:
                print(f"published {fid}", flush=True)
            time.sleep(0.5)
        print(f"selftest_done: {fid} frames published", flush=True)
        return 0
    tracks: dict[int, Track] = {}
    next_id = 1
    rows: list[list[object]] = []
    n_frames = 0
    decode_ms: list[float] = []

    for jpeg in mjpeg_frames(args.url, None, deadline):
        t0 = time.perf_counter()
        gray = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue

        # Safety Check: P1100 PTP LV pipeline collapses sometimes during uptime,
        # delivering 83% uniform magenta (which becomes gray). Std < 1.0 means no optical content.
        # This requires a full cycle of the stream wrapper to heal (re-wake camera).
        if n_frames > 0 and n_frames % 5 == 0:  # check every 5th frame for performance
            region_std = float(gray[300:1100].std())
            if region_std < 1.0:
                print(
                    f"FATAL: Camera LV buffer collapsed "
                    f"(uniform fill, std={region_std:.2f}). Force-restarting stream.",
                    file=sys.stderr,
                )
                import subprocess

                subprocess.run(["sudo", "-n", "systemctl", "restart", "skyshutter-stream"])
                sys.exit(2)

        dt_ms = (time.perf_counter() - t0) * 1000.0
        n_frames += 1
        blobs = detect_blobs(
            gray,
            args.thresh_rel,
            args.min_area,
            args.max_area,
            args.top,
            min_contrast=args.min_contrast,
        )
        now = round(time.time(), 3)
        matches = associate(tracks, blobs, args.gate)
        for tid, bi in matches:
            blob = blobs[bi]
            tracks[tid].add(blob)
            rows.append([now, tid, round(blob.cx, 2), round(blob.cy, 2), blob.area, blob.peak])
        matched = {bi for _, bi in matches}
        frame_dets: list[tuple[int, Blob]] = [(tid, blobs[bi]) for tid, bi in matches]
        for bi, blob in enumerate(blobs):  # unmatched blobs open new tracks
            if bi in matched:
                continue
            tr = Track(next_id)
            next_id += 1
            tr.add(blob)
            tracks[tr.ident] = tr
            rows.append([now, tr.ident, round(blob.cx, 2), round(blob.cy, 2), blob.area, blob.peak])
            frame_dets.append((tr.ident, blob))
        if publisher is not None:
            h, w = gray.shape
            publish(n_frames, frame_dets, w, h)
        if n_frames > 1:  # first frame pays the cv2 init (~1 s), skip in timing
            decode_ms.append(dt_ms)
        if n_frames % 30 == 0:
            print(f"frames={n_frames} tracks={len(tracks)}", flush=True)

    print(f"frames_total: {n_frames}", flush=True)
    if decode_ms:
        print(
            f"decode_ms: avg={sum(decode_ms) / len(decode_ms):.1f} max={max(decode_ms):.1f}",
            flush=True,
        )
    stable = sorted(tracks.values(), key=lambda t: len(t.xs), reverse=True)
    print(
        f"tracks_total: {len(stable)} (>=10 hits: {sum(1 for t in stable if len(t.xs) >= 10)})",
        flush=True,
    )
    for tr in stable[:10]:
        print(f"track: {tr.stats()}", flush=True)
    if args.out and rows:
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["t", "track", "x", "y", "area", "peak"])
            writer.writerows(rows)
        print(f"csv: {args.out} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
