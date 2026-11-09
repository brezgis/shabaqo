"""Automatic checks on per-sign stroke traces (run after each trace, or over everything).

usage: trace_qa.py <sid> [sid...]          check these signs, print one line each
       trace_qa.py --all [--write]         check every traced kit; --write saves work/trace_qa.json
       trace_qa.py --requeue               print v1-kit sids that should be re-traced with a v2 kit
       trace_qa.py --review                print sids a person should look at (still flagged after v2,
                                           identity doubts, overlaps)

Flags (any one means "look at this"):
  empty        trace has no strokes (fine if the notes explain it, e.g. nothing visible)
  off_cut      lock < 1.0: strokes mostly beside the grooves (trace_score.py)
  weak_native  native < 1.0 while lock is ok: may be tracing upscaling artefacts
  clipped      a stroke runs to within 6 crop px of the crop edge: the sign may continue outside
  incomplete   traced extent < 60% of the typical size of this sign type (sign_boxes.py),
               or the notes say parts were not resolved / were left out at a box edge
  identity     identity_ok = false
  overlap      trace overlaps a traced neighbour's trace by > 40% of the smaller extent
               (two sids traced on the same carving)
  absorbs      an untraced neighbour's box is mostly covered by this trace
               (its sign may be part of this one, e.g. a bird's feet given their own '?' box)
Re-queue = a v1 trace that is clipped, incomplete or off_cut: it gets a v2 kit and one re-trace.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_boxes as B  # noqa: E402
from trace_score import score  # noqa: E402

P = "/home/anna/projects/shabaka-stone/"
SIGNS = P + "work/signs/"
NOTE_INCOMPLETE = re.compile(r"not resolved|left out|cut off|clipped|beyond the crop|outside the crop|continues? (outside|beyond|past)", re.I)


def extent_full(sid):
    d = SIGNS + sid + "/"
    try:
        t = json.load(open(d + "trace.json")); m = json.load(open(d + "meta.json"))
    except (OSError, ValueError):
        return None
    pts = [p for s in t.get("strokes", []) for p in s.get("d", [])]
    if len(pts) < 2:
        return None
    (ox, oy), sc = m["crop"]["origin_full"], m["crop"]["scale"]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return [ox + min(xs) / sc, oy + min(ys) / sc, ox + max(xs) / sc, oy + max(ys) / sc]


def inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def area(a):
    return max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))


def check(sid):
    d = SIGNS + sid + "/"
    if not os.path.exists(d + "trace.json"):
        return {"sid": sid, "flags": ["untraced"]}
    t = json.load(open(d + "trace.json")); m = json.load(open(d + "meta.json"))
    W, H = m["crop"]["size"]
    strokes = [s for s in t.get("strokes", []) if len(s.get("d", [])) >= 2]
    r = {"sid": sid, "kit": m.get("kit", "v1"), "flags": [], "notes": t.get("notes", "")[:160]}
    if not strokes:
        r["flags"].append("empty")
        return r
    sc = score(d)
    r.update({k: sc[k] for k in ("lock", "native", "support")})
    if sc["lock"] < 1.0:
        r["flags"].append("off_cut")
    elif sc["native"] < 1.0:
        r["flags"].append("weak_native")
    pts = [p for s in strokes for p in s["d"]]
    edge = min(min(p[0] for p in pts), min(p[1] for p in pts), W - max(p[0] for p in pts), H - max(p[1] for p in pts))
    r["edge_px"] = round(edge)
    if edge <= 6:
        r["flags"].append("clipped")
    try:
        c = B.completeness(sid)
    except KeyError:
        c = None
    r["complete"] = None if c is None else round(c, 2)
    if (c is not None and c < 0.6) or NOTE_INCOMPLETE.search(t.get("notes", "")):
        r["flags"].append("incomplete")
    if not t.get("identity_ok", True):
        r["flags"].append("identity")
    me = extent_full(sid)
    S = B._load()
    unit = S["signs"].get(sid, {}).get("unit")
    if me and unit:
        for o in S["signs"].values():
            if o["unit"] != unit or o["sid"] == sid or not o.get("box"):
                continue
            ob = extent_full(o["sid"]) if o.get("strokes") else None
            if ob:
                if inter(me, ob) > 0.4 * min(area(me), area(ob)):
                    r["flags"].append(f"overlap:{o['sid']}")
            elif inter(me, o["box"]) > 0.6 * area(o["box"]):
                r["flags"].append(f"absorbs:{o['sid']}")
    return r


def requeue(r):
    """One automatic touch-up pass: only first-round (v1) traces are re-queued. A v2 trace that is
    still flagged goes to the review list (--review) instead of being re-traced again."""
    f = set(x.split(":")[0] for x in r["flags"])
    return r.get("kit") == "v1" and bool(f & {"clipped", "incomplete", "off_cut"})


def review(r):
    f = set(x.split(":")[0] for x in r["flags"])
    return r.get("kit") == "v2" and bool(f - {"empty"}) or bool(f & {"identity", "overlap", "absorbs"})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    if a[0] in ("--all", "--requeue", "--review"):
        sids = sorted(p.split("/")[-2] for p in glob.glob(SIGNS + "*/trace.json"))
        rows = [check(s) for s in sids]
        if a[0] in ("--requeue", "--review"):
            pick = requeue if a[0] == "--requeue" else review
            print(" ".join(r["sid"] for r in rows if pick(r)))
            sys.exit(0)
        from collections import Counter
        cnt = Counter(x.split(":")[0] for r in rows for x in r["flags"])
        print(f"{len(rows)} traces; flags: {dict(cnt)}; clean: {sum(not r['flags'] for r in rows)}; requeue: {sum(requeue(r) for r in rows)}")
        if "--write" in a:
            json.dump(rows, open(P + "work/trace_qa.json", "w"), indent=1, ensure_ascii=False)
            print("wrote work/trace_qa.json")
    else:
        for s in a:
            r = check(s)
            print(json.dumps({k: v for k, v in r.items() if k != "notes"}, ensure_ascii=False))
