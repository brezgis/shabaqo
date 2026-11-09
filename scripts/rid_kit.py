"""v2 tracing kits in Rothöhler's frame (work/signlist_roth.json, see scripts/renumber_roth.py).

usage: python3 scripts/rid_kit.py <rid> [rid ...]
       python3 scripts/rid_kit.py --pick <unit> <n>     print the first n untraced rids of a unit

Kit folder: work/signs/<alias>/ when the sign has a 1901 alias (so earlier work and traces stay where
they are), else work/signs/<rid>/. Identity, box and neighbours come from Rothöhler's list: the
Gardiner code is his, grid.png/context.png label every sign with its Rothöhler number (R<k>), and
meta.json gets "rid" and a "roth" block. Afterwards run scripts/roth_kit.py --sids <folders> for roth.png
(this script does it).
An existing trace.json is kept: the old folder is backed up to work/scratch/kit_rebuild_backup/<folder>/
and the trace's points are converted into the new crop coordinates (check.png is re-rendered).
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_boxes as B  # noqa: E402
import sign_kit as K  # noqa: E402

P = K.P
L = json.load(open(P + "work/signlist_roth.json"))
D = json.load(open(P + "web/data/stone.json"))
old = {s["sid"]: s for s in D["signs"]}
by_rid = {e["rid"]: e for es in L["units"].values() for e in es}


def folder(e):
    return e["alias"] or e["rid"]


def as_sign(e):
    """A stone.json-shaped sign for one Rothöhler entry (sid = its kit folder)."""
    base = dict(old.get(e["alias"]) or {}) if e["alias"] else {}
    traced = e["status"] == "traced" or bool(base.get("strokes"))
    note = "; ".join(x for x in (e.get("desc"), e.get("note")) if x)
    return dict(base, sid=folder(e), rid=e["rid"], unit=e["unit"], gardiner=e["gardiner"] or "?",
                box=e["box_full"], strokes=traced, label=f"R{e['k']}", note=note,
                status=base.get("status", "roth_new"), mirror=e["prefix"] not in ("L2", "L1R"))


def make(rid):
    e = by_rid[rid]
    if not e.get("box_full"):
        print(f"skip {rid}: no box"); return None
    unit = [as_sign(x) for x in L["units"][e["unit"]] if x.get("box_full")]
    me = next(s for s in unit if s["rid"] == rid)
    d0 = K.OUT + me["sid"] + "/"
    keep = None  # an existing trace survives a kit rebuild: its points are moved into the new crop
    if os.path.exists(d0 + "trace.json") and os.path.exists(d0 + "meta.json"):
        keep = (json.load(open(d0 + "meta.json")), json.load(open(d0 + "trace.json")))
        bk = P + f"work/scratch/kit_rebuild_backup/{me['sid']}/"
        if not os.path.exists(bk):
            shutil.copytree(d0, bk)
        me["strokes"] = False  # don't grow the box around the trace's (old-frame) extent twice
    S = B._load()  # size estimates should use HIS sign type
    S["signs"][me["sid"]] = dict(S["signs"].get(me["sid"], {}), **{k: me[k] for k in ("sid", "unit", "gardiner", "box")})
    d = K.make(me, unit, D["signlist"], v2=True)
    K.context(me["sid"], {"signs": unit})
    m = json.load(open(d + "meta.json"))
    for nb in m["neighbours"]:
        o = next((s for s in unit if s["sid"] == nb["sid"]), None)
        if o:
            nb["rid"] = o["rid"]
    if keep:
        om, ot = keep
        (pox, poy), psc = om["crop"]["origin_full"], om["crop"]["scale"]
        (nx, ny), nsc = m["crop"]["origin_full"], m["crop"]["scale"]
        cv = lambda p: [round(((pox + p[0] / psc) - nx) * nsc, 1), round(((poy + p[1] / psc) - ny) * nsc, 1)] + list(p[2:])
        nt = dict(ot, strokes=[dict(s, d=[cv(p) for p in s.get("d", [])]) for s in ot.get("strokes", [])])
        if ot.get("box"):
            nt["box"] = cv(ot["box"][:2]) + cv(ot["box"][2:4])
        json.dump(nt, open(d + "trace.json", "w"), indent=1, ensure_ascii=False)
        subprocess.run([sys.executable, P + "scripts/render_trace.py", d], check=False, capture_output=True)
    m["rid"] = rid
    m["roth"] = {"rid": rid, "k": e["k"], "gardiner": e["gardiner"], "desc": e.get("desc", ""),
                 "note": e.get("note", ""), "alias_1901": e["alias"], "match": e.get("match"),
                 "register": e.get("register"),
                 "old_gardiner_1901": (old.get(e["alias"]) or {}).get("gardiner") if e["alias"] else None}
    json.dump(m, open(d + "meta.json", "w"), indent=1, ensure_ascii=False)
    return folder(e)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    if a[0] == "--pick":
        es = [e for e in L["units"][a[1]] if e["status"] == "untraced" and e.get("box_full")]
        print(" ".join(e["rid"] for e in es[:int(a[2])])); sys.exit(0)
    made = [f for f in (make(r) for r in a) if f]
    for f in made:
        print(f"{f}  ({next(r for r in a if folder(by_rid[r]) == f)})")
    if made:
        subprocess.run([sys.executable, P + "scripts/roth_kit.py", "--sids", *made], check=True)
