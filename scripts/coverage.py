"""Coverage check: carved grooves that no traced stroke accounts for.

Per-sign tracing misses cuts that fall between sign boxes (each tracer assumes
the neighbour owns them). This maps groove-centre evidence over the whole
inscribed area (main relief AND native relief must agree), removes everything
within reach of an existing traced stroke, a column rule, or the millstone
damage, and groups what is left into candidate regions. Only units whose signs
are mostly traced are checked, so "uncovered" means "missed", not "not yet done".

usage: coverage.py [min_traced_fraction=0.8]
Output: work/coverage.json  [{unit, box_full, area, near_sid}], work/coverage_debug.jpg
"""
import json
import sys

import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
MINFRAC = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
K = 0.5  # work in the A2 frame
D = json.load(open(P + "web/data/stone.json"))


def evidence(img):
    z = (img.astype(np.float32) - 128) / 40
    out = np.zeros_like(z)
    for sg in (1.0, 1.8):
        zs = cv2.GaussianBlur(z, (0, 0), sg)
        dy = cv2.Sobel(zs, cv2.CV_32F, 0, 1, ksize=3) * sg
        dxx = cv2.Sobel(zs, cv2.CV_32F, 2, 0, ksize=3) * sg * sg
        out = np.maximum(out, np.maximum(dy, 0) + 0.35 * np.abs(dxx))
    return out


rel = cv2.resize(cv2.imread(P + "work/relief_full.png", 0), None, fx=K, fy=K, interpolation=cv2.INTER_AREA)
nat = cv2.imread(P + "work/mp/relief_signed3.png", 0)
E, En = evidence(rel), evidence(nat)
H, W = E.shape


def strong(e):
    # local threshold: well above the neighbourhood's typical texture
    mu = cv2.GaussianBlur(e, (0, 0), 25)
    sd = np.sqrt(cv2.GaussianBlur((e - mu) ** 2, (0, 0), 25)) + 1e-3
    return (e - mu) / sd > 2.2


cut = strong(E) & cv2.dilate(strong(En).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)

# what is already accounted for
acc = np.zeros((H, W), np.uint8)
for s in D["signs"]:
    for k in s.get("strokes") or []:
        p = (np.array(k["d"], np.float32).reshape(-1, 2) * K).astype(np.int32)
        cv2.polylines(acc, [p], bool(k.get("z")), 255, max(3, int(k["w"] * K) + 6))
for a, b, c, d in D.get("rules", []):
    cv2.line(acc, (int(a * K), int(b * K)), (int(c * K), int(d * K)), 255, 9)
mill = np.zeros((H, W), np.uint8)
for poly in D.get("mill", []):
    cv2.fillPoly(mill, [(np.array(poly, np.float32).reshape(-1, 2) * K).astype(np.int32)], 255)
mill = cv2.dilate(mill, np.ones((15, 15), np.uint8))

# only units that are (mostly) traced, and only inside their own extent
done = np.zeros((H, W), np.uint8)
units_ok = []
for u in D["units"]:
    ss = [s for s in D["signs"] if s["unit"] == u["id"] and s.get("box")]
    if not ss:
        continue
    frac = np.mean([bool(s.get("strokes")) or "strokes" in s or s.get("trace_notes") is not None for s in ss])
    if frac < MINFRAC:
        continue
    units_ok.append(u["id"])
    for s in ss:
        b = [int(v * K) for v in s["box"]]
        cv2.rectangle(done, (b[0] - 6, b[1] - 6), (b[2] + 6, b[3] + 6), 255, -1)
done = cv2.morphologyEx(done, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

miss = cut & (done > 0) & (acc == 0) & (mill == 0)
miss = cv2.morphologyEx(miss.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
miss = cv2.morphologyEx(miss, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
n, lab, st, cen = cv2.connectedComponentsWithStats(miss)
centres = [((s["box"][0] + s["box"][2]) / 2 * K, (s["box"][1] + s["box"][3]) / 2 * K, s) for s in D["signs"] if s.get("box")]
out = []
for i in range(1, n):
    x, y, w, h, a = st[i]
    if a < 30 or max(w, h) < 10:   # a real stroke fragment, not a speck
        continue
    cx, cy = cen[i]
    near = min(centres, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)[2]
    out.append({"unit": near["unit"], "near_sid": near["sid"], "area": int(a),
                "box_full": [round(x / K), round(y / K), round((x + w) / K), round((y + h) / K)]})
out.sort(key=lambda r: -r["area"])
json.dump(out, open(P + "work/coverage.json", "w"), indent=0)

dbg = cv2.cvtColor(rel, cv2.COLOR_GRAY2BGR)
dbg[acc > 0] = (dbg[acc > 0] * 0.6 + np.array([0, 90, 0])).astype(np.uint8)
dbg[miss > 0] = (0, 0, 255)
cv2.imwrite(P + "work/coverage_debug.jpg", dbg)
print("units checked:", units_ok)
print(len(out), "uncovered cut regions; by unit:",
      {u: sum(1 for r in out if r["unit"] == u) for u in sorted({r["unit"] for r in out})})
