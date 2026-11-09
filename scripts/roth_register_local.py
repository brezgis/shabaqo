"""Locally refine the registration of Rothöhler's facsimile (Tafel 1) onto the main photo.

work/H_roth_to_photo.json is one global homography (plate px -> FULL photo px); it lands Rothöhler's
signs near the right carvings but off by up to tens of px in places. Here his ink, warped by H into the
A2 frame (half resolution), is aligned tile by tile to the photo's carved-edge energy (normalised cross-correlation, translation only, 384-px tiles at 192-px stride). Outlier shifts are replaced by their neighbours' median, the field
is smoothed and applied, and the result is written as one image in the photo's A2 frame:

  work/roth_photo_a2.png   Rothöhler's ink (255 = ink) in A2 px, aligned to the carvings
  work/roth_shift_a2.npz   the per-tile shifts (for inspection)

usage: nice python3 scripts/roth_register_local.py
"""
import json
import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
TILE, STEP, MAXS, MINCC = 384, 192, 40.0, 0.15


def edge_energy(g):   # same as scripts/register.py
    g = g.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 25)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 25)) + 4
    z = (g - mu) / sd
    gx = cv2.Sobel(z, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(z, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


H = np.array(json.load(open(P + "work/H_roth_to_photo.json"))["H"])
plate = cv2.imread(P + "raw/refs/rothoehler2005/tafel1-000.jpg", 0)
photo = cv2.imread(P + "raw/commons_11448.jpg", 0)
A2 = (photo.shape[1] // 2, photo.shape[0] // 2)
half = np.diag([0.5, 0.5, 1.0])
ink = (255 - cv2.warpPerspective(plate, half @ H, A2, flags=cv2.INTER_AREA, borderValue=255)).astype(np.float32) / 255
ph = edge_energy(cv2.resize(photo, A2, interpolation=cv2.INTER_AREA))
ph /= np.percentile(ph, 99.5)
tpl_all, inp_all = cv2.GaussianBlur(ink, (0, 0), 3), cv2.GaussianBlur(ph, (0, 0), 3)

W, Hh = A2
gx = list(range(0, W - TILE + 1, STEP)); gy = list(range(0, Hh - TILE + 1, STEP))
sh = np.full((len(gy), len(gx), 2), np.nan, np.float32)
for j, y in enumerate(gy):
    for i, x in enumerate(gx):
        t = tpl_all[y:y + TILE, x:x + TILE]
        if (ink[y:y + TILE, x:x + TILE] > 0.5).mean() < 0.015:
            continue                          # too little of Rothöhler's ink here to align on
        # normalised cross-correlation of the tile (blurred ink) over a search window MAXS px wider
        m = int(MAXS)
        y0, x0 = max(0, y - m), max(0, x - m)
        inp = inp_all[y0:min(Hh, y + TILE + m), x0:min(W, x + TILE + m)]
        r = cv2.matchTemplate(inp, t, cv2.TM_CCOEFF_NORMED)
        _, cc, _, (px, py) = cv2.minMaxLoc(r)
        # confidence: the peak must stand out from the rest of the correlation surface
        mu, sd = float(r.mean()), float(r.std()) + 1e-6
        d = np.array([x0 + px - x, y0 + py - y], np.float32)
        if cc >= MINCC and (cc - mu) / sd >= 3.0 and np.all(np.abs(d) <= MAXS):
            sh[j, i] = d

# outliers: replace shifts that differ from their 3x3 neighbourhood median by > 8 px
fixed = sh.copy()
for j in range(sh.shape[0]):
    for i in range(sh.shape[1]):
        nb = sh[max(0, j - 1):j + 2, max(0, i - 1):i + 2].reshape(-1, 2)
        nb = nb[~np.isnan(nb[:, 0])]
        if len(nb) >= 3:
            med = np.median(nb, 0)
            if np.isnan(sh[j, i, 0]) or np.hypot(*(sh[j, i] - med)) > 8:
                fixed[j, i] = med
# fill remaining gaps with the global median, smooth, upsample to a dense field (tile centres)
gm = np.nanmedian(fixed.reshape(-1, 2), 0)
fixed = np.where(np.isnan(fixed), gm, fixed)
fixed = cv2.GaussianBlur(fixed, (0, 0), 1.0)
cx0, cy0 = TILE / 2, TILE / 2
dense = cv2.resize(fixed, (int(len(gx) * STEP), int(len(gy) * STEP)), interpolation=cv2.INTER_CUBIC)
field = np.zeros((Hh, W, 2), np.float32)
oy, ox = int(cy0 - STEP / 2), int(cx0 - STEP / 2)
field[:, :] = gm
h_, w_ = min(Hh - oy, dense.shape[0]), min(W - ox, dense.shape[1])
field[oy:oy + h_, ox:ox + w_] = dense[:h_, :w_]
# extend edges outward
field[:oy] = field[oy]; field[oy + h_:] = field[oy + h_ - 1]
field[:, :ox] = field[:, ox:ox + 1]; field[:, ox + w_:] = field[:, ox + w_ - 1:ox + w_]
# ink at template x lands at photo x + d  ->  aligned(y) = ink(y - d(y))
yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
aligned = cv2.remap(ink, xx - field[..., 0], yy - field[..., 1], cv2.INTER_LINEAR, borderValue=0)
cv2.imwrite(P + "work/roth_photo_a2.png", (np.clip(aligned, 0, 1) * 255).astype(np.uint8))
np.savez_compressed(P + "work/roth_shift_a2.npz", raw=sh, fixed=fixed, gx=np.array(gx), gy=np.array(gy), tile=TILE)
ok = ~np.isnan(sh[..., 0])
mag = np.hypot(sh[ok][:, 0], sh[ok][:, 1])
print(f"tiles aligned {ok.sum()}/{sh[..., 0].size}; shift |d| A2 px: median {np.median(mag):.1f}, p90 {np.percentile(mag, 90):.1f}, max {mag.max():.1f}")
