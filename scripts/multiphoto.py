"""Register the other Commons photos into the main photo's frame (half res)
and build per-photo and combined 'carved relief' maps.

Frame: main photo (commons_11448.jpg) downscaled x0.5 -> 5724 x 3726.
Outputs work/mp/<name>_reg.jpg, work/mp/<name>_relief.png, work/mp/relief_combined.png
and work/mp/registration.json (homographies, inlier counts).
"""
import json
import os
import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
OUT = P + "work/mp/"
os.makedirs(OUT, exist_ok=True)
K = 0.5
main = cv2.imread(P + "raw/commons_11448.jpg")
main = cv2.resize(main, None, fx=K, fy=K, interpolation=cv2.INTER_AREA)
Hm, Wm = main.shape[:2]
cv2.imwrite(OUT + "main_reg.jpg", main, [cv2.IMWRITE_JPEG_QUALITY, 92])

others = {
    "aug19": "raw/commons_aug19.jpg",
    "oct24v": "raw/commons_2024v.jpg",
    "oct24w": "raw/commons_2024w.jpg",
    "flickr6424": "raw/commons_6424753957.jpg",
}


def norm_gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(3.0, (16, 16)).apply(g)


sift = cv2.SIFT_create(nfeatures=40000)
# features on the main frame at a working scale
ws = 0.5  # of the half-res frame
gm = cv2.resize(norm_gray(main), None, fx=ws, fy=ws, interpolation=cv2.INTER_AREA)
km, dm = sift.detectAndCompute(gm, None)
flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})

info = {}
for name, path in others.items():
    img = cv2.imread(P + path)  # cv2 ignores EXIF orientation by default? use IMREAD flag
    img = cv2.imread(P + path, cv2.IMREAD_COLOR)
    s = min(1.0, 3000 / max(img.shape[:2]))
    g = cv2.resize(norm_gray(img), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ko, do = sift.detectAndCompute(g, None)
    matches = flann.knnMatch(do, dm, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    src = np.float32([ko[m.queryIdx].pt for m in good]) / s
    dst = np.float32([km[m.trainIdx].pt for m in good]) / ws
    H, mask = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 4.0, maxIters=20000, confidence=0.9999)
    inl = int(mask.sum()) if mask is not None else 0
    print(name, "matches", len(good), "inliers", inl)
    info[name] = {"H": H.tolist(), "inliers": inl, "src": path}
    reg = cv2.warpPerspective(img, H, (Wm, Hm), flags=cv2.INTER_AREA)
    valid = cv2.warpPerspective(np.full(img.shape[:2], 255, np.uint8), H, (Wm, Hm))
    reg[valid < 128] = 0
    cv2.imwrite(OUT + f"{name}_reg.jpg", reg, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(OUT + f"{name}_valid.png", valid)

json.dump(info, open(OUT + "registration.json", "w"), indent=1)


def relief(img):
    """Local-contrast-normalised luminance: incised strokes show as
    paired shadow/highlight; we keep the signed value and its magnitude."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 30)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 30)) + 3
    z = (g - mu) / sd
    # band-pass to the width of a carved stroke (~4-12 px at this scale)
    dog = cv2.GaussianBlur(z, (0, 0), 1.2) - cv2.GaussianBlur(z, (0, 0), 6)
    return dog


acc = np.zeros((Hm, Wm), np.float32)
cnt = np.zeros((Hm, Wm), np.float32)
for name in ["main"] + list(others):
    img = cv2.imread(OUT + f"{name}_reg.jpg")
    r = relief(img)
    valid = np.ones((Hm, Wm), bool) if name == "main" else cv2.imread(OUT + f"{name}_valid.png", 0) > 200
    valid = cv2.erode(valid.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    mag = np.abs(r)
    mag[~valid] = 0
    vis = np.clip(128 + r * 70, 0, 255).astype(np.uint8)
    cv2.imwrite(OUT + f"{name}_relief.png", vis)
    acc += mag * valid
    cnt += valid
comb = acc / np.maximum(cnt, 1)
comb = np.clip(comb / np.percentile(comb, 99.5) * 255, 0, 255).astype(np.uint8)
cv2.imwrite(OUT + "relief_combined.png", comb)
print("done")
