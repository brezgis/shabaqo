"""Photo-derived stroke extraction for one sign region.

Incised strokes under the gallery's top light show as a shadow band (upper
wall) paired with a highlight band (lower wall). We take |relief| on the
upscaled photo, require support from the native-photo relief (so Topaz
upscaling can't invent strokes), fuse the shadow/highlight pairs, and return
outline polygons in FULL-photo pixels.
"""
import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
_rel = None
_nat = None


def _load():
    global _rel, _nat
    if _rel is None:
        _rel = cv2.imread(P + "work/relief_full.png", 0)
        _nat = cv2.imread(P + "work/mp/relief_signed3.png", 0)  # A2 frame


def extract(box_full, pad=6, k_sigma=1.25):
    """box_full: [x0,y0,x1,y1] in FULL px. Returns (polys, mask, origin)."""
    _load()
    H, W = _rel.shape
    x0 = max(int(box_full[0]) - pad, 0); y0 = max(int(box_full[1]) - pad, 0)
    x1 = min(int(box_full[2]) + pad, W); y1 = min(int(box_full[3]) + pad, H)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return [], None, (x0, y0)
    d = np.abs(_rel[y0:y1, x0:x1].astype(np.float32) - 128)
    # threshold relative to a wider neighbourhood so faint and deep signs both work
    X0 = max(x0 - 60, 0); Y0 = max(y0 - 60, 0)
    ctx = np.abs(_rel[Y0:min(y1 + 60, H), X0:min(x1 + 60, W)].astype(np.float32) - 128)
    t = np.median(ctx) + k_sigma * 1.4826 * np.median(np.abs(ctx - np.median(ctx))) * 1.6
    m = (d > t).astype(np.uint8)
    # native support: |native relief| above its own local threshold, dilated
    nx0, ny0, nx1, ny1 = x0 // 2, y0 // 2, (x1 + 1) // 2, (y1 + 1) // 2
    n = np.abs(_nat[ny0:ny1, nx0:nx1].astype(np.float32) - 128)
    n = cv2.resize(n, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
    tn = np.percentile(n, 55)
    sup = cv2.dilate((n > tn).astype(np.uint8), np.ones((7, 7), np.uint8))
    m &= sup
    # fuse shadow/highlight pairs into one stroke, drop specks
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    nlab, lab, st, _ = cv2.connectedComponentsWithStats(m)
    area_min = max(18, 0.004 * m.size)
    keep = np.zeros_like(m)
    for i in range(1, nlab):
        if st[i, 4] >= area_min:
            keep[lab == i] = 1
    cs, _ = cv2.findContours(keep, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in cs:
        if cv2.contourArea(c) < 6:
            continue
        a = cv2.approxPolyDP(c, 0.9, True)[:, 0, :]
        polys.append((a + [x0, y0]).tolist())
    return polys, keep, (x0, y0)
