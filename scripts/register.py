"""Register Breasted's plate onto the Commons photo.

Seeds an affine from hand-picked frame corners, then refines a homography with
ECC between Breasted's ink (blurred) and the photo's carved-edge energy.
Writes work/H_plate_to_photo.json.
"""
import json
import cv2
import numpy as np

cv2.setNumThreads(4)
P = "/home/anna/projects/shabaka-stone/"
import os
CFG = os.environ.get("REG", "breasted")
if CFG == "breasted":
    plate = (cv2.imread(P + "work/breasted_plate_mask.png", 0) > 127).astype(np.float32)
    plate[2345:] = 0
    plate[:, 3755:] = 0
elif CFG == "br":
    plate = (cv2.imread(P + "work/br_mask.png", 0) > 127).astype(np.float32)
else:
    plate = (cv2.imread(P + "work/roth_mask.png", 0) > 127).astype(np.float32)
photo = cv2.imread(P + "raw/commons_11448.jpg", 0)

# hand-picked: (plate xy) -> (photo xy)
seed = np.float32([
    [[22, 354], [900, 778]],      # line 1 top-left
    [[3750, 354], [10815, 753]],  # line 1 top-right
    [[22, 531], [900, 1245]],     # line 2 bottom-left
]) if CFG == "breasted" else np.float32([
    [[571, 212], [900, 778]],     # Bryant & Read: line 1 top-left
    [[5974, 212], [10815, 753]],
    [[571, 494], [900, 1245]],
]) if CFG == "br" else np.float32([
    [[537, 563], [900, 778]],     # Rothoehler Tafel 1: line 1 top-left
    [[6229, 563], [10815, 753]],
    [[537, 911], [900, 1245]],
])
A = cv2.getAffineTransform(np.ascontiguousarray(seed[:, 0]), np.ascontiguousarray(seed[:, 1]))
H0 = np.vstack([A, [0, 0, 1]])


def edge_energy(g):
    g = g.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 25)
    sd = np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 25)) + 4
    z = (g - mu) / sd                      # flatten the warm->dark gradient
    gx = cv2.Sobel(z, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(z, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


RATIO = {"breasted": 1 / 2.66, "br": 1 / 1.83, "roth": 1 / 1.742}[CFG]

def run(scale, H, sigma):
    # template: plate at `scale`; input: photo resampled so that a unit warp
    # maps plate px -> photo px at that scale
    S = np.diag([scale, scale, 1]).astype(np.float64)
    tpl = cv2.resize(plate, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    tpl = cv2.GaussianBlur(tpl, (0, 0), sigma)
    # pre-shrink the photo by the same overall plate->photo ratio * scale
    k = scale * RATIO
    ph = cv2.resize(photo, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    ph = cv2.GaussianBlur(edge_energy(ph), (0, 0), sigma)
    K = np.diag([k, k, 1])
    W = K @ H @ np.linalg.inv(S)             # template px -> small-photo px
    W = (W / W[2, 2]).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6)
    cc, W = cv2.findTransformECC(tpl, ph, W, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
    H = np.linalg.inv(K) @ W.astype(np.float64) @ S
    print(f"scale {scale}: ecc {cc:.4f}")
    return H / H[2, 2]


H = H0
for scale, sigma in [(0.25, 3), (0.5, 3), (1.0, 2.5)]:
    H = run(scale, H, sigma)
json.dump({"H": H.tolist(), "seed_affine": H0.tolist()}, open(P + {"breasted": "work/H_plate_to_photo.json", "br": "work/H_br_to_photo.json", "roth": "work/H_roth_to_photo.json"}[CFG], "w"), indent=1)
print(H)
