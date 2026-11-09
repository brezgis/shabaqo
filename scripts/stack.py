"""Glue every photograph of the stone into one relief surface.

Each photo is registered to the main photo's FULL frame (SIFT + MAGSAC, then
ECC refinement on edge energy), its local relief computed, and the reliefs
fused with per-pixel weights = local detail energy x coverage. The main photo
is AI-upscaled, so it is excluded from the 'native stack' (the trustworthy one)
and only blended into the 'all stack'.

Outputs (work/stack/): reg_<name>.json, stack_native.png, stack_all.png,
weight maps for inspection, and photos.json (per-photo diagnostics).
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
OUT = P + "work/stack/"
os.makedirs(OUT, exist_ok=True)

MAIN = P + "raw/commons_11448.jpg"
PHOTOS = {
    "oct24v": "raw/commons_2024v.jpg",
    "oct24w": "raw/commons_2024w.jpg",
    "aug19": "raw/commons_aug19.jpg",
    "flickr6424": "raw/commons_6424753957.jpg",
    "cc0_5184": "raw/commons_cc0_5184.jpg",
    "bm2931858531": "raw/refs/commons-extra/British_Museum_(2931858531).jpg",
    "egypt113": "raw/refs/commons-extra/British_Museum_Egypt_113.jpg",
    "bm2011": "raw/photos2/British_Museum_2011-06-13d.jpg",
    "nic144": "raw/photos2/Flickr_-_Nic%27s_events_-_British_Museum_with_Cory_and_Mary%2C_6_Sep_2007_-_144.jpg",
    "nic145": "raw/photos2/Flickr_-_Nic%27s_events_-_British_Museum_with_Cory_and_Mary%2C_6_Sep_2007_-_145.jpg",
    "nic146": "raw/photos2/Flickr_-_Nic%27s_events_-_British_Museum_with_Cory_and_Mary%2C_6_Sep_2007_-_146.jpg",
    "thestone": "raw/photos2/The_Shabaka_Stone.JPG",
}
for f in sorted(glob.glob(P + "raw/photos3/*")):  # extra photos found later
    PHOTOS["x_" + os.path.splitext(os.path.basename(f))[0][:24]] = os.path.relpath(f, P)

main = cv2.imread(MAIN, 0)
FH, FW = main.shape
WS = 0.25  # matching scale of the main frame


def clahe(g):
    return cv2.createCLAHE(3.0, (16, 16)).apply(g)


def edge_energy(g):
    g = g.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 20)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 20)) + 3
    z = (g - mu) / sd
    return np.sqrt(cv2.Sobel(z, cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(z, cv2.CV_32F, 0, 1) ** 2)


def relief(g, s_small, s_big):
    g = g.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 60)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 60)) + 3
    z = (g - mu) / sd
    return cv2.GaussianBlur(z, (0, 0), s_small) - cv2.GaussianBlur(z, (0, 0), s_big)


sift = cv2.SIFT_create(nfeatures=60000, contrastThreshold=0.02)
gm = clahe(cv2.resize(main, None, fx=WS, fy=WS, interpolation=cv2.INTER_AREA))
km, dm = sift.detectAndCompute(gm, None)
flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 96})


def register(name, path):
    img = cv2.imread(P + path, 0)
    if img is None:
        return None
    s = min(1.0, 2600 / max(img.shape))
    g = clahe(cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
    ko, do = sift.detectAndCompute(g, None)
    if do is None or len(ko) < 50:
        return None
    good = [m for m, n in flann.knnMatch(do, dm, k=2) if m.distance < 0.78 * n.distance]
    if len(good) < 25:
        return {"name": name, "ok": False, "why": f"{len(good)} matches"}
    src = np.float32([ko[m.queryIdx].pt for m in good]) / s
    dst = np.float32([km[m.trainIdx].pt for m in good]) / WS
    H, mask = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 12.0, maxIters=50000, confidence=0.9999)
    if H is None or mask.sum() < 20:
        return {"name": name, "ok": False, "why": "no homography"}
    inl = int(mask.sum())
    # coverage + resolution (photo px per FULL px)
    corners = cv2.perspectiveTransform(np.float32([[[0, 0], [img.shape[1], 0], [img.shape[1], img.shape[0]], [0, img.shape[0]]]]), H)[0]
    area = cv2.contourArea(corners)
    if area < 0.01 * FW * FH or area > 30 * FW * FH:
        return {"name": name, "ok": False, "why": "degenerate"}
    res = np.sqrt(img.shape[0] * img.shape[1] / area)
    # ECC refinement on edge energy, working at a scale matched to the photo's resolution
    k = float(np.clip(res, 0.2, 1.0)) * 0.5
    x0, y0 = np.maximum(corners.min(0), 0).astype(int)
    x1, y1 = np.minimum(corners.max(0), [FW, FH]).astype(int)
    tpl = cv2.GaussianBlur(edge_energy(cv2.resize(main[y0:y1, x0:x1], None, fx=k, fy=k, interpolation=cv2.INTER_AREA)), (0, 0), 2)
    T = np.array([[k, 0, -x0 * k], [0, k, -y0 * k], [0, 0, 1]])
    W0 = T @ H  # photo -> small template frame
    inp_scale = min(1.0, k / max(res, 1e-6) * 1.0)
    S = np.diag([inp_scale, inp_scale, 1.0])
    inp = cv2.GaussianBlur(edge_energy(cv2.resize(img, None, fx=inp_scale, fy=inp_scale, interpolation=cv2.INTER_AREA)), (0, 0), 2)
    Wtpl = np.linalg.inv(W0 @ np.linalg.inv(S))  # template -> small-photo
    Wtpl = (Wtpl / Wtpl[2, 2]).astype(np.float32)
    cc = None
    try:
        cc, Wtpl = cv2.findTransformECC(tpl, inp, Wtpl, cv2.MOTION_HOMOGRAPHY,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 150, 1e-6), None, 5)
        Hr = np.linalg.inv(T) @ np.linalg.inv(Wtpl.astype(np.float64)) @ S
        Hr /= Hr[2, 2]
        # accept refinement only if it stays close to the SIFT solution
        c2 = cv2.perspectiveTransform(corners[None] * 0 + cv2.perspectiveTransform(
            np.float32([[[0, 0], [img.shape[1], 0], [img.shape[1], img.shape[0]], [0, img.shape[0]]]]), np.eye(3))[0][None], Hr)[0]
        if np.abs(c2 - corners).max() < 0.03 * max(FW, FH):
            H = Hr
    except cv2.error:
        pass
    info = {"name": name, "ok": True, "path": path, "restricted": "photos3/" in path, "inliers": inl, "ecc": None if cc is None else float(cc),
            "res_photo_px_per_full_px": float(res), "bbox_full": [int(x0), int(y0), int(x1), int(y1)], "H": H.tolist()}
    json.dump(info, open(OUT + f"reg_{name}.json", "w"))
    return info


def fuse(names, out_name, include_main=False):
    acc = np.zeros((FH, FW), np.float32)
    wsum = np.zeros((FH, FW), np.float32)
    items = [("main", None)] if include_main else []
    items += [(n, json.load(open(OUT + f"reg_{n}.json"))) for n in names if os.path.exists(OUT + f"reg_{n}.json")]
    for n, info in items:
        if info is None:
            r = relief(main, 2.0, 12)
            valid = np.ones_like(r, np.uint8)
            res = 0.5  # upscaled ~2x: treat as half real resolution
        else:
            img = cv2.imread(P + info["path"], 0)
            H = np.array(info["H"])
            x0, y0, x1, y1 = info["bbox_full"]
            Tt = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]]) @ H
            reg = cv2.warpPerspective(img, Tt, (x1 - x0, y1 - y0), flags=cv2.INTER_CUBIC)
            v = cv2.warpPerspective(np.full(img.shape, 255, np.uint8), Tt, (x1 - x0, y1 - y0), flags=cv2.INTER_NEAREST)
            res = info["res_photo_px_per_full_px"]
            # stroke-scale band-pass, wider where the photo is coarser
            sm = max(2.0, 1.0 / max(res, 0.05) * 0.9)
            rr = relief(reg, sm, sm * 6)
            r = np.zeros((FH, FW), np.float32); r[y0:y1, x0:x1] = rr
            valid = np.zeros((FH, FW), np.uint8); valid[y0:y1, x0:x1] = cv2.erode(v, np.ones((41, 41), np.uint8)) > 200
        # weight: local detail energy, favouring sharper (higher-res) sources
        en = cv2.GaussianBlur(r * r, (0, 0), 25)
        w = en * (min(res, 1.5) ** 2) * valid
        # feather the coverage edge so seams don't show
        w *= cv2.GaussianBlur(valid.astype(np.float32), (0, 0), 30)
        # normalise each photo's relief to unit local energy before mixing
        rn = r / np.sqrt(en + 1e-3)
        acc += rn * w
        wsum += w
        if info is not None:
            cv2.imwrite(OUT + f"w_{n}.jpg", cv2.resize(np.clip(w / (np.percentile(w[w > 0], 99) + 1e-6) * 255, 0, 255).astype(np.uint8), None, fx=0.1, fy=0.1))
        print("  fused", n, f"res={res:.2f}")
        del r, valid, w, en, rn
    st = acc / np.maximum(wsum, 1e-6)
    st[wsum < 1e-6] = 0
    img = np.clip(128 + st * 45, 0, 255).astype(np.uint8)
    cv2.imwrite(OUT + out_name, img)
    cv2.imwrite(OUT + "coverage_" + out_name.replace(".png", ".jpg"),
                cv2.resize(np.clip(wsum / np.percentile(wsum, 99) * 255, 0, 255).astype(np.uint8), None, fx=0.1, fy=0.1))
    return img


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("reg", "all"):
        diag = []
        for n, p in PHOTOS.items():
            info = register(n, p)
            print(n, None if info is None else {k: info.get(k) for k in ("ok", "inliers", "ecc", "res_photo_px_per_full_px", "why")})
            if info:
                diag.append({k: v for k, v in info.items() if k != "H"})
        json.dump(diag, open(OUT + "photos.json", "w"), indent=1)
    if step in ("fuse", "all"):
        ok = [d["name"] for d in json.load(open(OUT + "photos.json")) if d.get("ok")]
        fuse(ok, "stack_native.png", include_main=False)
        fuse(ok, "stack_all.png", include_main=True)
