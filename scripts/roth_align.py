"""Fit per-region corrections to the plate -> photo alignment of Rothöhler's Tafel, from existing traces.

Why: each region of his plate is straightened and then only scaled + shifted onto the photo box
(roth_map.py / roth_kit.py), so a column that slants or bows on the stone drifts along its length: in
cols 55-64 by up to ±130 FULL px, end to end (pilot batch roth-57a, 2026-11-08).

Model, per region (axis = the region's reading axis, t = position along it, FULL px):
    dx = a + b*t,   dy = c + d*t        (FULL px correction added after the raw transform)
fitted robustly to anchor pairs: his sign's plate-box centre mapped raw  ->  the centre of the trace of the
project sign matched to it (work/roth_inventory, work/signlist_roth.json). Slopes are fitted only when
anchors are >= 5 and span >= 30% of the region; with 2-4 anchors only the offset; fewer: no correction.

writes work/roth_align.json {"<unit>#<region index>": {axis, a, b, c, d, n, rms_before, rms_after}}
usage: python3 scripts/roth_align.py [-v]
"""
import json
import os
import sys

os.environ["ROTH_RAW"] = "1"  # fit against the uncorrected transforms
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import roth_map as RM  # noqa: E402

P = RM.P
L = json.load(open(P + "work/signlist_roth.json"))
verbose = "-v" in sys.argv


def region_of(unit, x, y):
    best = None
    for i, r in enumerate(x for x in RM.regions if x["unit"] == unit):
        if "T" not in r:
            continue
        inside = cv2.pointPolygonTest(r["quad"].reshape(-1, 1, 2), (float(x), float(y)), True)
        if best is None or inside > best[0]:
            best = (inside, i, r)
    return best


def robust_line(t, v, slope):
    """least squares v = p + q*t (q = 0 if not slope), dropping outliers (> max(25, 3 * robust sigma))."""
    keep = np.ones(len(t), bool)
    for _ in range(4):
        if slope:
            q, p = np.polyfit(t[keep], v[keep], 1)
        else:
            p, q = float(np.median(v[keep])), 0.0
        res = v - (p + q * t)
        sig = 1.4826 * np.median(np.abs(res[keep] - np.median(res[keep])))
        nk = np.abs(res) <= max(25.0, 3 * sig)
        if nk.sum() < (5 if slope else 2) or (nk == keep).all():
            break
        keep = nk
    return float(p), float(q), keep


out = {}
for unit, es in L["units"].items():
    f = P + f"work/roth_inventory/{unit}.json"
    if not os.path.exists(f):
        continue
    inv = {s.get("sid"): s for s in json.load(open(f))["signs"] if s.get("sid")}
    anchors = {}  # region index -> list of (raw mapped x, y, trace x, y)
    for e in es:
        s = inv.get(e["alias"]) if e["alias"] else None
        pb = e.get("plate_box") or (s or {}).get("plate_box")
        if e["status"] != "traced" or not pb or e.get("parts"):
            continue
        px, py = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
        hit = region_of(unit, px, py)
        if not hit:
            continue
        mx, my = RM._pt(hit[2]["T"], px, py)
        b = e["box_full"]
        anchors.setdefault(hit[1], []).append((mx, my, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
    regs = [r for r in RM.regions if r["unit"] == unit]
    for i, A in sorted(anchors.items()):
        r = regs[i]; axis = r["e"].get("axis", "y")
        A = np.array(A)
        t = A[:, 0] if axis == "x" else A[:, 1]
        dx, dy = A[:, 2] - A[:, 0], A[:, 3] - A[:, 1]
        lo, hi = r["e"].get("photo_range") or [t.min(), t.max()]
        slope = len(A) >= 5 and (t.max() - t.min()) >= 0.3 * max(1.0, hi - lo)
        if len(A) < 2:
            continue
        a, b, kx = robust_line(t, dx, slope)
        c, d, ky = robust_line(t, dy, slope)
        before = float(np.sqrt(np.mean(dx ** 2 + dy ** 2)))
        rx, ry = dx - (a + b * t), dy - (c + d * t)
        k = kx & ky
        after = float(np.sqrt(np.mean(rx[k] ** 2 + ry[k] ** 2)))
        out[f"{unit}#{i}"] = {"axis": axis, "a": round(a, 2), "b": round(b, 5), "c": round(c, 2), "d": round(d, 5),
                              "n": int(len(A)), "inliers": int(k.sum()), "slope": bool(slope),
                              "rms_before": round(before, 1), "rms_after_inliers": round(after, 1),
                              "part": r["e"].get("part", "")}
        if verbose:
            print(f"{unit:9}#{i} n={len(A):3} in={k.sum():3} slope={slope!s:5} rms {before:6.1f} -> {after:5.1f}  {r['e'].get('part', '')[:40]}")

json.dump(out, open(P + "work/roth_align.json.tmp", "w"), indent=1)
os.replace(P + "work/roth_align.json.tmp", P + "work/roth_align.json")  # atomic: kits may be building
print(f"{len(out)} region corrections -> work/roth_align.json")
