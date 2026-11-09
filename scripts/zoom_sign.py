"""zoom.py <sign_dir> x0 y0 x1 y1 [scale] [out]
Crops relief | photo | native for region, scales, draws grid every 10px (labels every 50),
overlays trace.json centre lines (1px, coloured) if present. Writes <sign_dir>/zoom.png (per sign, safe with parallel tracers)."""
import json, os, sys
import cv2
import numpy as np

NOTRACE = "--notrace" in sys.argv
sys.argv = [a for a in sys.argv if a != "--notrace"]   # flag may appear anywhere
d = sys.argv[1].rstrip("/") + "/"
x0, y0, x1, y1 = map(int, sys.argv[2:6])
sc = float(sys.argv[6]) if len(sys.argv) > 6 else 2.0
sid = os.path.basename(d.rstrip("/"))
out = sys.argv[7] if len(sys.argv) > 7 else os.path.join(d, "zoom.png")
tr = None
if os.path.exists(d + "trace.json") and not NOTRACE:
    tr = json.load(open(d + "trace.json"))
panels = []
for nm in ("relief.png", "photo.png", "native.png"):
    im = cv2.imread(d + nm, 0)
    if im is None:
        continue
    H, W = im.shape
    c = np.full((y1 - y0, x1 - x0), 128, np.uint8)
    ax0, ay0, ax1, ay1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    c[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] = im[ay0:ay1, ax0:ax1]
    c = cv2.resize(c, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
    c = cv2.cvtColor(c, cv2.COLOR_GRAY2BGR)
    for gx in range((x0 // 10 + 1) * 10, x1, 10):
        X = int((gx - x0) * sc)
        col = (0, 160, 255) if gx % 50 == 0 else (0, 90, 140)
        cv2.line(c, (X, 0), (X, 6 if gx % 50 else 14), col, 1)
        if gx % 50 == 0:
            cv2.putText(c, str(gx), (X + 2, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for gy in range((y0 // 10 + 1) * 10, y1, 10):
        Y = int((gy - y0) * sc)
        col = (0, 160, 255) if gy % 50 == 0 else (0, 90, 140)
        cv2.line(c, (0, Y), (6 if gy % 50 else 14, Y), col, 1)
        if gy % 50 == 0:
            cv2.putText(c, str(gy), (16, Y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    if tr and "--notrace" not in sys.argv:
        for i, s in enumerate(tr.get("strokes", [])):
            pts = (np.array(s["d"], np.float32).reshape(-1, 2) - [x0, y0]) * sc
            cv2.polylines(c, [np.round(pts).astype(np.int32)], bool(s.get("closed")),
                          [(0, 0, 255), (0, 255, 0), (255, 0, 255), (255, 255, 0), (0, 255, 255)][i % 5], 1, cv2.LINE_AA)
    cv2.putText(c, nm[:-4], (c.shape[1] - 70, c.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    panels.append(c)
gap = np.full((panels[0].shape[0], 6, 3), 255, np.uint8)
row = [panels[0]]
for p in panels[1:]:
    row += [gap, p]
cv2.imwrite(out, np.hstack(row))
print(out)
