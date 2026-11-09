"""Find carvings claimed by two signs: strokes of different sids in the same
unit that lie on top of each other (in FULL px, from web/data/stone.json).

usage: dupes.py [min_overlap_px=40]
"""
import json
import sys
from collections import defaultdict

import cv2
import numpy as np

MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 40
D = json.load(open("/home/anna/projects/shabaka-stone/web/data/stone.json"))
by = defaultdict(list)
for s in D["signs"]:
    if s.get("strokes"):
        by[s["unit"]].append(s)


def raster(s, org, shape):
    m = np.zeros(shape, np.uint8)
    for k in s["strokes"]:
        p = (np.array(k["d"], np.float32).reshape(-1, 2) - org).astype(np.int32)
        cv2.polylines(m, [p], bool(k.get("z")), 1, 5)
    return m


hits = []
for u, ss in by.items():
    for i in range(len(ss)):
        for j in range(i + 1, len(ss)):
            a, b = ss[i]["box"], ss[j]["box"]
            if a[2] < b[0] - 5 or b[2] < a[0] - 5 or a[3] < b[1] - 5 or b[3] < a[1] - 5:
                continue
            x0, y0 = min(a[0], b[0]) - 10, min(a[1], b[1]) - 10
            x1, y1 = max(a[2], b[2]) + 10, max(a[3], b[3]) + 10
            shape = (int(y1 - y0) + 1, int(x1 - x0) + 1)
            ov = int((raster(ss[i], [x0, y0], shape) & raster(ss[j], [x0, y0], shape)).sum())
            if ov >= MIN:
                hits.append((ov, ss[i]["sid"], ss[j]["sid"]))
for ov, a, b in sorted(hits, reverse=True):
    print(f"{a:>10} {b:>10}  overlap {ov}px")
print(len(hits), "pairs")
