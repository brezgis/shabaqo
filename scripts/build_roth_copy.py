"""Rothöhler's 2005 plate (raw/refs/rothoehler2005/tafel1-000.jpg) drawn onto the photo, for the viewer's
"Rothöhler 2005" overlay: each plate region (work/roth_columns.json) is warped into FULL px with the same
per-region mapping as the kits (scripts/roth_map.py, incl. the roth_align drift corrections), the ruled
lines are left out, and the ink is vectorised like Breasted's copy in build_data.py.

usage: python3 scripts/build_roth_copy.py [out.json]     default web/data/roth_copy.json (only this file is written)
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import roth_map as rm

P = rm.P
OUT = sys.argv[1] if len(sys.argv) > 1 else P + "web/data/roth_copy.json"
W, H, HALF = 11448, 7452, np.diag([0.5, 0.5, 1.0])
acc = np.zeros((H // 2, W // 2), np.uint8)
n = 0
for r in rm.regions:
    if "T" not in r:
        continue
    m = np.zeros_like(rm._signs)
    cv2.fillPoly(m, [r["quad"].astype(np.int32)], 255)
    ink = cv2.bitwise_and(rm._signs, m)
    acc = np.maximum(acc, cv2.warpPerspective(ink, HALF @ r["T"], (W // 2, H // 2), flags=cv2.INTER_LINEAR))
    n += 1
cs, _ = cv2.findContours((acc > 90).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
polys = [[round(float(v), 1) for v in (cv2.approxPolyDP(c, 0.7, True)[:, 0, :] * 2.0).ravel()] for c in cs if len(c) >= 4]
tmp = OUT + ".tmp"
json.dump({"source": "Rothöhler 2005, Tafel 1", "regions": n, "polys": polys}, open(tmp, "w"), separators=(",", ":"))
os.replace(tmp, OUT)
print(n, "regions,", len(polys), "polygons,", sum(len(p) for p in polys) // 2, "points ->", OUT,
      f"({os.path.getsize(OUT) / 1e6:.1f} MB)")
cv2.imwrite(P + "work/scratch/roth_copy_check.jpg", cv2.resize(acc, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA))
