"""Column-context image for a sign kit: the sign among its neighbours, at lower zoom.
usage: context_img.py <sid> [sid...]   -> work/signs/<sid>/context.png
"""
import json, sys
import cv2
P = "/home/anna/projects/shabaka-stone/"
D = json.load(open(P + "web/data/stone.json"))
by = {s["sid"]: s for s in D["signs"]}
g = cv2.imread(P + "raw/commons_11448.jpg", 0)
for sid in sys.argv[1:]:
    s = by[sid]; b = s["box"]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    x0, x1 = int(cx - 260), int(cx + 260); y0, y1 = int(cy - 420), int(cy + 420)
    c = cv2.cvtColor(cv2.createCLAHE(2.0, (8, 8)).apply(g[y0:y1, x0:x1]), cv2.COLOR_GRAY2BGR)
    for o in D["signs"]:
        ob = o.get("box")
        if not ob or o["unit"] != s["unit"] or ob[2] < x0 or ob[0] > x1 or ob[3] < y0 or ob[1] > y1:
            continue
        col = (0, 255, 0) if o["sid"] == sid else (0, 0, 220)
        cv2.rectangle(c, (int(ob[0] - x0), int(ob[1] - y0)), (int(ob[2] - x0), int(ob[3] - y0)), col, 2 if o["sid"] == sid else 1)
        cv2.putText(c, f'{o["sid"].split(".")[-1]}:{o["gardiner"]}', (int(ob[2] - x0) + 2, int(ob[1] - y0) + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1, cv2.LINE_AA)
    cv2.imwrite(P + f"work/signs/{sid}/context.png", c)
    print(sid)
