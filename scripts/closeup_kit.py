"""Add closeup.png to sign kits that lie inside the 2024-10-03w close-up photograph.

raw/commons_2024w.jpg (Djehouty, CC BY-SA 4.0, Canon 60D, 44 mm) shows the top of columns 54-59 at about
3.9 px per FULL px, i.e. ~8x the real resolution of the main photograph (whose 11448 px are a 2x AI upscale).
work/H_closeup2024w_to_full.npy maps close-up px -> FULL px (SIFT + RANSAC against the un-upscaled main
frame raw/commons_5724_original.jpg; 215 inliers, rms 1.3 FULL px).

closeup.png has the kit crop's geometry (meta.json "crop"), so trace coordinates apply unchanged. A small
translation is fitted per kit against photo.png (ECC) and stored in meta.json "closeup".

usage: closeup_kit.py <kit_dir> [...]      closeup_kit.py --list   (rids fully inside the close-up)
"""
import json
import sys

import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
H = np.load(P + "work/H_closeup2024w_to_full.npy")
W_, H_ = 3456, 5184


def inside(box, margin=0):
    poly = cv2.perspectiveTransform(np.float32([[0, 0], [W_, 0], [W_, H_], [0, H_]]).reshape(-1, 1, 2), H).reshape(-1, 2)
    x0, y0, x1, y1 = box
    return all(cv2.pointPolygonTest(poly, (float(x), float(y)), True) >= margin for x, y in [(x0, y0), (x1, y1), (x0, y1), (x1, y0)])


def build(d, img):
    d = d.rstrip("/") + "/"
    meta = json.load(open(d + "meta.json"))
    c = meta["crop"]
    ox, oy = c["origin_full"]
    sc = c["scale"]
    w, h = c["size"]
    T = np.array([[1 / sc, 0, ox], [0, 1 / sc, oy], [0, 0, 1]])
    M = np.linalg.inv(H) @ T                      # crop px -> close-up px
    out = cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
    valid = cv2.warpPerspective(np.full(img.shape[:2], 255, np.uint8), M, (w, h), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
    shift = [0.0, 0.0]
    cc = None
    ph = cv2.imread(d + "photo.png", 0)
    if ph is not None and ph.shape == out.shape[:2] and valid.mean() > 200:
        a = cv2.GaussianBlur(ph, (0, 0), 3).astype(np.float32)
        b = cv2.GaussianBlur(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), (0, 0), 3).astype(np.float32)
        try:
            cc, Wm = cv2.findTransformECC(a, b, np.eye(2, 3, dtype=np.float32), cv2.MOTION_TRANSLATION,
                                          (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
            if abs(Wm[0, 2]) < 15 and abs(Wm[1, 2]) < 15:
                shift = [float(Wm[0, 2]), float(Wm[1, 2])]
                S = np.array([[1, 0, shift[0]], [0, 1, shift[1]], [0, 0, 1]])
                out = cv2.warpPerspective(img, M @ S, (w, h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)
        except cv2.error:
            pass
    cv2.imwrite(d + "closeup.png", out)
    meta["closeup"] = {"src": "raw/commons_2024w.jpg", "shift_crop_px": [round(s, 1) for s in shift], "ecc": None if cc is None else round(float(cc), 3),
                       "covered": round(float(valid.mean() / 255), 3)}
    json.dump(meta, open(d + "meta.json", "w"), ensure_ascii=False, indent=1)
    return meta["closeup"]


if __name__ == "__main__":
    if sys.argv[1] == "--list":
        L = json.load(open(P + "work/signlist_roth.json"))
        print(" ".join(e["rid"] for es in L["units"].values() for e in es if e.get("box_full") and inside(e["box_full"])))
    else:
        img = cv2.imread(P + "raw/commons_2024w.jpg")
        for d in sys.argv[2 if sys.argv[1] == "--" else 1:]:
            print(d, build(d, img))
