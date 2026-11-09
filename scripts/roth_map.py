"""Coordinates between Rothöhler's plate (raw/refs/rothoehler2005/tafel1-000.jpg) and the photo (FULL px),
using the per-region alignment from his printed column labels (work/roth_columns.json; same method as
scripts/roth_kit.py: first/last signs of each region land on ours, one scale per region).

As a module:  from roth_map import regions, plate_to_full, full_to_plate
CLI:
  python3 scripts/roth_map.py p2f <unit> <px> <py>      plate px -> FULL px (through that unit's region)
  python3 scripts/roth_map.py f2p <unit> <fx> <fy>      FULL px -> plate px
  python3 scripts/roth_map.py traces <unit>             existing traces of that unit: sid, gardiner label,
                                                        trace bbox (FULL), centre in plate px, roth_agrees
  python3 scripts/roth_map.py regions <unit>            that unit's plate regions (label, part, plate box)
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
_plate = cv2.imread(P + "raw/refs/rothoehler2005/tafel1-000.jpg", 0)
_ink = (_plate < 160).astype(np.uint8)
_n, _lab, _st, _ = cv2.connectedComponentsWithStats(_ink, connectivity=8)
_keep = np.zeros(_n, bool); _keep[1:] = _st[1:, cv2.CC_STAT_AREA] >= 40
_ink = np.where(_keep[_lab], 255, 0).astype(np.uint8)
_rules = cv2.morphologyEx(_ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))) | \
         cv2.morphologyEx(_ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (200, 1)))
_signs = np.where(cv2.dilate(_rules, np.ones((5, 5), np.uint8)) > 0, 0, _ink)

def _align_corr(unit, i):
    """Per-region drift correction fitted from traces (scripts/roth_align.py); identity if none or ROTH_RAW."""
    f = P + "work/roth_align.json"
    if os.environ.get("ROTH_RAW") or not os.path.exists(f):
        return np.eye(3)
    c = json.load(open(f)).get(f"{unit}#{i}")
    if not c:
        return np.eye(3)
    a, b, cc, d = c["a"], c["b"], c["c"], c["d"]
    if c["axis"] == "x":
        return np.array([[1 + b, 0, a], [d, 1, cc], [0, 0, 1]])
    return np.array([[1, b, a], [0, 1 + d, cc], [0, 0, 1]])


regions = []
for unit, entries in json.load(open(P + "work/roth_columns.json")).items():
    for ri, e in enumerate(entries):
        q = np.float32(e.get("quad") or [[e["plate"][0], e["plate"][1]], [e["plate"][2], e["plate"][1]],
                                         [e["plate"][2], e["plate"][3]], [e["plate"][0], e["plate"][3]]])
        w = int(round(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))))
        h = int(round(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))))
        R = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
        st = cv2.warpPerspective(_signs, R, (w, h), flags=cv2.INTER_NEAREST)
        ys, xs = np.nonzero(st[2:-2, 2:-2])
        pb = e.get("photo_box")
        r = {"unit": unit, "e": e, "quad": q}
        if len(xs) >= 20 and pb:
            ix0, iy0, ix1, iy1 = xs.min() + 2, ys.min() + 2, xs.max() + 2, ys.max() + 2
            if e.get("axis") == "x":
                s = (pb[2] - pb[0]) / max(1, ix1 - ix0)
                tx, ty = pb[0] - ix0 * s, (pb[1] + pb[3]) / 2 - (iy0 + iy1) / 2 * s
            else:
                s = (pb[3] - pb[1]) / max(1, iy1 - iy0)
                tx, ty = (pb[0] + pb[2]) / 2 - (ix0 + ix1) / 2 * s, pb[1] - iy0 * s
            if not 0.84 <= s <= 2.7:  # tiny ink extent (e.g. 28's one-sign region): typical plate scale, centred
                s = 1.68
                tx, ty = (pb[0] + pb[2]) / 2 - (ix0 + ix1) / 2 * s, (pb[1] + pb[3]) / 2 - (iy0 + iy1) / 2 * s
            r["T"] = _align_corr(unit, ri) @ np.array([[s, 0, tx], [0, s, ty], [0, 0, 1]]) @ R
            r["Ti"] = np.linalg.inv(r["T"])
        regions.append(r)


def _pt(M, x, y):
    v = M @ np.array([x, y, 1.0]); return float(v[0] / v[2]), float(v[1] / v[2])


def plate_to_full(unit, x, y):
    """Plate px -> FULL px through the region of `unit` that contains the point (or the nearest one)."""
    best = None
    for r in regions:
        if r["unit"] != unit or "T" not in r:
            continue
        inside = cv2.pointPolygonTest(r["quad"].reshape(-1, 1, 2), (float(x), float(y)), True)
        if best is None or inside > best[0]:
            best = (inside, r)
    return _pt(best[1]["T"], x, y) if best else None


def region_index(unit, x, y):
    """Index (within the unit, as in work/roth_align.json "<unit>#<i>") of the region plate_to_full uses."""
    best = None
    for i, r in enumerate(r for r in regions if r["unit"] == unit):
        if "T" not in r:
            continue
        inside = cv2.pointPolygonTest(r["quad"].reshape(-1, 1, 2), (float(x), float(y)), True)
        if best is None or inside > best[0]:
            best = (inside, i)
    return best[1] if best else None


def full_to_plate(unit, x, y):
    """FULL px -> plate px through the region of `unit` whose photo range contains y (x for lines)."""
    best = None
    for r in regions:
        if r["unit"] != unit or "T" not in r:
            continue
        lo, hi = r["e"]["photo_range"]
        v = x if r["e"].get("axis") == "x" else y
        d = 0 if lo <= v <= hi else min(abs(v - lo), abs(v - hi))
        if best is None or d < best[0]:
            best = (d, r)
    return _pt(best[1]["Ti"], x, y) if best else None


def unit_traces(unit):
    out = []
    for f in sorted(glob.glob(P + "work/signs/*/trace.json")):
        d = os.path.dirname(f)
        try:
            m = json.load(open(d + "/meta.json")); tr = json.load(open(f))
        except Exception:
            continue
        if m.get("unit") != unit:
            continue
        (ox, oy), sc = m["crop"]["origin_full"], m["crop"]["scale"]
        pts = [np.array(s["d"], float) / sc + [ox, oy] for s in tr.get("strokes", []) if s.get("d")]
        if pts:
            a = np.vstack(pts); bb = [a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()]
        elif tr.get("box"):
            b = tr["box"]; bb = [b[0] / sc + ox, b[1] / sc + oy, b[2] / sc + ox, b[3] / sc + oy]
        else:
            bb = None
        c = full_to_plate(unit, (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2) if bb else None
        out.append({"sid": m["sid"], "label": m.get("gardiner"), "empty": not pts,
                    "bbox_full": [round(v) for v in bb] if bb else None,
                    "centre_plate": [round(v) for v in c] if c else None,
                    "roth_agrees": tr.get("roth_agrees"), "identity_ok": tr.get("identity_ok", True)})
    key = lambda t: [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in t["sid"].replace("-", ".").split(".")]
    return sorted(out, key=key)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd in ("p2f", "f2p"):
        u, x, y = sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
        print((plate_to_full if cmd == "p2f" else full_to_plate)(u, x, y))
    elif cmd == "traces":
        for t in unit_traces(sys.argv[2]):
            print(json.dumps(t))
    elif cmd == "regions":
        for r in regions:
            if r["unit"] == sys.argv[2]:
                print(json.dumps({k: r["e"].get(k) for k in ("label", "part", "plate", "photo_range", "axis")}))
