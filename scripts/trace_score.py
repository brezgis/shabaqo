"""Faithfulness score for a sign trace: do the strokes sit on carved grooves?

A carved groove under the gallery's top light leaves a strong band of edge
energy (shadow edge + highlight edge). We sample a groove-evidence map along
every stroke and compare it with the same strokes displaced by 4-8 crop px in
8 directions. On a real cut the trace "locks in": evidence on the path is
clearly higher than just beside it. On texture, the ratio sits near 1.

  lock      = mean evidence on path / mean evidence on displaced copies
  support   = fraction of path samples whose evidence is above the crop's 70th pct
  native    = the same lock ratio on the non-upscaled relief (guards against
              strokes that exist only in the AI-upscaled photo)

usage: trace_score.py <sign_dir> [trace file name, default trace.json]
       trace_score.py --all [glob]       (prints a table)
"""
import glob
import json
import sys

import cv2
import numpy as np


def evidence(img):
    """Groove-centre evidence under top light: a carved groove reads, top to bottom, as a
    shadowed upper wall then a lit lower wall, so its centre line sits on a strong
    POSITIVE vertical intensity gradient. Vertical grooves show a weaker left/right
    pairing; their centre line sits on a peak of |d2/dx2|. Computed at a few groove scales (crop px are 3x FULL)."""
    g = img.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 25)
    z = (g - mu) / (np.sqrt(cv2.GaussianBlur((g - mu) ** 2, (0, 0), 25)) + 3)
    out = np.zeros_like(z)
    for sg in (2.0, 3.5, 5.5):
        zs = cv2.GaussianBlur(z, (0, 0), sg)
        dy = cv2.Sobel(zs, cv2.CV_32F, 0, 1, ksize=3) * sg
        # vertical grooves: the centre is where the left-right profile curves most
        # (|d2/dx2|), not where its walls are (|d/dx| peaks on both walls)
        dxx = cv2.Sobel(zs, cv2.CV_32F, 2, 0, ksize=3) * sg * sg
        out = np.maximum(out, np.maximum(dy, 0) + 0.35 * np.abs(dxx))
    return cv2.GaussianBlur(out, (0, 0), 1.5)


def samples(strokes, step=2.0):
    pts = []
    for s in strokes:
        d = np.array(s["d"], np.float32).reshape(-1, 2)
        if s.get("closed") and len(d) > 2:
            d = np.vstack([d, d[:1]])
        for a, b in zip(d[:-1], d[1:]):
            n = max(1, int(np.linalg.norm(b - a) / step))
            for t in np.linspace(0, 1, n, endpoint=False):
                pts.append(a + (b - a) * t)
        if len(d):
            pts.append(d[-1])
    return np.array(pts, np.float32).reshape(-1, 2)


def sample_map(m, pts):
    h, w = m.shape
    x = np.clip(pts[:, 0], 0, w - 1.001).astype(np.float32); y = np.clip(pts[:, 1], 0, h - 1.001).astype(np.float32)
    return cv2.remap(m, x.reshape(1, -1), y.reshape(1, -1), cv2.INTER_LINEAR).ravel()


def lock_ratio(m, pts):
    on = sample_map(m, pts).mean()
    off = []
    for r in (5.0, 8.0):
        for a in np.linspace(0, 2 * np.pi, 8, endpoint=False):
            off.append(sample_map(m, pts + [r * np.cos(a), r * np.sin(a)]).mean())
    return float(on / (np.mean(off) + 1e-6))


def score(sign_dir, name="trace.json"):
    d = sign_dir.rstrip("/") + "/"
    tr = json.load(open(d + name))
    strokes = [s for s in tr.get("strokes", []) if len(s.get("d", [])) >= 2]
    if not strokes:
        return {"sid": d.split("/")[-2], "n": 0}
    ev = evidence(cv2.imread(d + "photo.png", 0))
    evr = evidence(cv2.imread(d + "relief.png", 0))
    evn = evidence(cv2.imread(d + "native.png", 0))
    pts = samples(strokes)
    p70 = np.percentile(evr, 70)
    length = float(sum(np.linalg.norm(np.diff(np.array(s["d"], np.float32).reshape(-1, 2), axis=0), axis=1).sum() for s in strokes))
    return {"sid": d.split("/")[-2], "n": len(strokes), "len": round(length),
            "lock": round(lock_ratio(evr, pts), 3), "lock_photo": round(lock_ratio(ev, pts), 3),
            "native": round(lock_ratio(evn, pts), 3),
            "support": round(float((sample_map(evr, pts) > p70).mean()), 3)}


if __name__ == "__main__":
    if sys.argv[1] == "--all":
        pat = sys.argv[2] if len(sys.argv) > 2 else "/home/anna/projects/shabaka-stone/work/signs/*/"
        name = sys.argv[3] if len(sys.argv) > 3 else "trace.json"
        rows = []
        for d in sorted(glob.glob(pat)):
            try:
                rows.append(score(d, name))
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        rows = [r for r in rows if r.get("n")]
        for r in rows:
            print(r)
        if rows:
            for k in ("lock", "native", "support"):
                v = np.array([r[k] for r in rows])
                print(f"{k}: median {np.median(v):.3f}  p10 {np.percentile(v, 10):.3f}  n={len(v)}")
    else:
        print(score(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "trace.json"))
