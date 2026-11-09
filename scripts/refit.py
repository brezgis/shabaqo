"""Per-sign refit of Breasted's drawing onto the stone.

For each reference sign box, brute-force a small translation + scale of the
sign's own ink so that it best matches the photo's carved-edge energy
(|relief|, gated by native-photo support). A mild prior keeps signs near the
global registration when the photo is uninformative.
"""
import cv2
import numpy as np

from geom import P, H

cv2.setNumThreads(4)
_cache = {}


def _load():
    if _cache:
        return
    plate = cv2.imread(P + "work/rules_removed.png", 0)
    F = np.load(P + "work/disp_field.npz")
    Hh, Ww = plate.shape
    dx = cv2.resize(F["dx"], (Ww, Hh)); dy = cv2.resize(F["dy"], (Ww, Hh))
    gy, gx = np.mgrid[0:Hh, 0:Ww].astype(np.float32)
    shifted = cv2.remap(plate, gx - dx, gy - dy, cv2.INTER_LINEAR)
    rel = cv2.imread(P + "work/relief_full.png", 0)
    _cache["ink"] = cv2.warpPerspective(shifted, H, (rel.shape[1], rel.shape[0]), flags=cv2.INTER_LINEAR)
    e = np.abs(rel.astype(np.float32) - 128)
    nat = cv2.imread(P + "work/mp/relief_signed3.png", 0)
    nat = np.abs(cv2.resize(nat, (rel.shape[1], rel.shape[0])).astype(np.float32) - 128)
    _cache["energy"] = cv2.GaussianBlur(e * np.sqrt(nat / (nat.mean() + 1e-3)), (0, 0), 2.0)


def ink_full():
    _load()
    return _cache["ink"]


def refit(box_full, search=14, step=2, scales=(0.9, 0.95, 1.0, 1.05, 1.1)):
    """Return (dx, dy, s, score, gain) for the sign in box_full (FULL px).
    Template-matches the sign's own (globally warped) ink against carved-edge
    energy within +-search px; a mild distance prior keeps uninformative signs put."""
    _load()
    ink, en = _cache["ink"], _cache["energy"]
    x0, y0, x1, y1 = [int(round(v)) for v in box_full]
    Hh, Ww = en.shape
    g = ink[max(y0 - 3, 0):y1 + 3, max(x0 - 3, 0):x1 + 3].astype(np.float32) / 255
    if g.size == 0 or g.sum() < 5:
        return 0, 0, 1.0, 0.0, 0.0
    g = cv2.GaussianBlur(g, (0, 0), 2.0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    best = (-1e9, 0, 0, 1.0); base = None
    for s in scales:
        t = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
        th, tw = t.shape
        X0 = int(round(cx - tw / 2)) - search; Y0 = int(round(cy - th / 2)) - search
        if X0 < 0 or Y0 < 0 or X0 + tw + 2 * search > Ww or Y0 + th + 2 * search > Hh:
            continue
        win = en[Y0:Y0 + th + 2 * search, X0:X0 + tw + 2 * search]
        if t.std() < 1e-4 or win.std() < 1e-4:
            continue
        r = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED)
        yy, xx = np.mgrid[0:r.shape[0], 0:r.shape[1]]
        d = np.hypot(xx - search, yy - search)
        r = r - 0.004 * d - 0.25 * abs(np.log(s))
        iy, ix = np.unravel_index(np.argmax(r), r.shape)
        if s == 1.0:
            base = float(r[search, search])
        if r[iy, ix] > best[0]:
            best = (float(r[iy, ix]), ix - search, iy - search, s)
    sc, dx, dy, s = best
    if sc == -1e9:
        return 0, 0, 1.0, 0.0, 0.0
    return dx, dy, s, sc, sc - (base if base is not None else sc)
