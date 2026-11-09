"""Refine the stone outline from the photo: dark basalt vs light wall, searched in a band around
work/stone_outline.json. Writes a fine polygon (full-image px) + a check image."""
import json, sys, cv2, numpy as np
S = sys.argv[1]; P = "/home/anna/projects/shabaka-stone/"
im = cv2.imread(S + "/photo_L12.jpg"); sc = 4.0                       # L12 = full/4
H, W = im.shape[:2]
o = np.array(json.load(open(P + "work/stone_outline.json")), float).reshape(-1, 2) / sc
coarse = np.zeros((H, W), np.uint8); cv2.fillPoly(coarse, [o.round().astype(np.int32)], 255)
band = 30                                                             # L12 px = 120 full px
k = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
inner = cv2.erode(coarse, k(band)); outer = cv2.dilate(coarse, k(band))
# GrabCut seeded by the coarse outline: well inside = stone, well outside = wall, band = undecided.
# (a global brightness threshold fails: the gallery light makes the top of the stone nearly as bright as the wall)
gc = np.full((H, W), cv2.GC_BGD, np.uint8)
gc[outer > 0] = cv2.GC_PR_BGD; gc[coarse > 0] = cv2.GC_PR_FGD; gc[inner > 0] = cv2.GC_FGD
bgm = np.zeros((1, 65), np.float64); fgm = np.zeros((1, 65), np.float64)
cv2.grabCut(im, gc, None, bgm, fgm, 6, cv2.GC_INIT_WITH_MASK)
m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
thr = "grabcut"
# keep the top edge as in the coarse outline (brackets overlap it), i.e. nothing above coarse top
top = int(o[:, 1].min()); m[:max(0, top - 2), :] = 0
m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k(3)); m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k(6))
n, lab_, st, _ = cv2.connectedComponentsWithStats(m)
m = np.where(lab_ == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]), 255, 0).astype(np.uint8)
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k(12))
# fill holes (the millstone socket etc. are inside)
ff = m.copy(); cv2.floodFill(ff, None, (0, 0), 255); m = m | cv2.bitwise_not(ff)
cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
c = max(cs, key=cv2.contourArea)
poly = cv2.approxPolyDP(c, 0.6, True).reshape(-1, 2).astype(float)   # ~2.4 full px tolerance
full = (poly * sc).round(1)
json.dump(full.flatten().tolist(), open(S + "/cutout/stone_outline_fine.json", "w"))
print("threshold L", thr, "points", len(full), "area ratio vs coarse", round(cv2.contourArea(c) / cv2.contourArea(o.astype(np.float32)), 4))
vis = im.copy(); vis[m == 0] = (vis[m == 0] * 0.25 + np.array([40, 120, 40]) * 0.75).astype(np.uint8)
cv2.polylines(vis, [o.round().astype(np.int32)], True, (0, 0, 255), 1)
cv2.imwrite(S + "/cutout/mask_check.jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
for nm, (x0, y0, x1, y1) in {"tl": (0, 0, 800, 650), "tr": (2062, 0, 2862, 650), "bl": (0, 1250, 800, 1863), "br": (2062, 1250, 2862, 1863), "l": (0, 650, 600, 1250)}.items():
    cv2.imwrite(S + f"/cutout/mc_{nm}.jpg", vis[y0:y1, x0:x1])
