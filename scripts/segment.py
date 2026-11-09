"""Segment Breasted's 1901 plate (ZÄS 39, Taf. I-II) into sign boxes.

Input:  work/breasted_plate_mask.png  (1-bit, ink = white)
Output: work/rules_removed.png, work/glyphs.json (boxes in plate px)
"""
import json
import cv2
import numpy as np

W = "/home/anna/projects/shabaka-stone/work/"
m = cv2.imread(W + "breasted_plate_mask.png", 0)
ink = (m > 127).astype(np.uint8)
H, Wd = ink.shape
ink[2345:] = 0        # caption / next page
ink[:, 3755:] = 0     # page edge

# column number row and gutters are rules, not signs
def opened(k):
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))

vert = opened((1, 90))
horiz = opened((110, 1))
# dashed rules: close vertically first, then keep only long thin runs
dash = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 22)))
dash = cv2.morphologyEx(dash, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 160)))
dash &= ink
rules = cv2.dilate(vert | horiz | dash, np.ones((3, 3), np.uint8))
# but keep vertical strokes that are part of signs: a rule is ≤ 5px wide
clean = ink & (1 - rules)

# hatched damage (millstone grooves + socket): dense big blobs
blur = cv2.blur(clean.astype(np.float32), (41, 41))
damage = (blur > 0.33).astype(np.uint8)
damage = cv2.morphologyEx(damage, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
damage = cv2.dilate(damage, np.ones((15, 15), np.uint8))
n, lab, st, _ = cv2.connectedComponentsWithStats(damage)
dmask = np.zeros_like(damage)
for i in range(1, n):
    if st[i, 4] > 9000:
        dmask[lab == i] = 1
clean[dmask == 1] = 0
cv2.imwrite(W + "damage_mask.png", dmask * 255)
cv2.imwrite(W + "rules_removed.png", clean * 255)

# components -> sign clusters. Breasted stipples worn areas with dots, so
# small specks never seed a merge: they only attach to a nearby real stroke.
n, lab, st, cen = cv2.connectedComponentsWithStats(clean)
big, small = [], []
for i in range(1, n):
    x, y, w, h, a = (int(v) for v in st[i])
    (big if a >= 40 else small).append([x, y, x + w, y + h, a])

def overlap_frac(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0]); iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    sm = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / max(sm, 1)

# merge strokes whose boxes substantially overlap (a sign broken in pieces)
changed = True
while changed:
    changed = False
    out = []
    for b in big:
        for o in out:
            if overlap_frac(o, b) > 0.35:
                o[0] = min(o[0], b[0]); o[1] = min(o[1], b[1])
                o[2] = max(o[2], b[2]); o[3] = max(o[3], b[3]); o[4] += b[4]
                changed = True
                break
        else:
            out.append(list(b))
    big = out

# attach specks that sit inside or touch a sign box; drop the rest (stipple)
for s_ in small:
    cx, cy = (s_[0] + s_[2]) / 2, (s_[1] + s_[3]) / 2
    for o in big:
        if o[0] - 3 <= cx <= o[2] + 3 and o[1] - 3 <= cy <= o[3] + 3 and s_[4] >= 12:
            o[4] += s_[4]
            break
boxes = big
boxes = [b for b in boxes if b[4] >= 25 and (b[2] - b[0]) < 140 and (b[3] - b[1]) < 160]
boxes.sort(key=lambda b: (b[0] // 40, b[1]))
glyphs = [{"id": i, "box": [int(v) for v in b[:4]], "area": int(b[4])} for i, b in enumerate(boxes)]
json.dump(glyphs, open(W + "glyphs.json", "w"))
print(len(glyphs), "sign clusters")
