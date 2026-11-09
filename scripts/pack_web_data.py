"""Slim the viewer data for the web: keep only what web/app.js reads, and move Breasted's copy (1.6 MB of
polygons, only drawn when its overlay is switched on) into its own file, fetched on first use.

usage: python3 scripts/pack_web_data.py <stone.json in> <out dir>
       writes <out dir>/stone.json and <out dir>/breasted.json (the input is not modified)

The full data (trace notes, per-unit notes and translations, Breasted issues, ...) stays in the input file.

The public edition spells the king Shabaqo; the working data says Shabaka. The name is changed here, in the
prose fields listed in PROSE only, so identifiers, file names and sign data are never touched.
"""
import json
import os
import re
import sys

SIGN_KEYS = ("sid", "alias", "unit", "gardiner", "alt", "uni", "box", "mirror", "strokes", "status")
UNIT_KEYS = ("id", "title", "short", "section", "summary", "words", "signs", "bounds", "preservation")
TOP_DROP = ("breasted", "about_html", "mill", "rules")
NAME = re.compile(r"\bShabaka\b(?![_ ]?Stone)")   # not the stone's own name, nor file names


def shabaqo(t):
    return NAME.sub("Shabaqo", t) if isinstance(t, str) else t


def normalize(slim):
    """Spell the king's name the edition's way in the prose a reader sees: unit summaries, word glosses,
    section blurbs. Changes nothing else."""
    for u in slim.get("units", []):
        u["summary"] = shabaqo(u.get("summary"))
        for w in u.get("words") or []:
            if "gloss" in w:
                w["gloss"] = shabaqo(w["gloss"])
    for s in slim.get("sections", []):
        if "blurb" in s:
            s["blurb"] = shabaqo(s["blurb"])
    return slim


def write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return os.path.getsize(path)


def main(src, out):
    D = json.load(open(src))
    os.makedirs(out, exist_ok=True)
    slim = {k: v for k, v in D.items() if k not in TOP_DROP}
    slim["signs"] = [{k: s[k] for k in SIGN_KEYS if s.get(k) not in (None, "", [])} for s in D["signs"]]
    slim["units"] = [{k: u[k] for k in UNIT_KEYS if k in u} for u in D["units"]]
    slim["lazy"] = {"breasted": "breasted.json"}
    normalize(slim)
    a = write(os.path.join(out, "stone.json"), slim)
    b = write(os.path.join(out, "breasted.json"), D.get("breasted", []))
    print(f"{src} ({os.path.getsize(src) / 1e6:.2f} MB) -> stone.json {a / 1e6:.2f} MB + breasted.json {b / 1e6:.2f} MB in {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
