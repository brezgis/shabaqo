"""Viewer data in Rothöhler's sign numbering (work/signlist_roth.json), built on top of web/data/stone.json.

Keeps everything build_data.py makes (units, readings, words, copies, outline, millstone, ...) and replaces the
signs: one record per Rothöhler sign, sid = its rid ("<unit>.R<k>"), "alias" = the 1901 sid, strokes read fresh
from the sign's trace folder (work/signs/<alias or rid>/) plus any merged parts. Rejected / merged entries are left
out. Unit sign lists and word sign lists are re-pointed from 1901 sids to rids.

Status (what the viewer colours): traced -> confirmed (same as 1901) / corrected (relabelled) / added (new in his
list or carved but not in 1901); empty / lost / untraced -> not_visible.

Does NOT import build_data.py (that module builds and writes web/data/stone.json at import time).

usage: python3 scripts/build_roth_data.py [out.json]      default work/scratch/stone_roth.json (web/ untouched)
"""
import json
import os
import re
import sys
import unicodedata

P = "/home/anna/projects/shabaka-stone/"
OUT = sys.argv[1] if len(sys.argv) > 1 else P + "work/scratch/stone_roth.json"
base = json.load(open(P + "web/data/stone.json"))
L = json.load(open(P + "work/signlist_roth.json"))
old = {s["sid"]: s for s in base["signs"]}


def uni(code):  # same as build_data.uni
    m = re.match(r"^(Aa|[A-Z])(\d+)([A-Za-z]?)$", (code or "").strip().replace(" ", "").rstrip("?"))
    if not m:
        return ""
    for name in (f"EGYPTIAN HIEROGLYPH {m.group(1).upper()}{int(m.group(2)):03d}{m.group(3).upper()}",
                 f"EGYPTIAN HIEROGLYPH {m.group(1).upper()}{int(m.group(2)):03d}"):
        try:
            return unicodedata.lookup(name)
        except KeyError:
            pass
    return ""


def strokes_of(folder):
    """(strokes in FULL px as the viewer wants them, notes, identity_ok, extent) for a trace folder, or None."""
    tf, mf = P + f"work/signs/{folder}/trace.json", P + f"work/signs/{folder}/meta.json"
    if not (os.path.exists(tf) and os.path.exists(mf)):
        return None
    try:
        tr, km = json.load(open(tf)), json.load(open(mf))
    except ValueError:
        return None
    (ox, oy), sc = km["crop"]["origin_full"], km["crop"]["scale"]
    conv = lambda pt: [round(ox + pt[0] / sc, 1), round(oy + pt[1] / sc, 1)]
    st = [{"d": [v for pt in s["d"] for v in conv(pt)], "w": round(s.get("w", 6) / sc, 2),
           "c": (s.get("conf") or "clear")[0], "z": 1 if s.get("closed") else 0}
          for s in tr.get("strokes", []) if len(s.get("d", [])) >= 2]
    xs = [v for s in st for v in s["d"][0::2]]; ys = [v for s in st for v in s["d"][1::2]]
    ext = [min(xs), min(ys), max(xs), max(ys)] if xs else None
    return st, tr.get("notes", ""), tr.get("identity_ok", True), ext


signs, rid_of = [], {}
for unit, es in L["units"].items():
    for e in es:
        if e["status"] in ("rejected", "merged"):
            continue
        rid, alias = e["rid"], e["alias"]
        o = old.get(alias, {}) if alias else {}
        rec = {"sid": rid, "alias": alias, "unit": unit, "gardiner": e["gardiner"] or "?", "alt": o.get("alt"),
               "uni": uni(e["gardiner"]), "visibility": o.get("visibility"), "register": e.get("register"),
               "note": "; ".join(x for x in (e.get("desc"), e.get("note")) if x), "box": e.get("box_full"),
               "where": "trace" if e["status"] == "traced" else e.get("box_src"),
               "mirror": e["prefix"] not in ("L2", "L1R")}
        got = strokes_of(alias or rid)
        notes, ok, strokes = "", True, []
        if got:
            strokes, notes, ok, ext = got
        for part in e.get("parts", []):  # merged 1901 fragments (bird's ground line, cobra's tail, ...)
            pg = strokes_of(part)
            if pg:
                strokes = strokes + pg[0]
        if strokes:
            rec["strokes"] = strokes
            xs = [v for s in strokes for v in s["d"][0::2]]; ys = [v for s in strokes for v in s["d"][1::2]]
            rec["box"] = [min(xs), min(ys), max(xs), max(ys)]
        rec["trace_notes"], rec["identity_ok"] = notes, ok
        if e["status"] == "traced":
            m = e.get("match")
            rec["status"] = "added" if (not alias or m in ("new", "stone_only")) else ("corrected" if m == "relabel" else "confirmed")
        else:
            rec["status"] = "not_visible"
        if rec["box"]:
            rec["box"] = [round(float(v), 1) for v in rec["box"]]
        signs.append(rec)
        rid_of[rid] = rid
for a, rid in L["alias"].items():
    rid_of.setdefault(a, rid)
kept = {s["sid"] for s in signs}

stats = {}
for s in signs:
    stats[s["status"]] = stats.get(s["status"], 0) + 1
by_unit = {}
for s in signs:
    by_unit.setdefault(s["unit"], []).append(s)
for u in base["units"]:
    us = by_unit.get(u["id"], [])
    u["signs"] = [s["sid"] for s in us]
    u["counts"] = {}
    for s in us:
        u["counts"][s["status"]] = u["counts"].get(s["status"], 0) + 1
    u["n_present"] = sum(1 for s in us if s["status"] != "not_visible")
    for w in u.get("words", []):
        seen = []
        for sid in w.get("signs", []):
            r = rid_of.get(sid)
            if r in kept and r not in seen:
                seen.append(r)
        w["signs"] = seen
    u["words"] = [w for w in u.get("words", []) if w["signs"]]
mx = max([u["n_present"] for u in base["units"] if u["id"] not in ("lines1-2", "48-52")] or [1])
for u in base["units"]:
    u["preservation"] = min(1.0, u["n_present"] / mx)

base["signs"], base["stats"], base["numbering"] = signs, stats, "rothoehler2005"
tmp = OUT + ".tmp"
json.dump(base, open(tmp, "w"), ensure_ascii=False, separators=(",", ":"))
os.replace(tmp, OUT)
print(len(signs), "signs", stats, f"-> {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")
