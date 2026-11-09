"""Per-sign tracing kits for the stroke-tracing agents.

usage: sign_kit.py <unit> [n_signs|all] [--from sid]          (original behaviour, v1 kits)
       sign_kit.py --sids <sid> [sid...] [--v2] [--retrace]    (selected signs)
       sign_kit.py <unit> all --v2                              (v2 kits for a whole unit)
       --seed: wide margin (150 FULL px) for seed signs whose position is still uncertain

For each sign writes work/signs/<sid>/:
  photo.png    the stone (main photo, CLAHE), crop around the sign box, upscaled
  relief.png   local relief of the main photo (upscaled source)
  native.png   relief from the non-upscaled photos (to rule out upscaling artefacts)
  grid.png     photo with a 10-px grid in crop coordinates (for reading coordinates)
  context.png  the column at lower zoom around the sign (v2: always regenerated)
  meta.json    sign identity, crop geometry, the sign's box and neighbours' boxes
All images share one coordinate system: crop px = (FULL px - origin) * scale.

v2 kits (touch-up, see STROKE_BRIEF.md "v2 kits"):
  - the green box is grown to at least ~85% of the typical size of this sign type
    (scripts/sign_boxes.py), because many boxes come from Breasted's clusters and are too small;
  - the crop margin scales with the sign (>= 60% of its typical size, >= 48 FULL px);
  - neighbours that are already traced are RED (their traced extent: do not trace into them);
    untraced neighbours are ORANGE DASHED (approximate positions from the old copy: the sign may
    extend into them, e.g. a bird's legs inside a box labelled '?');
  - --retrace: an existing trace.json is moved to trace_prev.json (converted into the new crop
    coordinates) and the old kit is backed up under work/scratch/kit_touchup/backup/<sid>/.
"""
import json
import os
import shutil
import sys

import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
OUT = P + "work/signs/"
BACKUP = P + "work/scratch/kit_touchup/backup/"
SCALE = 3.0      # FULL px -> crop px
PAD = 48         # FULL px of context around the box (boxes can be off by tens of px)
MAX_CROP = 1500  # crop px: keep images readable for the tracer (scale is lowered if needed)

_cache = {}


def layers():
    if not _cache:
        g = cv2.imread(P + "raw/commons_11448.jpg", 0)
        _cache["photo"] = g
        _cache["relief"] = cv2.imread(P + "work/relief_full.png", 0)
        n = cv2.imread(P + "work/mp/relief_signed3.png", 0)
        _cache["native"] = cv2.resize(n, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_CUBIC)
    return _cache


def crop(img, x0, y0, x1, y1, scale):
    H, W = img.shape[:2]
    c = np.zeros((y1 - y0, x1 - x0), img.dtype)  # zero-fill outside the photo
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    c[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
    return cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def dashed_rect(img, a, b, col, dash=8):
    (x0, y0), (x1, y1) = a, b
    for (p, q) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        L = int(np.hypot(q[0] - p[0], q[1] - p[1]))
        for t in range(0, L, dash * 2):
            u, v = t / max(L, 1), min(t + dash, L) / max(L, 1)
            cv2.line(img, (int(p[0] + (q[0] - p[0]) * u), int(p[1] + (q[1] - p[1]) * u)),
                     (int(p[0] + (q[0] - p[0]) * v), int(p[1] + (q[1] - p[1]) * v)), col, 1)


def traced_extent(sid):
    """FULL-px extent of an existing trace (from its kit), or None."""
    d = OUT + sid + "/"
    try:
        t = json.load(open(d + "trace.json")); m = json.load(open(d + "meta.json"))
    except (OSError, ValueError):
        return None
    pts = [p for s in t.get("strokes", []) for p in s.get("d", [])]
    if len(pts) < 2:
        return None
    (ox, oy), sc = m["crop"]["origin_full"], m["crop"]["scale"]
    a = np.array(pts, float)
    return [ox + a[:, 0].min() / sc, oy + a[:, 1].min() / sc, ox + a[:, 0].max() / sc, oy + a[:, 1].max() / sc]


def make(sign, unit_signs, signlist, v2=False, retrace=False, seed=False):
    L = layers()
    sid = sign["sid"]
    d = OUT + sid + "/"
    bx = list(sign["box"])
    pad, scale = PAD, SCALE
    prev = None
    if v2:
        import sign_boxes as B
        ext = traced_extent(sid)
        if ext:  # an existing trace is the best evidence of where the sign is; grow around it
            bx = [min(bx[0], ext[0]), min(bx[1], ext[1]), max(bx[2], ext[2]), max(bx[3], ext[3])]
        bx = B.expected_box(sid, bx)
        tw, th = B.typical(sid)
        pad = int(max(PAD, 0.6 * max(tw, th), 150 if seed else 0))  # seeds: box may be off by ~150 FULL px
        span = max(bx[2] - bx[0], bx[3] - bx[1]) + 2 * pad
        scale = min(SCALE, MAX_CROP / span)
    if retrace and os.path.exists(d + "trace.json"):
        bk = BACKUP + sid + "/"
        if not os.path.exists(bk):  # keep the FIRST original; never overwrite a backup
            shutil.copytree(d, bk)
        om = json.load(open(d + "meta.json")); ot = json.load(open(d + "trace.json"))
        prev = (om, ot)
        os.remove(d + "trace.json")
        for f in ("check.png", "codex_log.txt"):
            if os.path.exists(d + f):
                os.remove(d + f)
    elif os.path.exists(d + "trace_prev.json") and os.path.exists(d + "meta.json"):
        # kit rebuilt again before the re-trace happened: carry the earlier trace into the new crop
        prev = (json.load(open(d + "meta.json")), json.load(open(d + "trace_prev.json")))
    x0 = int(bx[0]) - pad; y0 = int(bx[1]) - pad
    x1 = int(bx[2]) + pad; y1 = int(bx[3]) + pad
    os.makedirs(d, exist_ok=True)
    ph = crop(L["photo"], x0, y0, x1, y1, scale)
    ph = cv2.createCLAHE(2.0, (4, 4)).apply(ph)
    cv2.imwrite(d + "photo.png", ph)
    cv2.imwrite(d + "relief.png", crop(L["relief"], x0, y0, x1, y1, scale))
    cv2.imwrite(d + "native.png", crop(L["native"], x0, y0, x1, y1, scale))
    gimg = cv2.cvtColor(ph, cv2.COLOR_GRAY2BGR)
    h, w = ph.shape
    over = gimg.copy()
    for x in range(0, w, 50):
        cv2.line(over, (x, 0), (x, h), (0, 170, 255), 1)
    for y in range(0, h, 50):
        cv2.line(over, (0, y), (w, y), (0, 170, 255), 1)
    gimg = cv2.addWeighted(over, 0.35, gimg, 0.65, 0)
    for x in range(0, w, 10):
        t = 9 if x % 50 == 0 else 4
        cv2.line(gimg, (x, 0), (x, t), (0, 255, 255), 1); cv2.line(gimg, (x, h - 1), (x, h - 1 - t), (0, 255, 255), 1)
    for y in range(0, h, 10):
        t = 9 if y % 50 == 0 else 4
        cv2.line(gimg, (0, y), (t, y), (0, 255, 255), 1); cv2.line(gimg, (w - 1, y), (w - 1 - t, y), (0, 255, 255), 1)
    for x in range(50, w, 50):
        cv2.putText(gimg, str(x), (x + 2, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    for y in range(50, h, 50):
        cv2.putText(gimg, str(y), (12, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    to_crop = lambda b: [round((b[0] - x0) * scale, 1), round((b[1] - y0) * scale, 1),
                         round((b[2] - x0) * scale, 1), round((b[3] - y0) * scale, 1)]
    sb = to_crop(bx)
    cv2.rectangle(gimg, (int(sb[0]), int(sb[1])), (int(sb[2]), int(sb[3])), (0, 255, 0), 1)
    neigh = []
    for o in unit_signs:
        if o["sid"] == sid or not o.get("box"):
            continue
        ob = o["box"]
        traced = bool(o.get("strokes"))
        if v2 and traced:
            ob = traced_extent(o["sid"]) or ob
        if ob[2] > x0 and ob[0] < x1 and ob[3] > y0 and ob[1] < y1:
            cb = to_crop(ob)
            neigh.append({"sid": o["sid"], "gardiner": o["gardiner"], "box": cb, "traced": traced})
            a, b = (int(cb[0]), int(cb[1])), (int(cb[2]), int(cb[3]))
            if v2 and not traced:
                dashed_rect(gimg, a, b, (0, 140, 255))
            else:
                cv2.rectangle(gimg, a, b, (0, 0, 255), 1)
            if v2:
                cv2.putText(gimg, f'{o.get("label") or o["sid"].split(".")[-1]}:{o["gardiner"]}', (a[0] + 2, max(10, a[1] + 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255) if traced else (0, 140, 255), 1)
    cv2.imwrite(d + "grid.png", gimg)
    sg = signlist.get(sign["gardiner"], {})
    meta = {
        "sid": sid, "unit": sign["unit"], "gardiner": sign["gardiner"], "alt": sign.get("alt"),
        "sign_name": sg.get("name"), "unicode": sign.get("uni"), "status": sign["status"],
        "tracer_note": sign.get("note", ""), "faces": "right" if sign.get("mirror", True) else "left",
        "crop": {"origin_full": [x0, y0], "scale": round(scale, 4), "size": [w, h]},
        "sign_box": sb, "neighbours": neigh,
    }
    if v2:
        import sign_boxes as B
        meta["kit"] = "v2"
        meta["typical_size_crop"] = [round(v * scale) for v in B.typical(sid)]
    if prev:
        om, ot = prev
        (pox, poy), psc = om["crop"]["origin_full"], om["crop"]["scale"]
        cv = lambda p: [round(((pox + p[0] / psc) - x0) * scale, 1), round(((poy + p[1] / psc) - y0) * scale, 1)]
        pt = dict(ot)
        pt["strokes"] = [dict(s, d=[cv(p) for p in s.get("d", [])]) for s in ot.get("strokes", [])]
        if ot.get("box"):
            pt["box"] = cv(ot["box"][:2]) + cv(ot["box"][2:])
        json.dump(pt, open(d + "trace_prev.json", "w"), indent=1, ensure_ascii=False)
        meta["prev_trace"] = "trace_prev.json"
    json.dump(meta, open(d + "meta.json", "w"), indent=1, ensure_ascii=False)
    return d


def context(sid, D):
    """Column context at lower zoom: this sign GREEN, traced neighbours RED, untraced ORANGE (approximate)."""
    g = layers()["photo"]
    by = {s["sid"]: s for s in D["signs"]}
    s = by[sid]; b = s["box"]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    x0, x1 = int(cx - 260), int(cx + 260); y0, y1 = int(cy - 420), int(cy + 420)
    c = cv2.cvtColor(cv2.createCLAHE(2.0, (8, 8)).apply(crop(g, x0, y0, x1, y1, 1.0)), cv2.COLOR_GRAY2BGR)
    for o in D["signs"]:
        ob = o.get("box")
        if not ob or o["unit"] != s["unit"] or ob[2] < x0 or ob[0] > x1 or ob[3] < y0 or ob[1] > y1:
            continue
        me = o["sid"] == sid
        col = (0, 255, 0) if me else ((0, 0, 220) if o.get("strokes") else (0, 140, 255))
        a, bb = (int(ob[0] - x0), int(ob[1] - y0)), (int(ob[2] - x0), int(ob[3] - y0))
        if me or o.get("strokes"):
            cv2.rectangle(c, a, bb, col, 2 if me else 1)
        else:
            dashed_rect(c, a, bb, col, 5)
        cv2.putText(c, f'{o.get("label") or o["sid"].split(".")[-1]}:{o["gardiner"]}', (bb[0] + 2, a[1] + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1, cv2.LINE_AA)
    cv2.imwrite(OUT + f"{sid}/context.png", c)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    args = [a for a in sys.argv[1:]]
    v2 = "--v2" in args; retrace = "--retrace" in args; seed = "--seed" in args
    args = [a for a in args if a not in ("--v2", "--retrace", "--seed")]
    D = json.load(open(P + "web/data/stone.json"))
    by = {s["sid"]: s for s in D["signs"]}
    if args and args[0] == "--sids":
        sel = [by[x] for x in args[1:] if x in by and by[x].get("box")]
    else:
        unit = args[0]
        n = args[1] if len(args) > 1 else "all"
        us = [s for s in D["signs"] if s["unit"] == unit and s.get("box")]
        sel = us
        if "--from" in args:
            k = [s["sid"] for s in us].index(args[args.index("--from") + 1])
            sel = us[k:]
        if n != "all":
            sel = sel[:int(n)]
    for s in sel:
        us = [o for o in D["signs"] if o["unit"] == s["unit"] and o.get("box")]
        print(make(s, us, D["signlist"], v2=v2, retrace=retrace, seed=seed))
        if v2:
            context(s["sid"], D)
