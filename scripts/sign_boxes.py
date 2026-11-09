"""Expected sign sizes, for regularising kit boxes and spotting incomplete traces.

Typical size of a sign = median traced extent (FULL px) of that Gardiner code across all
well-scored traces, times a per-unit scale factor (signs in line 1 are bigger than in the
columns; columns differ a little). Codes with <4 good traces fall back to the median of
their Gardiner category (G, N, ...) and then to the unit's median sign size.

  typical(sid)        -> (w, h) in FULL px
  expected_box(sid)   -> FULL-px box: the current box grown (never shrunk) to the typical size
  completeness(sid)   -> traced extent / typical size (min over w, h; None if untraced)
"""
import glob
import json
import os
import re
import statistics as st

P = "/home/anna/projects/shabaka-stone/"
_S = {}


def _good_extent(sid):
    d = P + f"work/signs/{sid}/"
    try:
        t = json.load(open(d + "trace.json")); m = json.load(open(d + "meta.json"))
    except (OSError, ValueError):
        return None
    pts = [p for s in t.get("strokes", []) for p in s.get("d", [])]
    if len(pts) < 2 or not t.get("identity_ok", True):
        return None
    sc = m["crop"]["scale"]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return ((max(xs) - min(xs)) / sc, (max(ys) - min(ys)) / sc)


def _cat(code):
    m = re.match(r"^(Aa|[A-Z])", code or "")
    return m.group(1) if m else "?"


def rid_signs():
    """Rothöhler signs without a 1901 alias, shaped like stone.json signs (sid = rid, box = box_full,
    strokes = truthy once traced)."""
    try:
        L = json.load(open(P + "work/signlist_roth.json"))
    except OSError:
        return []
    out = []
    for es in L["units"].values():
        for e in es:
            if e["alias"] or not e.get("box_full"):
                continue
            t = P + f"work/signs/{e['rid']}/trace.json"
            traced = False
            if os.path.exists(t):
                try:
                    traced = any(len(s.get("d", [])) >= 2 for s in json.load(open(t)).get("strokes", []))
                except ValueError:
                    pass
            out.append({"sid": e["rid"], "rid": e["rid"], "unit": e["unit"], "gardiner": e["gardiner"] or "?",
                        "box": e["box_full"], "strokes": traced, "status": "roth_new",
                        "note": e.get("desc", ""), "mirror": e["prefix"] not in ("L2", "L1R")})
    return out


def _load():
    if _S:
        return _S
    D = json.load(open(P + "web/data/stone.json"))
    _S["signs"] = {s["sid"]: s for s in D["signs"]}
    # signs new in Rothöhler's list (no 1901 sid) are keyed by their rid; their kits are work/signs/<rid>/
    for s in rid_signs():
        _S["signs"].setdefault(s["sid"], s)
    try:  # 1901 signs: the box from Rothöhler's list (trace extent once traced) supersedes the 1901 box
        for es in json.load(open(P + "work/signlist_roth.json"))["units"].values():
            for e in es:
                for a in [e["alias"]] + e.get("parts", []) if e["alias"] else []:
                    if a in _S["signs"] and e.get("box_full") and a == e["alias"]:
                        _S["signs"][a] = dict(_S["signs"][a], box=e["box_full"])
    except OSError:
        pass
    ext = {}
    for d in glob.glob(P + "work/signs/*/trace.json"):
        sid = d.split("/")[-2]
        e = _good_extent(sid)
        if e and sid in _S["signs"]:
            ext[sid] = e
    _S["ext"] = ext
    # first pass: raw per-code medians of the larger dimension
    by_code = {}
    for sid, (w, h) in ext.items():
        by_code.setdefault(_S["signs"][sid]["gardiner"], []).append((w, h))
    med = {c: (st.median(x[0] for x in v), st.median(x[1] for x in v)) for c, v in by_code.items() if len(v) >= 4}
    # per-unit scale: how big this unit's signs are relative to the code medians
    ratios = {}
    for sid, (w, h) in ext.items():
        s = _S["signs"][sid]; m = med.get(s["gardiner"])
        if m:
            ratios.setdefault(s["unit"], []).append(max(w, h) / max(m))
    _S["unit_k"] = {u: st.median(v) for u, v in ratios.items() if len(v) >= 5}
    # second pass: code medians normalised by unit scale
    norm = {}
    for sid, (w, h) in ext.items():
        s = _S["signs"][sid]; k = _S["unit_k"].get(s["unit"], 1.0)
        norm.setdefault(s["gardiner"], []).append((w / k, h / k))
    _S["code"] = {c: (st.median(x[0] for x in v), st.median(x[1] for x in v)) for c, v in norm.items() if len(v) >= 4}
    cat = {}
    for c, v in norm.items():
        cat.setdefault(_cat(c), []).extend(v)
    _S["cat"] = {c: (st.median(x[0] for x in v), st.median(x[1] for x in v)) for c, v in cat.items() if len(v) >= 6}
    allv = [x for v in norm.values() for x in v]
    _S["any"] = (st.median(x[0] for x in allv), st.median(x[1] for x in allv))
    return _S


def unit_scale(unit):
    S = _load()
    if unit in S["unit_k"]:
        return S["unit_k"][unit]
    # neighbouring units (columns are numbered left to right)
    try:
        n = int(unit.split("-")[0])
        near = sorted((abs(int(u.split("-")[0]) - n), k) for u, k in S["unit_k"].items() if u[0].isdigit())
        return near[0][1] if near else 1.0
    except ValueError:
        return 1.0


def typical(sid):
    S = _load(); s = S["signs"][sid]
    base = S["code"].get(s["gardiner"]) or S["cat"].get(_cat(s["gardiner"])) or S["any"]
    k = unit_scale(s["unit"])
    return base[0] * k, base[1] * k


def expected_box(sid, box=None, grow=0.85):
    """Grow the box (never shrink) so each side is at least grow * typical size, about its centre."""
    S = _load(); b = list(box or S["signs"][sid]["box"])
    tw, th = typical(sid)
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    w = max(b[2] - b[0], grow * tw); h = max(b[3] - b[1], grow * th)
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def completeness(sid):
    S = _load()
    e = _good_extent(sid)
    if not e or S["signs"][sid]["gardiner"] in ("?", "", None) or S["signs"][sid]["gardiner"] not in S["code"]:
        return None  # only judge signs whose type has a reliable size (>= 4 good traces of that code)
    tw, th = typical(sid)
    # thin signs (strokes, bars) are legitimately thin in one dimension: judge by the larger one
    return max(e[0] / tw, e[1] / th) if min(tw, th) < 0.35 * max(tw, th) else min(e[0] / tw, e[1] / th)
