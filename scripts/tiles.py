"""Deep Zoom (DZI) pyramids for the viewer.

  photo   - main photo, full res (11448 x 7452)
  relief  - local relief of the main photo, full res
  native  - relief averaged from the three non-upscaled photos (A2 res, upsampled)
"""
import math
import os
import sys
import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
WEB = P + "web/tiles/"
TS, OV = 254, 1


def relief_full(gray):
    g = gray.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 60)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 60)) + 3
    z = (g - mu) / sd
    d = cv2.GaussianBlur(z, (0, 0), 2.0) - cv2.GaussianBlur(z, (0, 0), 12)
    return np.clip(128 + d * 80, 0, 255).astype(np.uint8)


def dzi(img, name, q=82):
    h, w = img.shape[:2]
    out = WEB + name + "_files/"
    maxlev = math.ceil(math.log2(max(w, h)))
    cur = img
    for lev in range(maxlev, -1, -1):
        d = out + str(lev) + "/"
        os.makedirs(d, exist_ok=True)
        ch, cw = cur.shape[:2]
        for ty in range(math.ceil(ch / TS)):
            for tx in range(math.ceil(cw / TS)):
                x0 = max(tx * TS - OV, 0); y0 = max(ty * TS - OV, 0)
                x1 = min((tx + 1) * TS + OV, cw); y1 = min((ty + 1) * TS + OV, ch)
                cv2.imwrite(f"{d}{tx}_{ty}.jpg", cur[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, q])
        nw, nh = max(1, math.ceil(cw / 2)), max(1, math.ceil(ch / 2))
        cur = cv2.resize(cur, (nw, nh), interpolation=cv2.INTER_AREA)
    with open(WEB + name + ".dzi", "w") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?><Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
                f'Format="jpg" Overlap="{OV}" TileSize="{TS}"><Size Width="{w}" Height="{h}"/></Image>')
    print(name, w, h, "levels", maxlev + 1)


if __name__ == "__main__":
    which = sys.argv[1:] or ["photo", "relief", "native"]
    photo = cv2.imread(P + "raw/commons_11448.jpg")
    H, W = photo.shape[:2]
    if "photo" in which:
        dzi(photo, "photo")
    if "relief" in which:
        r = relief_full(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY))
        cv2.imwrite(P + "work/relief_full.png", r)
        dzi(r, "relief")
    if "native" in which:
        n = cv2.imread(P + "work/mp/relief_signed3.png", 0)
        n = cv2.resize(n, (W, H), interpolation=cv2.INTER_CUBIC)
        dzi(n, "native")
