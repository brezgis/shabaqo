"""Build tracing sheets for the per-column tracing agents.

For every column (and chunks of the two horizontal lines) renders panels of
the same A2-frame region:  PHOTO (CLAHE) | RELIEF-main | RELIEF-native-avg |
BREASTED overlay with numbered reference boxes.  Rulers are in A2 px, so
agents can give coordinates for signs Breasted missed.

Outputs work/sheets/<id>_<k>.png and work/sheets/index.json, plus
work/breasted_boxes_a2.json (reference boxes B<n> in A2 coords).
"""
import json
import os
import sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from geom import P, plate_to_a2, box_plate_to_a2, H  # noqa: E402

cv2.setNumThreads(4)
OUT = P + "work/sheets/"
os.makedirs(OUT, exist_ok=True)

photo = cv2.imread(P + "work/mp/main_reg.jpg")
gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
photo_v = cv2.createCLAHE(2.5, (32, 32)).apply(gray)
rel_main = cv2.imread(P + "work/mp/main_relief.png", 0)
rel_avg = cv2.imread(P + "work/mp/relief_signed3.png", 0)

# Breasted ink warped into A2 frame (red overlay on a dim photo)
F = np.load(P + "work/disp_field.npz")
plate = cv2.imread(P + "work/breasted_plate_mask.png", 0)
plate[2345:] = 0
plate[:, 3755:] = 0
Hh, Ww = plate.shape
dx = cv2.resize(F["dx"], (Ww, Hh)); dy = cv2.resize(F["dy"], (Ww, Hh))
gy, gx = np.mgrid[0:Hh, 0:Ww].astype(np.float32)
plate_shift = cv2.remap(plate, gx - dx, gy - dy, cv2.INTER_LINEAR)
A2H, A2W = gray.shape
ink_a2 = cv2.warpPerspective(plate_shift, np.diag([0.5, 0.5, 1]) @ H, (A2W, A2H), flags=cv2.INTER_AREA)

glyphs = json.load(open(P + "work/glyphs.json"))
bboxes = []
for g in glyphs:
    b = box_plate_to_a2(g["box"])
    bboxes.append({"id": f"B{g['id']}", "a2": [round(v, 1) for v in b], "plate": g["box"]})
json.dump(bboxes, open(P + "work/breasted_boxes_a2.json", "w"))

SC = 1.6  # sheet upscaling


def panel_set(x0, y0, x1, y1, boxes_here):
    def up(img):
        return cv2.resize(img, None, fx=SC, fy=SC, interpolation=cv2.INTER_CUBIC)
    a = cv2.cvtColor(up(photo_v[y0:y1, x0:x1]), cv2.COLOR_GRAY2BGR)
    b = cv2.cvtColor(up(rel_main[y0:y1, x0:x1]), cv2.COLOR_GRAY2BGR)
    c = cv2.cvtColor(up(rel_avg[y0:y1, x0:x1]), cv2.COLOR_GRAY2BGR)
    d = (cv2.cvtColor(up(photo_v[y0:y1, x0:x1]), cv2.COLOR_GRAY2BGR) * 0.45).astype(np.uint8)
    ink = up(ink_a2[y0:y1, x0:x1]) > 70
    d[ink] = (40, 40, 255)
    for bx in boxes_here:
        X0, Y0, X1, Y1 = [(v - o) * SC for v, o in zip(bx["a2"], (x0, y0, x0, y0))]
        cv2.rectangle(d, (int(X0), int(Y0)), (int(X1), int(Y1)), (0, 220, 0), 1)
        cv2.putText(d, bx["id"][1:], (int(X1) + 2, int((Y0 + Y1) / 2) + 4), cv2.FONT_HERSHEY_SIMPLEX,
                    0.38, (80, 255, 255), 1, cv2.LINE_AA)
    return a, b, c, d


def label(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 18), (0, 0, 0), -1)
    cv2.putText(img, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def vruler(y0, y1, h):
    r = np.full((h, 58, 3), 255, np.uint8)
    for y in range((y0 // 25 + 1) * 25, y1, 25):
        Y = int((y - y0) * SC)
        L = 14 if y % 100 == 0 else 7
        cv2.line(r, (58 - L, Y), (57, Y), (0, 0, 0), 1)
        if y % 100 == 0:
            cv2.putText(r, str(y), (2, Y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 200), 1, cv2.LINE_AA)
    return r


def hruler(x0, x1, w):
    r = np.full((22, w, 3), 255, np.uint8)
    for x in range((x0 // 25 + 1) * 25, x1, 25):
        X = int((x - x0) * SC)
        cv2.line(r, (X, 0), (X, 6 if x % 100 else 12), (0, 0, 0), 1)
        if x % 50 == 0:
            cv2.putText(r, str(x), (X + 2, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (0, 0, 200), 1, cv2.LINE_AA)
    return r


index = {}
cols = json.load(open(P + "work/columns.json"))
top_plate, bot_plate = 596, 2342
for i, c in enumerate(cols):
    half = 34 if c["label"] != "48-52" else 135
    xs = [c["cx"] - half, c["cx"] + half]
    tl = plate_to_a2([[xs[0], top_plate], [xs[1], top_plate], [xs[0], bot_plate], [xs[1], bot_plate]])
    x0 = int(tl[:, 0].min()) - 22; x1 = int(tl[:, 0].max()) + 22
    y0 = int(tl[:, 1].min()) - 10; y1 = int(tl[:, 1].max()) + 10
    # boxes whose centre falls in this column's plate x-range
    here = [b for b in bboxes
            if xs[0] - 4 <= (b["plate"][0] + b["plate"][2]) / 2 <= xs[1] + 4
            and b["plate"][1] >= top_plate - 5]
    nseg = 4
    edges = np.linspace(y0, y1, nseg + 1).astype(int)
    files = []
    for k in range(nseg):
        s0, s1 = edges[k] - 15, edges[k + 1] + 15
        a, b, cc, d = panel_set(x0, s0, x1, s1, [h for h in here if s0 <= (h["a2"][1] + h["a2"][3]) / 2 <= s1])
        gap = np.full((a.shape[0], 6, 3), 255, np.uint8)
        row = np.hstack([vruler(s0, s1, a.shape[0]), label(a, "photo"), gap, label(b, "relief"), gap,
                         label(cc, "relief-native"), gap, label(d, "Breasted ref")])
        ruler = np.hstack([np.full((22, 58, 3), 255, np.uint8), hruler(x0, x1, a.shape[1]),
                           np.full((22, row.shape[1] - 58 - a.shape[1], 3), 255, np.uint8)])
        img = np.vstack([ruler, row])
        fn = f"col{c['label']}_{k + 1}of{nseg}.png"
        cv2.imwrite(OUT + fn, img)
        files.append(fn)
    index[c["label"]] = {"a2_bounds": [x0, y0, x1, y1], "files": files, "breasted_box_ids": [h["id"] for h in here]}

# horizontal lines 1 and 2
tl = plate_to_a2([[22, 350], [3752, 350], [22, 535], [3752, 535]])
X0, X1 = int(tl[:, 0].min()) - 10, int(tl[:, 0].max()) + 10
Y0, Y1 = int(tl[:, 1].min()) - 12, int(tl[:, 1].max()) + 12
edges = np.linspace(X0, X1, 13).astype(int)
files = []
for k in range(12):
    s0, s1 = edges[k] - 20, edges[k + 1] + 20
    here = [b for b in bboxes if b["plate"][3] < 545 and s0 <= (b["a2"][0] + b["a2"][2]) / 2 <= s1]
    a, b, cc, d = panel_set(s0, Y0, s1, Y1, here)
    stack = [hruler(s0, s1, a.shape[1])]
    for im, t in [(a, "photo"), (b, "relief"), (cc, "relief-native"), (d, "Breasted ref")]:
        stack.append(np.hstack([vruler(Y0, Y1, im.shape[0]), label(im, t)])[:, 58:])
        stack.append(np.full((5, a.shape[1], 3), 255, np.uint8))
    img = np.vstack(stack)
    img = np.hstack([np.vstack([np.full((22, 58, 3), 255, np.uint8)] +
                               [np.vstack([vruler(Y0, Y1, a.shape[0]), np.full((5, 58, 3), 255, np.uint8)])] * 4), img])
    fn = f"lines12_{k + 1:02d}of12.png"
    cv2.imwrite(OUT + fn, img)
    files.append(fn)
index["lines1-2"] = {"a2_bounds": [X0, Y0, X1, Y1], "files": files}
json.dump(index, open(OUT + "index.json", "w"), indent=1)
print(len(index), "units;", sum(len(v["files"]) for v in index.values()), "sheets")
