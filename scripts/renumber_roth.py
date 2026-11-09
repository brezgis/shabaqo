"""Make Rothöhler 2005's sign sequence the canonical sign list (Anna, 2026-11-07).

Input:  work/roth_inventory/<unit>.json (see work/ROTH_INVENTORY_TASK.md), web/data/stone.json (1901-derived
        signs and boxes), existing traces (work/signs/<sid>/trace.json).
Output: work/signlist_roth.json
  {"units": {unit: [entry, ...]},           entries in reading order
   "alias": {old_sid: rid},                 every 1901 sid that maps to a sign
   "phantom": {old_sid: note},              1901 sids with neither carving nor a sign in Rothöhler
   "stats": {...}}
  entry = {rid, unit, prefix, k, register, gardiner, desc, alias, match, source, status, box_full, note}
    rid      "<prefix>.R<k>": prefix = unit for columns, L1L/L1R/L2 for the lines; k counts per prefix
    source   "roth" (a sign he draws) | "stone_only" (carved on the stone, not in his drawing)
    status   "traced" (alias has a trace with strokes) | "empty" (alias traced, nothing visible) |
             "lost" (he draws it, surface lost) | "untraced"
    box_full FULL-px box: the trace's extent if traced, else the 1901 box, else his plate box mapped
             through scripts/roth_map.py
Traces are tied to positions on the stone, so nothing traced is lost: each traced 1901 sid becomes
the alias of the Rothöhler sign at its place. A traced 1901 sid that is only part of a sign (PART_OF, or
"part_of" in the inventory) becomes an extra alias of that sign, listed in the entry's "parts".

usage: python3 scripts/renumber_roth.py [--units u ...]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roth_map import plate_to_full, region_index, unit_traces  # noqa: E402

P = "/home/anna/projects/shabaka-stone/"
D = json.load(open(P + "web/data/stone.json"))
old = {s["sid"]: s for s in D["signs"]}
D_UNITS = [u["id"] for u in D["units"]]
args = sys.argv[1:]
only = set(args[args.index("--units") + 1:]) if "--units" in args else None


def sid_key(sid):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", sid)]


def plate_box_full(unit, pb):
    a = plate_to_full(unit, pb[0], pb[1]); b = plate_to_full(unit, pb[2], pb[3])
    if not a or not b:
        # units with no mapped region (38, 39: only ruled dashes beside the hole) borrow the nearest
        # numbered unit's mapping; rough (~50-100 FULL px), the tracer places the sign by context
        if not unit.isdigit():
            return None
        for nb in sorted((u for u in D_UNITS if u.isdigit() and u != unit), key=lambda u: abs(int(u) - int(unit))):
            a = plate_to_full(nb, pb[0], pb[1]); b = plate_to_full(nb, pb[2], pb[3])
            if a and b:
                break
        else:
            return None
    return [round(min(a[0], b[0])), round(min(a[1], b[1])), round(max(a[0], b[0])), round(max(a[1], b[1]))]


# traced 1901 sids that are a PART of a neighbouring sign in Rothöhler's drawing (a bird's ground line, the
# shaft under an O9 top, a bird body split from its head ...): their trace joins the parent's Rothöhler sign as a
# second alias instead of being dropped. Inventories can also say so with "part_of" on a phantom or stone_only
# entry.
# Resolved from the inventory phantom notes, 2026-11-08.
PART_OF = {
    "3.8": "3.7", "3.14": "3.13", "4.10": "4.9", "9.11": "9.10", "13.38": "13.37",
    "62.24": "62.23", "62.47": "62.46", "62.57": "62.56",
    "63.19": "63.18", "63.24": "63.23", "63.29": "63.27", "63.59": "63.58",
    # listed as stone_only by their inventory, but only fragments of the neighbouring sign
    "53.34": "53.33", "54.38": "54.37", "55.7": "55.8", "55.27": "55.26",
}

ALIGN = json.load(open(P + "work/roth_align.json")) if os.path.exists(P + "work/roth_align.json") else {}
FAR, GOOD_N, GOOD_RMS = 60, 8, 25  # see the "box_src" rule below


def reliable_plate_box(unit, pb):
    """His plate box mapped to FULL px, only where that region's drift fit is trustworthy; else None."""
    i = region_index(unit, (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2)
    c = ALIGN.get(f"{unit}#{i}") if i is not None else None
    if not c or c["n"] < GOOD_N or c["rms_after_inliers"] > GOOD_RMS:
        return None
    return plate_box_full(unit, pb)


out = {"units": {}, "alias": {}, "phantom": {}, "stats": {}}
missing = []
for u in D["units"]:
    unit = u["id"]
    if only and unit not in only:
        continue
    f = P + f"work/roth_inventory/{unit}.json"
    if not os.path.exists(f):
        missing.append(unit); continue
    inv = json.load(open(f))
    tr = {t["sid"]: t for t in unit_traces(unit)}
    lost_n = {x.get("n") for x in inv.get("lost", [])}
    seq = []
    for s in inv.get("signs", []):
        seq.append({"src": "roth", "s": s})
    phantoms, parts = [], {}  # parts: parent sid -> [part sids]
    # stone-only signs: insert after the last Rothöhler sign whose alias comes before them in 1901 order
    for so in inv.get("stone_only", []):
        parent = so.get("part_of") or PART_OF.get(so["sid"])
        if parent and any(e["s"].get("sid") == parent for e in seq):
            parts.setdefault(parent, []).append(so["sid"])
            continue
        k = 0
        for i, e in enumerate(seq):
            a = e["s"].get("sid")
            if a and sid_key(a) < sid_key(so["sid"]):
                k = i + 1
        seq.insert(k, {"src": "stone_only", "s": {"sid": so["sid"], "note": so.get("note", ""),
                                                   "gardiner": (old.get(so["sid"]) or {}).get("gardiner", "?")}})
    # never drop a trace: a "phantom" that carries a real trace takes the place of an adjacent
    # (1901-order) alias that is untraced or empty (typical when one 1901 box covered a group and the
    # "match the first sid" rule picked the untraced one)
    for p in inv.get("phantom", []):
        t = tr.get(p["sid"])
        parent = p.get("part_of") or PART_OF.get(p["sid"])
        if t and not t["empty"] and parent and any(e["s"].get("sid") == parent for e in seq):
            parts.setdefault(parent, []).append(p["sid"])
            continue
        if t and not t["empty"]:
            ordered = sorted([e["s"]["sid"] for e in seq if e["s"].get("sid")], key=sid_key)
            pk = sid_key(p["sid"])
            near = sorted(ordered, key=lambda a: abs(sid_key(a)[-1] - pk[-1]) if isinstance(pk[-1], int)
                          and isinstance(sid_key(a)[-1], int) else 99)
            for a in near[:2]:
                ta = tr.get(a)
                if ta is None or ta["empty"]:
                    for e in seq:
                        if e["s"].get("sid") == a:
                            e["s"] = dict(e["s"], sid=p["sid"],
                                          note=(e["s"].get("note", "") + f" [alias swapped: {a} was untraced/empty, {p['sid']} carries the trace]").strip())
                    p = {"sid": a, "note": f"swapped with {p['sid']} (which carries the trace)"}
                    break
            else:
                out.setdefault("traced_phantoms", []).append(p["sid"])
        phantoms.append(p)
    for p in phantoms:
        out["phantom"][p["sid"]] = p.get("note", "")
    counters, entries = {}, []
    for e in seq:
        s = e["s"]
        reg = s.get("register") or unit
        prefix = reg if unit == "lines1-2" else unit
        counters[prefix] = counters.get(prefix, 0) + 1
        k = counters[prefix]
        alias = s.get("sid")
        box_src = None
        # a sign new in his list is traced in work/signs/<rid>/ (scripts/rid_kit.py); its rid must stay stable,
        # so don't reorder an inventory once kits for its new signs exist
        t = tr.get(alias) if alias else tr.get(f"{prefix}.R{k}")
        if t and not t["empty"]:
            status, box = "traced", t["bbox_full"]
        elif t and t["empty"]:
            status, box = ("lost" if s.get("n") in lost_n else "empty"), (t["bbox_full"] or (old.get(alias) or {}).get("box"))
        else:
            status = "lost" if (e["src"] == "roth" and s.get("n") in lost_n) else "untraced"
            box = (old.get(alias) or {}).get("box") if alias else None
            # box_src rule: an untraced 1901 box that lies > FAR px from his sign mapped through a reliable
            # region fit is probably misplaced (pilot roth-57a: 57.3 sat 115 px off): use his mapped box
            if box and s.get("plate_box"):
                rb = reliable_plate_box(unit, s["plate_box"])
                if rb and ((box[0] + box[2] - rb[0] - rb[2]) ** 2 + (box[1] + box[3] - rb[1] - rb[3]) ** 2) ** .5 / 2 > FAR:
                    box, box_src = rb, "roth_mapped"
        for ps in parts.get(alias, []) if alias else []:  # merge traced parts: union box, counts as traced
            pb = tr[ps]["bbox_full"]
            if pb:
                box = [min(box[0], pb[0]), min(box[1], pb[1]), max(box[2], pb[2]), max(box[3], pb[3])] \
                    if box and status == "traced" else pb
            status = "traced"
        if not box and s.get("plate_box"):
            box = plate_box_full(unit, s["plate_box"])
        rid = f"{prefix}.R{k}"
        ent = {"rid": rid, "unit": unit, "prefix": prefix, "k": k, "register": reg,
               "gardiner": s.get("gardiner") or (old.get(alias) or {}).get("gardiner", "?"),
               "desc": s.get("desc", ""), "alias": alias, "match": s.get("match", "stone_only" if e["src"] == "stone_only" else None),
               "source": e["src"], "status": status, "plate_box": s.get("plate_box"),
               "box_src": box_src or ("trace" if status == "traced" else "1901" if alias else "roth_mapped"),
               "box_full": [round(v, 1) for v in box] if box else None, "note": s.get("note", "")}
        if alias and parts.get(alias):
            ent["parts"] = parts[alias]  # extra 1901 sids whose traces belong to this sign
            for ps in parts[alias]:
                out["alias"][ps] = rid
        entries.append(ent)
        if alias:
            out["alias"][alias] = rid
    out["units"][unit] = entries

# hand decisions (work/roth_overrides.json): applied after the inventories so every rid keeps its k
OV = json.load(open(P + "work/roth_overrides.json")) if os.path.exists(P + "work/roth_overrides.json") else {}
by_rid = {e["rid"]: e for es in out["units"].values() for e in es}


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])] if a and b else (a or b)


for rid, why in OV.get("reject", {}).items():
    if rid in by_rid:
        by_rid[rid].update(status="rejected", note=(by_rid[rid]["note"] + " [rejected: " + why + "]").strip())
for rid, parent in OV.get("merge_into", {}).items():
    e, pe = by_rid.get(rid), by_rid.get(parent)
    if e and pe:
        if e["alias"]:
            pe.setdefault("parts", []).append(e["alias"]); out["alias"][e["alias"]] = parent
            if e["status"] == "traced":
                pe["box_full"] = _union(pe["box_full"], e["box_full"])
        e.update(status="merged", note=(e["note"] + f" [merged into {parent}]").strip())
for sid, rid in OV.get("part_alias", {}).items():
    pe = by_rid.get(rid)
    if not pe:
        continue
    for e in by_rid.values():
        if sid in e.get("parts", []):
            e["parts"].remove(sid)
    out["phantom"].pop(sid, None)
    pe.setdefault("parts", []).append(sid); out["alias"][sid] = rid

# 1901 sids not accounted for anywhere (should be none)
covered = set(out["alias"]) | set(out["phantom"])
units_done = set(out["units"])
unaccounted = [sid for sid, s in old.items() if s["unit"] in units_done and sid not in covered]
allE = [e for es in out["units"].values() for e in es]
out["stats"] = {
    "units": len(units_done), "missing_inventories": missing, "signs": len(allE),
    "traced": sum(e["status"] == "traced" for e in allE), "empty": sum(e["status"] == "empty" for e in allE),
    "lost": sum(e["status"] == "lost" for e in allE), "untraced": sum(e["status"] == "untraced" for e in allE),
    "rejected": sum(e["status"] == "rejected" for e in allE), "merged": sum(e["status"] == "merged" for e in allE),
    "new_signs": sum(e["source"] == "roth" and not e["alias"] for e in allE),
    "stone_only": sum(e["source"] == "stone_only" for e in allE), "phantoms": len(out["phantom"]),
    "no_box": [e["rid"] for e in allE if not e["box_full"]][:20], "unaccounted_1901": unaccounted[:30],
    "traced_phantoms_unresolved": out.get("traced_phantoms", []),
}
tmp = P + "work/signlist_roth.json.tmp"  # atomic: tracer tools read this file while batches run
json.dump(out, open(tmp, "w"), indent=1, ensure_ascii=False)
os.replace(tmp, P + "work/signlist_roth.json")
print(json.dumps(out["stats"], indent=1))
