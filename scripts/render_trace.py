"""Render a sign trace over its crops so a tracer can check it.

usage: render_trace.py <sign_dir> [trace file, default trace.json]
Reads <sign_dir>/trace.json and writes <sign_dir>/check.png:
  [photo + trace] [relief + trace] [trace alone] side by side.

trace.json format (crop pixel coordinates, see meta.json):
{
  "strokes": [ {"d": [[x,y],[x,y],...], "w": 6, "closed": false, "conf": "clear|faint|restored"} ],
  "notes": "..."
}
Each stroke is a polyline along the CENTRE of a carved groove; w = groove width in crop px.
"""
import json
import sys

import cv2
import numpy as np

d = sys.argv[1].rstrip("/") + "/"
meta = json.load(open(d + "meta.json"))
name = sys.argv[2] if len(sys.argv) > 2 else "trace.json"
tr = json.load(open(d + name))
ph = cv2.cvtColor(cv2.imread(d + "photo.png", 0), cv2.COLOR_GRAY2BGR)
rl = cv2.cvtColor(cv2.imread(d + "relief.png", 0), cv2.COLOR_GRAY2BGR)
h, w = ph.shape[:2]
alone = np.full((h, w, 3), 245, np.uint8)
COL = {"clear": (0, 200, 255), "faint": (255, 190, 0), "restored": (200, 120, 255)}


def draw(img, alpha):
    ov = img.copy()
    for s in tr.get("strokes", []):
        pts = np.array(s["d"], np.float32).reshape(-1, 2)
        if len(pts) < 2:
            continue
        c = COL.get(s.get("conf", "clear"), (0, 200, 255))
        cv2.polylines(ov, [np.round(pts).astype(np.int32)], bool(s.get("closed")), c,
                      max(1, int(round(s.get("w", 5)))), cv2.LINE_AA)
    return cv2.addWeighted(ov, alpha, img, 1 - alpha, 0)


a = draw(ph, 0.55)
b = draw(rl, 0.55)
for s in tr.get("strokes", []):
    pts = np.round(np.array(s["d"], np.float32).reshape(-1, 2)).astype(np.int32)
    if len(pts) >= 2:
        cv2.polylines(alone, [pts], bool(s.get("closed")), (30, 30, 30), max(1, int(round(s.get("w", 5)))), cv2.LINE_AA)
sb = meta["sign_box"]
for im in (a, b, alone):
    cv2.rectangle(im, (int(sb[0]), int(sb[1])), (int(sb[2]), int(sb[3])), (0, 255, 0), 1)
gap = np.full((h, 8, 3), 255, np.uint8)
out = d + ("check.png" if name == "trace.json" else "check_" + name.replace("trace_", "").replace(".json", "") + ".png")
cv2.imwrite(out, np.hstack([a, gap, b, gap, alone]))
print("wrote", out, f"({len(tr.get('strokes', []))} strokes)")
