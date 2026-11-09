"""Per-unit alignment of Rothöhler's facsimile to the photo, anchored on our own traces.

The global homography (work/H_roth_to_photo.json) is off by up to several hundred FULL px in places
(his drawing is not geometrically uniform), sometimes by a whole column. Here, for each unit (column or
horizontal line) and for up to BANDS bands along its length, the unit's traced strokes (trace.json,
converted to FULL px) are rasterised and matched by normalised cross-correlation against Rothöhler's
ink (warped by the global H, his long ruling lines removed) over a wide search window. The best shift is
the correction to apply after H for that band.

writes work/roth_unit_shift.json:
  {unit: {"axis": "y"|"x", "bands": [{"c": centre along axis (FULL px), "dx", "dy", "cc", "z", "n_strokes"}]}}
Bands with too few traces, or a weak / non-distinct peak, are left out; roth_kit.py interpolates
between good bands and falls back to the unit's median (or the neighbours') where a unit has none.

usage: nice python3 scripts/roth_register_units.py
"""
import glob
import json
import os

import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
K = 0.25                 # work at quarter resolution (FULL px * K)
SEARCH = 700             # FULL px search radius
BANDS = 3
MIN_STROKES = 6

H = np.array(json.load(open(P + "work/H_roth_to_photo.json"))["H"])
plate = cv2.imread(P + "raw/refs/rothoehler2005/tafel1-000.jpg", 0)
ink = (plate < 160).astype(np.uint8) * 255
n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 40
ink = np.where(keep[lab], 255, 0).astype(np.uint8)
lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 250))) | \
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (250, 1)))
ink = cv2.subtract(ink, cv2.dilate(lines, np.ones((7, 7), np.uint8)))      # signs only, no rules

D = json.load(open(P + "web/data/stone.json"))
W, Hh = D["image"]["w"], D["image"]["h"]
S = np.diag([K, K, 1.0])
roth = cv2.warpPerspective(ink, S @ H, (int(W * K), int(Hh * K)), flags=cv2.INTER_AREA)
roth = cv2.GaussianBlur(roth.astype(np.float32), (0, 0), 2.0)

# traced strokes per unit, in FULL px
strokes = {}
for f in glob.glob(P + "work/signs/*/trace.json"):
    d = os.path.dirname(f)
    sid = os.path.basename(d)
    try:
        tr = json.load(open(f)); m = json.load(open(d + "/meta.json"))
    except Exception:
        continue
    (ox, oy), sc = m["crop"]["origin_full"], m["crop"]["scale"]
    for s in tr.get("strokes", []):
        pts = np.array(s["d"], float)
        if len(pts) >= 2:
            strokes.setdefault(m["unit"], []).append(pts / sc + [ox, oy])

out = {}
for u in D["units"]:
    uid, b = u["id"], u.get("bounds")
    if not b or uid not in strokes:
        continue
    x0, y0, x1, y1 = b
    axis = "x" if (x1 - x0) > (y1 - y0) else "y"
    lo, hi = (x0, x1) if axis == "x" else (y0, y1)
    bands = []
    for i in range(BANDS):
        a, z = lo + (hi - lo) * i / BANDS, lo + (hi - lo) * (i + 1) / BANDS
        bx0, by0, bx1, by1 = (a, y0, z, y1) if axis == "x" else (x0, a, x1, z)
        sel = [p for p in strokes[uid] if bx0 <= p[:, 0].mean() <= bx1 and by0 <= p[:, 1].mean() <= by1]
        if len(sel) < MIN_STROKES:
            continue
        pad = 60
        tx0, ty0 = int((bx0 - pad) * K), int((by0 - pad) * K)
        tw, th = int((bx1 - bx0 + 2 * pad) * K), int((by1 - by0 + 2 * pad) * K)
        tpl = np.zeros((th, tw), np.uint8)
        for p in sel:
            q = np.round((p * K) - [tx0, ty0]).astype(np.int32)
            cv2.polylines(tpl, [q], False, 255, 2)
        tpl = cv2.GaussianBlur(tpl.astype(np.float32), (0, 0), 2.0)
        r = int(SEARCH * K)
        sx0, sy0 = max(0, tx0 - r), max(0, ty0 - r)
        sx1, sy1 = min(roth.shape[1], tx0 + tw + r), min(roth.shape[0], ty0 + th + r)
        win = roth[sy0:sy1, sx0:sx1]
        if win.shape[0] < th or win.shape[1] < tw or win.max() == 0:
            continue
        res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
        _, cc, _, (px, py) = cv2.minMaxLoc(res)
        zsc = (cc - res.mean()) / (res.std() + 1e-6)
        # Rothöhler's ink for this band sits at (template origin + shift): correction = -shift
        shx, shy = (sx0 + px - tx0) / K, (sy0 + py - ty0) / K
        bands.append({"c": round((a + z) / 2, 1), "dx": round(-shx, 1), "dy": round(-shy, 1),
                      "cc": round(float(cc), 3), "z": round(float(zsc), 2), "n_strokes": len(sel)})
    good = [bd for bd in bands if bd["cc"] >= 0.15 and bd["z"] >= 4.0]
    out[uid] = {"axis": axis, "bands": good, "rejected": [bd for bd in bands if bd not in good]}

json.dump(out, open(P + "work/roth_unit_shift.json", "w"), indent=1)
for uid, v in out.items():
    s = "  ".join(f"{bd['c']:.0f}:({bd['dx']:+.0f},{bd['dy']:+.0f}) cc{bd['cc']:.2f} z{bd['z']:.0f}" for bd in v["bands"])
    r = len(v["rejected"])
    print(f"{uid:>9} {v['axis']}  {s}{'   rejected ' + str(r) if r else ''}")
