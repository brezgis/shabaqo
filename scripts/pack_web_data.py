"""Slim the viewer data for the web: keep only what web/app.js reads, and move Breasted's copy (1.6 MB of
polygons, only drawn when its overlay is switched on) into its own file, fetched on first use.

usage: python3 scripts/pack_web_data.py <stone.json in> <out dir>
       writes <out dir>/stone.json and <out dir>/breasted.json (the input is not modified)

The full data (trace notes, per-unit notes and translations, Breasted issues, ...) stays in the input file.
"""
import json
import os
import sys

SIGN_KEYS = ("sid", "alias", "unit", "gardiner", "alt", "uni", "box", "mirror", "strokes", "status")
UNIT_KEYS = ("id", "title", "short", "section", "summary", "words", "signs", "bounds", "preservation")
TOP_DROP = ("breasted", "about_html", "mill", "rules")


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
    a = write(os.path.join(out, "stone.json"), slim)
    b = write(os.path.join(out, "breasted.json"), D.get("breasted", []))
    print(f"{src} ({os.path.getsize(src) / 1e6:.2f} MB) -> stone.json {a / 1e6:.2f} MB + breasted.json {b / 1e6:.2f} MB in {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
