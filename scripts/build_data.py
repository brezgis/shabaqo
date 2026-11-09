"""Assemble web/data/stone.json from the tracing agents' reports.

Per sign:
  - Breasted-matched signs: Breasted's own outline for that sign, refit
    individually to the photo (translation + scale), unless the tracer marked it
    corrected / not visible.
  - added / corrected signs: strokes extracted from the photo inside the
    tracer's box (gated by native-photo relief), shown in their own colour.
"""
import glob
import json
import os
import sys
import unicodedata

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from geom import P, plate_to_full, H  # noqa: E402
from refit import refit, ink_full  # noqa: E402
from strokes import extract  # noqa: E402

OUT = P + "web/data/"
os.makedirs(OUT, exist_ok=True)
T = 7.155  # thumbnail(1600px) -> FULL

bbox_a2 = {b["id"]: b["a2"] for b in json.load(open(P + "work/breasted_boxes_a2.json"))}
cols = json.load(open(P + "work/columns.json"))
brmap = json.load(open(P + "work/br_mapping.json"))
signlist = json.load(open(P + "work/gardiner_signs.json")) if os.path.exists(P + "work/gardiner_signs.json") else {}
INK = ink_full()

SECTIONS = [
    ("Titulary & dedication", ["lines1-2"],
     "Shabaka's names, and his note that he found this text worm-eaten and copied it anew."),
    ("Ptah, king of the Two Lands", [str(i) for i in range(3, 10)], "Ptah's titles; Geb gathers the Ennead."),
    ("The judgement of Geb", [str(i) for i in range(10, 19)], "Geb divides Egypt between Horus and Seth, then gives it all to Horus."),
    ("The drama", [str(i) for i in range(19, 36)], "Speeches of the gods, set out like a script; badly worn."),
    ("The millstone's wound", [str(i) for i in range(36, 48)], "Columns almost erased by grinding."),
    ("The gods in Ptah", ["48-52"], "A table of the forms of Ptah."),
    ("Heart and tongue", [str(i) for i in range(53, 62)], "Creation by thought and command."),
    ("Osiris & Memphis", [str(i) for i in range(62, 65)], "Osiris drowned and brought ashore; Memphis as granary of the land."),
]
section_of = {u: s[0] for s in SECTIONS for u in s[1]}


def uni(code):
    if not code or code == "?":
        return ""
    c = code.strip().replace(" ", "")
    import re
    m = re.match(r"^(Aa|[A-Z])(\d+)([A-Za-z]?)$", c)
    if not m:
        return ""
    name = f"EGYPTIAN HIEROGLYPH {m.group(1).upper()}{int(m.group(2)):03d}{m.group(3).upper()}"
    try:
        return unicodedata.lookup(name)
    except KeyError:
        try:
            return unicodedata.lookup(f"EGYPTIAN HIEROGLYPH {m.group(1).upper()}{int(m.group(2)):03d}")
        except KeyError:
            return ""


def flat(poly):
    return [round(float(v), 1) for p in poly for v in p]


def ink_polys(box_full, dx=0, dy=0, s=1.0):
    """Outline polygons of Breasted's (globally warped) ink inside box, then
    apply the per-sign refit about the box centre."""
    x0, y0, x1, y1 = [int(round(v)) for v in box_full]
    x0 -= 3; y0 -= 3; x1 += 3; y1 += 3
    m = (INK[y0:y1, x0:x1] > 90).astype(np.uint8)
    if m.sum() == 0:
        return []
    cs, _ = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for c in cs:
        if cv2.contourArea(c) < 4 and len(c) < 6:
            continue
        a = cv2.approxPolyDP(c, 0.8, True)[:, 0, :].astype(float) + [x0, y0]
        a = (a - [cx, cy]) * s + [cx + dx, cy + dy]
        out.append(flat(a))
    return out


def union(boxes):
    b = np.array(boxes, float)
    return [b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()]


units, signs, stats = [], [], {}
reports = {os.path.basename(f)[:-5]: json.load(open(f)) for f in sorted(glob.glob(os.environ.get("TRACE_DIR", P + "work/trace_out") + "/*.json"))}
order = ["lines1-2"] + [c["label"] for c in cols]

def traced_box(sid):
    """FULL-px box of a sign's stroke trace (strokes' extent, else the trace's box)."""
    tf = P + f"work/signs/{sid}/trace.json"
    if not os.path.exists(tf):
        return None
    try:
        tr = json.load(open(tf)); km = json.load(open(P + f"work/signs/{sid}/meta.json"))
    except (ValueError, OSError):
        return None
    (ox, oy), sc = km["crop"]["origin_full"], km["crop"]["scale"]
    pts = [pt for st in tr.get("strokes", []) for pt in st.get("d", [])]
    if pts:
        a = np.array(pts, float)
        return [ox + a[:, 0].min() / sc, oy + a[:, 1].min() / sc, ox + a[:, 0].max() / sc, oy + a[:, 1].max() / sc]
    return None


def unit_offsets(rep, uid):
    """Coarse wide search for every Breasted-matched sign, then a rolling median
    along the line/column, so a stretch that the global warp got wrong moves together."""
    items = []
    for sg in rep.get("signs", []):
        bids = [b for b in sg.get("breasted", []) or [] if b in bbox_a2]
        if not bids or sg.get("status") == "not_visible":
            continue
        bf = [v * 2 for v in union([bbox_a2[b] for b in bids])]
        tb = traced_box(sg["sid"])
        if tb:  # stroke-traced on the stone: the strongest anchor there is
            dx = (tb[0] + tb[2]) / 2 - (bf[0] + bf[2]) / 2; dy = (tb[1] + tb[3]) / 2 - (bf[1] + bf[3]) / 2
            if abs(dx) < 400 and abs(dy) < 400:
                items += [(sg["sid"], bf, dx, dy, 1.0)] * 5
                continue
        own = sg.get("bbox_a2")
        if own:  # the tracer measured this sign on the stone: a strong anchor
            ocx, ocy = (own[0] + own[2]), (own[1] + own[3])  # x2 for FULL, /2 for centre
            dx, dy = ocx - (bf[0] + bf[2]) / 2, ocy - (bf[1] + bf[3]) / 2
            if abs(dx) < 220 and abs(dy) < 220:
                items += [(sg["sid"], bf, dx, dy, 1.0)] * 3
                continue
        dx, dy, s_, sc, gain = refit(bf, search=110, scales=(1.0,))
        items.append((sg["sid"], bf, dx, dy, gain))
    if not items:
        return {}
    horiz = uid == "lines1-2"
    key = (lambda it: (it[0][:2], (it[1][0] + it[1][2]) / 2)) if horiz else (lambda it: (it[1][1] + it[1][3]) / 2)
    items.sort(key=key)
    out = {}
    for i, it in enumerate(items):
        grp = it[0][:2] if horiz else None
        nb = [x for x in items[max(0, i - 6):i + 7] if not horiz or x[0][:2] == grp]
        w = [x for x in nb if x[4] > 0.05] or nb
        out[it[0]] = (float(np.median([x[2] for x in w])), float(np.median([x[3] for x in w])))
    return out


for uid in order:
    rep = reports.get(uid)
    if rep is None:
        continue
    usigns, counts = [], {}
    offs = unit_offsets(rep, uid)
    for sg in rep.get("signs", []):
        st = sg.get("status", "confirmed")
        bids = [b for b in sg.get("breasted", []) or [] if b in bbox_a2]
        rec = {"sid": sg["sid"], "unit": uid, "gardiner": sg.get("gardiner", "?"), "alt": sg.get("alt"),
               "uni": uni(sg.get("gardiner")), "status": st, "visibility": sg.get("visibility"),
               "note": sg.get("note", ""), "box": None}
        counts[st] = counts.get(st, 0) + 1
        own = sg.get("bbox_a2")
        # WHERE: tracer's own box wins; otherwise Breasted's box re-fitted to the carving.
        # (Breasted's drawn shapes are not used for the trace itself.)
        if own and (st in ("added", "corrected") or not bids):
            rec["box"] = [v * 2 for v in own]
            rec["where"] = "tracer"
        elif bids:
            bf = [v * 2 for v in union([bbox_a2[b] for b in bids])]
            ox, oy = offs.get(sg["sid"], (0.0, 0.0))
            bf = [bf[0] + ox, bf[1] + oy, bf[2] + ox, bf[3] + oy]
            dx, dy, s, sc, gain = (0, 0, 1.0, 0, 0) if st == "not_visible" else refit(bf, search=12)
            cx, cy = (bf[0] + bf[2]) / 2 + dx, (bf[1] + bf[3]) / 2 + dy
            hw, hh = (bf[2] - bf[0]) / 2 * s, (bf[3] - bf[1]) / 2 * s
            rec["box"] = [cx - hw, cy - hh, cx + hw, cy + hh]
            rec["where"] = "refit" if st != "not_visible" else "breasted"
        # HOW IT LOOKS: the per-sign stroke trace drawn on the photographs (work/signs/<sid>/trace.json)
        tf = P + f"work/signs/{sg['sid']}/trace.json"
        if os.path.exists(tf):
            try:
                tr = json.load(open(tf)); km = json.load(open(P + f"work/signs/{sg['sid']}/meta.json"))
                (ox, oy), sc_ = km["crop"]["origin_full"], km["crop"]["scale"]
                conv = lambda pt: [round(ox + pt[0] / sc_, 1), round(oy + pt[1] / sc_, 1)]
                rec["strokes"] = [{"d": [v for pt in stk["d"] for v in conv(pt)], "w": round(stk.get("w", 6) / sc_, 2),
                                   "c": stk.get("conf", "clear")[0], "z": 1 if stk.get("closed") else 0}
                                  for stk in tr.get("strokes", []) if len(stk.get("d", [])) >= 2]
                if tr.get("box"):
                    b = tr["box"]; rec["box"] = conv(b[:2]) + conv(b[2:])
                rec["trace_notes"] = tr.get("notes", "")
                rec["identity_ok"] = tr.get("identity_ok", True)
            except Exception as ex:
                print("bad trace", sg["sid"], ex)
        if rec["box"] is not None:
            rec["box"] = [round(float(v), 1) for v in rec["box"]]
        rec["mirror"] = not (uid == "lines1-2" and (sg["sid"].startswith("L2") or sg["sid"].startswith("L1R")))
        stats[st] = stats.get(st, 0) + 1
        signs.append(rec)
        usigns.append(rec)

    boxes = [s["box"] for s in usigns if s["box"]]
    if boxes:
        bounds = union(boxes)
    else:  # column outline from the grid
        c = next((c for c in cols if c["label"] == uid), None)
        if c:
            q = plate_to_full([[c["cx"] - 30, 600], [c["cx"] + 30, 2340]])
            bounds = [q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()]
        else:
            bounds = [900, 750, 10800, 1260]
    title = "Lines 1–2" if uid == "lines1-2" else ("Columns 48–52" if uid == "48-52" else f"Column {uid}")
    short = "1–2" if uid == "lines1-2" else uid
    units.append({
        "id": uid, "title": title, "short": short, "section": section_of.get(uid, ""),
        "summary": rep.get("summary", ""), "translation": rep.get("translation", ""),
        "lacunae": rep.get("lacunae", ""), "breasted_issues": rep.get("breasted_issues", []),
        "confidence": rep.get("confidence", ""), "registers": rep.get("registers", []),
        "words": [w for w in rep.get("words", []) if w.get("signs")],
        "signs": [s["sid"] for s in usigns], "counts": counts,
        "bounds": [round(float(v), 1) for v in bounds],
        "n_present": sum(1 for s in usigns if s["status"] != "not_visible"),
        "copies": {"breasted": f"copies/breasted_{uid}.jpg", "br": f"copies/br_{uid}.jpg",
                   "br_cols": brmap.get(uid, {}).get("br_shown", [])},
    })

mx = max([u["n_present"] for u in units if u["id"] not in ("lines1-2", "48-52")] or [1])
for u in units:
    u["preservation"] = min(1.0, u["n_present"] / mx)

# Breasted's copy as published (global warp only), for comparison
plate = cv2.imread(P + "work/rules_removed.png", 0)
glob_ink = cv2.warpPerspective(plate, H, (11448, 7452), flags=cv2.INTER_LINEAR)
small = cv2.resize(glob_ink, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) > 70
cs, _ = cv2.findContours(small.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
breasted = [flat(cv2.approxPolyDP(c, 0.7, True)[:, 0, :] * 2.0) for c in cs if len(c) >= 4]

# millstone: grooves as capsules + the socket (thumbnail coords x T)
grooves = [((820, 150), (838, 465), 32), ((548, 262), (742, 465), 32), ((1112, 282), (938, 478), 30),
           ((1290, 402), (960, 555), 30), ((438, 518), (720, 572), 30), ((945, 605), (1255, 655), 30),
           ((488, 738), (712, 622), 28), ((585, 835), (760, 662), 26), ((735, 935), (805, 705), 24),
           ((895, 705), (962, 975), 24), ((965, 678), (1112, 862), 26)]
mill = []
for (a, b, w) in grooves:
    a, b = np.array(a, float) * T, np.array(b, float) * T
    d = (b - a) / np.linalg.norm(b - a); n = np.array([-d[1], d[0]]) * w * T / 2
    ang = np.linspace(0, np.pi, 8)
    poly = [a + n, b + n] + [b + n * np.cos(t) + d * np.linalg.norm(n) * np.sin(t) for t in ang] + \
           [b - n, a - n] + [a - n * np.cos(t) - d * np.linalg.norm(n) * np.sin(t) for t in ang]
    mill.append(flat(poly))
mill.append(flat(np.array([(790, 510), (910, 510), (915, 630), (795, 632)], float) * T))

about = open(P + "work/about.html").read() if os.path.exists(P + "work/about.html") else "<h2>The Shabaka Stone</h2>"
data = {
    "image": {"w": 11448, "h": 7452}, "home": [700, 420, 11150, 7250],
    "units": units, "signs": [s for s in signs], "order": [u["id"] for u in units],
    "sections": [{"name": n, "units": [u for u in us if u in {x["id"] for x in units}], "blurb": b} for n, us, b in SECTIONS],
    "signlist": signlist, "breasted": breasted, "mill": mill, "outline": json.load(open(P + "work/stone_outline.json")),
    "rules": json.load(open(P + "work/rules.json")) if os.path.exists(P + "work/rules.json") else [], "stats": stats, "about_html": about,
}
json.dump(data, open(OUT + "stone.json", "w"), ensure_ascii=False, separators=(",", ":"))
print(len(units), "units,", len(signs), "signs", stats, f"{os.path.getsize(OUT + 'stone.json') / 1e6:.1f} MB")
