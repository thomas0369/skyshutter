#!/bin/bash
# Waechter bis zur Dunkelheit: alle 5 min Frame-Sonde (median, Riesenblob?).
# Bei median < 100 ohne gesaettigten Riesenblob: ein 120-s-Kalibriellauf
# des star_tracker mit CSV, danach Selbstbeendigung.
set -u
REPORT=/tmp/darkness_report.txt
DIR="$(cd "$(dirname "$0")/.." && pwd)"
: > "$REPORT"
echo "watcher start $(date +%H:%M:%S)" >> "$REPORT"

while true; do
    RESULT=$(python3 - << 'EOF'
import urllib.request, cv2, numpy as np
req = urllib.request.Request("http://127.0.0.1:8080/stream.mjpg", headers={"User-Agent": "darkwatch"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        buf = b""; jpg = None
        while True:
            chunk = r.read(65536)
            if not chunk: break
            buf += chunk
            e = buf.find(b"\xff\xd9"); s = buf.find(b"\xff\xd8")
            if s >= 0 and e > s:
                jpg = buf[s:e+2]; break
    if not jpg:
        print("NOFRAME 0 0"); raise SystemExit
    g = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if g is None:
        print("NOFRAME 0 0"); raise SystemExit
    med = float(np.median(g))
    mask = (g > 254).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    big = int(stats[1:, 4].max()) if n > 1 else 0
    print(f"MEDIAN {med:.0f} {big}")
except SystemExit:
    pass
except Exception as exc:
    print(f"FAIL 0 0")
EOF
)
    TS=$(date +%H:%M:%S)
    echo "$TS $RESULT" >> "$REPORT"
    case "$RESULT" in
        MEDIAN*)
            MED=$(echo "$RESULT" | awk "{print \$2}")
            BIG=$(echo "$RESULT" | awk "{print \$3}")
            # dunkel genug UND kein gesaettigter Vollframe-Blob?
            if [ "$(echo "$MED" | awk '{print ($1 < 100) ? 1 : 0}')" = "1" ] && [ "$BIG" -lt 100000 ]; then
                echo "$TS DUNKEL -- starte Kalibriellauf" >> "$REPORT"
                python3 "$DIR/tools/cv/star_tracker.py" --duration 120 \
                    --out /tmp/stars.csv >> "$REPORT" 2>&1
                echo "$TS Kalibriellauf fertig (CSV: /tmp/stars.csv)" >> "$REPORT"
                exit 0
            fi
            ;;
    esac
    sleep 300
done
