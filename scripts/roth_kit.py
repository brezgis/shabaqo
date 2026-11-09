"""Rothöhler's facsimile (Diss. Heidelberg 2005, Tafel) as a reference in every sign kit, aligned
column by column from his own printed column labels (work/roth_columns.json, see roth_columns.md).

His Tafel is a schematic over the stone's outline, not a geometric copy, so no single warp fits it.
For each region of his plate mapped to a project unit (a quad along his ruling lines + the photo box
of the project signs it contains), the quad is straightened, the extent of his ink inside it is found,
and that extent is mapped onto the photo box: his first and last signs land on ours, the rest scales
linearly. Each region therefore has its own plate -> FULL-photo transform.

writes, for each kit work/signs/<sid>/:
  roth.png   kit photo with Rothöhler's ink in red: every region overlapping the crop, each through its
             own transform (so neighbouring columns are aligned too)
and for each unit:
  work/signs/roth_col<unit>.png   his drawing of that unit: each region straightened, labelled, stacked
                                  (old strips are backed up to work/scratch/roth_strips_v1/ once)

usage: nice python3 scripts/roth_kit.py [--sids sid ...]
"""
import glob
import json
import os
import shutil
import sys

import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
plate = cv2.imread(P + "raw/refs/rothoehler2005/tafel1-000.jpg", 0)
# drop scanner speckle: keep only ink blobs of real size
_ink = (plate < 160).astype(np.uint8)
_n, _lab, _st, _ = cv2.connectedComponentsWithStats(_ink, connectivity=8)
_keep = np.zeros(_n, bool); _keep[1:] = _st[1:, cv2.CC_STAT_AREA] >= 40
plate = np.where(_keep[_lab], plate, 255).astype(np.uint8)
ink_all = (plate < 160).astype(np.uint8) * 255
rules = cv2.morphologyEx(ink_all, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))) | \
        cv2.morphologyEx(ink_all, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (200, 1)))
signs_only = np.where(cv2.dilate(rules, np.ones((5, 5), np.uint8)) > 0, 0, ink_all)

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


M = json.load(open(P + "work/roth_columns.json"))
regions = []
for unit, entries in M.items():
    for ri, e in enumerate(entries):
        q = np.float32(e.get("quad") or [[e["plate"][0], e["plate"][1]], [e["plate"][2], e["plate"][1]],
                                         [e["plate"][2], e["plate"][3]], [e["plate"][0], e["plate"][3]]])
        w = int(round(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))))
        h = int(round(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))))
        R = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))  # plate -> straight
        straight_signs = cv2.warpPerspective(signs_only, R, (w, h), flags=cv2.INTER_NEAREST)
        ys, xs = np.nonzero(straight_signs[2:-2, 2:-2])
        pb = e.get("photo_box")
        entry = {"unit": unit, "e": e, "quad": q, "R": R, "w": w, "h": h}
        if len(xs) >= 20 and pb:
            ix0, iy0, ix1, iy1 = xs.min() + 2, ys.min() + 2, xs.max() + 2, ys.max() + 2
            # one scale, from the along-axis extent (first to last sign is reliable); across the column the
            # photo box can be inflated by side-by-side signs or misplaced 1901 boxes, so only centre there
            if e.get("axis") == "x":
                s = (pb[2] - pb[0]) / max(1, ix1 - ix0)
                tx, ty = pb[0] - ix0 * s, (pb[1] + pb[3]) / 2 - (iy0 + iy1) / 2 * s
            else:
                s = (pb[3] - pb[1]) / max(1, iy1 - iy0)
                tx, ty = (pb[0] + pb[2]) / 2 - (ix0 + ix1) / 2 * s, pb[1] - iy0 * s
            if not 0.84 <= s <= 2.7:  # tiny ink extent (e.g. 28's one-sign region): typical plate scale, centred
                s = 1.68
                tx, ty = (pb[0] + pb[2]) / 2 - (ix0 + ix1) / 2 * s, (pb[1] + pb[3]) / 2 - (iy0 + iy1) / 2 * s
            A = np.array([[s, 0, tx], [0, s, ty], [0, 0, 1]])                               # straight -> FULL
            entry["T"] = _align_corr(unit, ri) @ A @ R                                                              # plate -> FULL
            # photo-side footprint of the whole quad (for overlap tests)
            fp = cv2.perspectiveTransform(q.reshape(-1, 1, 2), entry["T"]).reshape(-1, 2)
            entry["fp"] = [fp[:, 0].min(), fp[:, 1].min(), fp[:, 0].max(), fp[:, 1].max()]
        regions.append(entry)

args = sys.argv[1:]
sids = [s for s in args[args.index("--sids") + 1:] if not s.startswith("--")] if "--sids" in args else None

n = 0
for meta_path in sorted(glob.glob(P + "work/signs/*/meta.json")):
    d = os.path.dirname(meta_path) + "/"
    sid = os.path.basename(d.rstrip("/"))
    if sids and sid not in sids:
        continue
    m = json.load(open(meta_path))
    ph = cv2.imread(d + "photo.png")
    if ph is None:
        continue
    (ox, oy), sc = m["crop"]["origin_full"], m["crop"]["scale"]
    Hc, Wc = ph.shape[:2]
    cx0, cy0, cx1, cy1 = ox, oy, ox + Wc / sc, oy + Hc / sc
    Ccrop = np.array([[sc, 0, -ox * sc], [0, sc, -oy * sc], [0, 0, 1]])
    ink = np.zeros((Hc, Wc), np.float32)
    for r in regions:
        if "T" not in r:
            continue
        fx0, fy0, fx1, fy1 = r["fp"]
        if fx1 < cx0 or fx0 > cx1 or fy1 < cy0 or fy0 > cy1:
            continue
        mask = np.zeros_like(plate); cv2.fillPoly(mask, [np.round(r["quad"]).astype(np.int32)], 255)
        src = np.where(mask > 0, 255 - plate, 0).astype(np.uint8)
        wv = cv2.warpPerspective(src, Ccrop @ r["T"], (Wc, Hc), flags=cv2.INTER_LINEAR)
        ink = np.maximum(ink, wv.astype(np.float32))
    a = np.clip((ink - 55) / 120, 0, 1)[..., None]
    red = np.zeros_like(ph); red[..., 2] = 235; red[..., 1] = 40; red[..., 0] = 40
    out = (ph.astype(np.float32) * (1 - 0.75 * a) + red * 0.75 * a).astype(np.uint8)
    cv2.putText(out, "Rothoehler 2005, aligned per column (first/last signs)", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 235), 2)
    cv2.imwrite(d + "roth.png", out)
    n += 1
print(f"roth.png written for {n} kits")

if sids is None:
    bk = P + "work/scratch/roth_strips_v1/"
    if not os.path.isdir(bk):
        os.makedirs(bk)
        for f in glob.glob(P + "work/signs/roth_col*.png"):
            shutil.copy2(f, bk)
    made = 0
    for unit in M:
        parts = []
        for r in regions:
            if r["unit"] != unit:
                continue
            st = cv2.warpPerspective(plate, r["R"], (r["w"], r["h"]), flags=cv2.INTER_LINEAR, borderValue=255)
            if r["e"].get("axis") == "x" and st.shape[1] > 3000:   # very long line: keep it readable
                k = 3000 / st.shape[1]; st = cv2.resize(st, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            lab = f"EB {unit}: {r['e'].get('part', '')} [{r['e'].get('label', '')}]"[:90]
            head = np.full((34, max(st.shape[1], 10)), 255, np.uint8)
            cv2.putText(head, lab, (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
            parts.append(head); parts.append(np.pad(st, ((0, 0), (0, head.shape[1] - st.shape[1])), constant_values=255))
        if not parts:
            continue
        W = max(p.shape[1] for p in parts)
        parts = [np.pad(p, ((0, 0), (0, W - p.shape[1])), constant_values=255) for p in parts]
        cv2.imwrite(P + f"work/signs/roth_col{unit}.png", np.vstack(parts)); made += 1
    print(f"column strips written: {made} (old strips backed up in work/scratch/roth_strips_v1/)")
