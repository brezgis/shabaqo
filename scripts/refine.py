"""Local refinement of the plate->photo registration.

Warps the photo's edge energy into plate coordinates with the global H, then
runs translation-only ECC on overlapping patches. Patch shifts are filtered
and smoothed into a dense displacement field D (plate px), so that
    photo_xy = H( p + D(p) ).
Writes work/disp_field.npz (dx, dy at 1/8 plate res).
"""
import json
import cv2
import numpy as np
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
H = np.array(json.load(open(P + "work/H_plate_to_photo.json"))["H"])
plate = (cv2.imread(P + "work/breasted_plate_mask.png", 0) > 127).astype(np.float32)
plate[2345:] = 0
plate[:, 3755:] = 0
dmg = cv2.imread(P + "work/damage_mask.png", 0) > 0
ph = cv2.imread(P + "raw/commons_11448.jpg", 0).astype(np.float32)
mu = cv2.GaussianBlur(ph, (0, 0), 40)
sd = np.sqrt(cv2.GaussianBlur((ph - mu) ** 2, (0, 0), 40)) + 4
z = (ph - mu) / sd
e = np.sqrt(cv2.Sobel(z, cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(z, cv2.CV_32F, 0, 1) ** 2)
Hh, Ww = plate.shape
edge = cv2.warpPerspective(e, np.linalg.inv(H), (Ww, Hh), flags=cv2.INTER_AREA | cv2.WARP_FILL_OUTLIERS)

import sys
CC_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.25
sig = 2.0
tpl_all = cv2.GaussianBlur(plate, (0, 0), sig)
inp_all = cv2.GaussianBlur(edge, (0, 0), sig)

pts, shifts, ccs = [], [], []
ERR, ALL = [], []
R, step = 140, 90
crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
for cy in range(360, 2345, step):
    for cx in range(30, 3750, step):
        y0, y1, x0, x1 = cy - R, cy + R, cx - R, cx + R
        if y0 < 0 or x0 < 0 or y1 > Hh or x1 > Ww:
            continue
        t = tpl_all[y0:y1, x0:x1]
        if plate[y0:y1, x0:x1].mean() < 0.03 or dmg[y0:y1, x0:x1].mean() > 0.25:
            continue
        # search in a padded window
        pad = 24
        if y0 - pad < 0 or x0 - pad < 0 or y1 + pad > Hh or x1 + pad > Ww:
            continue
        W = np.eye(2, 3, dtype=np.float32)
        W[0, 2] = pad; W[1, 2] = pad
        try:
            cc, W = cv2.findTransformECC(t, inp_all[y0 - pad:y1 + pad, x0 - pad:x1 + pad], W,
                                         cv2.MOTION_TRANSLATION, crit, None, 5)
        except cv2.error as ex:
            ERR.append(str(ex)[-60:]); continue
        dx, dy = W[0, 2] - pad, W[1, 2] - pad
        ALL.append((cc, dx, dy))
        if abs(dx) > 18 or abs(dy) > 18 or cc < CC_MIN:
            continue
        pts.append((cx, cy)); shifts.append((dx, dy)); ccs.append(cc)

print('errors', len(ERR), ERR[:2]); A_=np.array(ALL); print('cc pct', np.percentile(A_[:,0],[10,50,90]), 'big shift', (np.abs(A_[:,1:])>18).any(1).sum())
pts = np.array(pts, float); shifts = np.array(shifts, float)
print(len(pts), "patches; median |d| =", np.median(np.linalg.norm(shifts, axis=1)))
# reject local outliers vs neighbours' median
keep = np.ones(len(pts), bool)
for i in range(len(pts)):
    nb = np.linalg.norm(pts - pts[i], axis=1) < 260
    med = np.median(shifts[nb], axis=0)
    if np.linalg.norm(shifts[i] - med) > 4:
        keep[i] = False
pts, shifts = pts[keep], shifts[keep]
print(len(pts), "after outlier rejection")

f = 8
gy, gx = np.mgrid[0:Hh:f, 0:Ww:f]
D = []
for k in range(2):
    lin = griddata(pts, shifts[:, k], (gx, gy), method="linear")
    near = griddata(pts, shifts[:, k], (gx, gy), method="nearest")
    v = np.where(np.isnan(lin), near, lin)
    D.append(gaussian_filter(v, 6))
np.savez(P + "work/disp_field.npz", dx=D[0].astype(np.float32), dy=D[1].astype(np.float32), f=f)
print("field range dx", D[0].min(), D[0].max(), "dy", D[1].min(), D[1].max())
