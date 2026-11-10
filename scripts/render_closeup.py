"""Render a trace over the close-up crop.  usage: render_closeup.py <sign_dir> [trace file]
Writes <sign_dir>/check_closeup.png: [closeup] [closeup + trace] [photo + trace], at 2x for small crops."""
import json
import sys

import cv2
import numpy as np

d = sys.argv[1].rstrip("/") + "/"
name = sys.argv[2] if len(sys.argv) > 2 else "trace.json"
cu = cv2.imread(d + "closeup.png")
ph = cv2.cvtColor(cv2.imread(d + "photo.png", 0), cv2.COLOR_GRAY2BGR)
try:
    strokes = json.load(open(d + name)).get("strokes", [])
except FileNotFoundError:
    strokes = []
COL = {"clear": (255, 255, 0), "faint": (0, 200, 255), "restored": (255, 0, 255)}
f = 2 if max(cu.shape[:2]) <= 700 else 1


def draw(im):
    im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    for i, s in enumerate(strokes):
        p = (np.array(s["d"], np.float32).reshape(-1, 2) * f).astype(np.int32)
        if len(p) < 2:
            continue
        cv2.polylines(im, [p], bool(s.get("closed")), COL.get(s.get("conf"), (255, 255, 255)), 1, cv2.LINE_AA)
        cv2.putText(im, str(i), tuple(int(v) for v in p[0] + [3, -3]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    return im


plain = cv2.resize(cu, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
cv2.imwrite(d + "check_closeup.png", np.hstack([plain, draw(cu.copy()), draw(ph.copy())]))
print("wrote", d + "check_closeup.png")
