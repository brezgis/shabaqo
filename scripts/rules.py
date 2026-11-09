"""Trace the stone's carved column rules, guided by the placed signs.

Each column's centre line is fitted (robust quadratic x(y)) through the
centres of its placed signs, which follows the photo's slight lens bow. The
rule between two neighbouring columns is the midline of their fits. Every
120-px stretch of that midline is then snapped sideways (+-14 FULL px) to the
strongest vertical-groove evidence and kept only where a cut is clearly
visible there (independent photos included). Horizontal frame lines are found
by a row search. Output: work/rules.json, [x0, y0, x1, y1] FULL-px segments.
"""
import json
import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
D = json.load(open(P + "web/data/stone.json"))
rel = cv2.imread(P + "work/relief_full.png", 0).astype(np.float32)
nat = cv2.resize(cv2.imread(P + "work/mp/relief_signed3.png", 0).astype(np.float32), (rel.shape[1], rel.shape[0]))


def ev_v(img):
    z = cv2.GaussianBlur((img - 128) / 40, (0, 0), 2.0)
    return np.abs(cv2.Sobel(z, cv2.CV_32F, 1, 0, ksize=3))


EV = cv2.GaussianBlur(ev_v(rel) * 0.6 + ev_v(nat) * 0.4, (0, 0), 1.5)

# column centre fits
cols = {}
for u in D["units"]:
    if u["id"] in ("lines1-2", "48-52"):
        continue
    pts = np.array([[(s["box"][0] + s["box"][2]) / 2, (s["box"][1] + s["box"][3]) / 2]
                    for s in D["signs"] if s["unit"] == u["id"] and s.get("box") and s["status"] != "not_visible"])
    if len(pts) < 6:
        continue
    k = np.polyfit(pts[:, 1], pts[:, 0], 2)
    for _ in range(3):  # trim outliers (wide signs, mis-assigned boxes)
        r = np.abs(np.polyval(k, pts[:, 1]) - pts[:, 0]); m = r < max(12, 2.5 * np.median(r))
        k = np.polyfit(pts[m, 1], pts[m, 0], 2)
    cols[int(u["id"])] = (k, pts[:, 1].min(), pts[:, 1].max())

Y0, Y1, SEG = 1250, 5850, 120
rules, kept, total = [], 0, 0


def col_x(c, y):
    return np.polyval(cols[c][0], y)


for c in sorted(cols):
    if c + 1 not in cols:
        continue
    for y in np.arange(Y0, Y1, SEG):
        ya, yb = y, min(y + SEG, Y1)
        xa = (col_x(c, ya) + col_x(c + 1, ya)) / 2; xb = (col_x(c, yb) + col_x(c + 1, yb)) / 2
        ys = np.arange(ya, yb, 2, dtype=np.float32)
        best, bo = -1, 0
        for o in range(-14, 15, 2):
            xs = (xa + (xb - xa) * (ys - ya) / (yb - ya) + o).astype(np.float32)
            v = np.percentile(cv2.remap(EV, xs.reshape(1, -1), ys.reshape(1, -1), cv2.INTER_LINEAR), 50)
            if v > best:
                best, bo = v, o
        xs = (xa + (xb - xa) * (ys - ya) / (yb - ya) + bo).astype(np.float32)
        off = np.mean([np.percentile(cv2.remap(EV, (xs + d).reshape(1, -1), ys.reshape(1, -1), cv2.INTER_LINEAR), 50)
                       for d in (-12, -8, 8, 12)])
        total += 1
        if best > 1.35 * off:
            kept += 1
            rules.append([round(float(xa + bo), 1), float(ya), round(float(xb + bo), 1), float(yb)])

# merge touching stretches of the same rule
rules.sort(key=lambda r: (round(r[0] / 40), r[1]))
merged = []
for r in rules:
    if merged and abs(merged[-1][2] - r[0]) < 6 and abs(merged[-1][3] - r[1]) < 1:
        merged[-1][2], merged[-1][3] = r[2], r[3]
    else:
        merged.append(list(r))
json.dump(merged, open(P + "work/rules.json", "w"))
print(len(cols), "columns fitted;", kept, "of", total, "rule stretches visible ->", len(merged), "segments")
