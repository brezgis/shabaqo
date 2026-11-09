"""Snap traced strokes onto the groove centres (active-contour style).

The tracer decides WHAT is carved (which strokes, their topology). This decides
exactly WHERE each stroke runs: every stroke is resampled every ~4 crop px, each
point may move along the stroke's local normal by up to +-R px, and a Viterbi
pass picks the offsets that maximise groove-centre evidence (see trace_score)
minus a smoothness penalty on neighbouring offsets. A snapped trace is kept only
if its lock score improves on BOTH the main relief and the native relief, so
snapping can't drag a stroke onto an upscaling artefact.

usage: snap.py <sign_dir> [--write]       prints before/after scores
       snap.py --all [--write]
Writes trace_snapped.json (and, with --write, updates trace.json, keeping
trace_orig.json as the agent's original).
"""
import glob
import json
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, "/home/anna/projects/shabaka-stone/scripts")
import trace_score as T  # noqa: E402

R = 7        # max normal offset, crop px (crop = 3x FULL, so ~2.3 FULL px)
STEP = 4.0   # resample spacing
LAMBDA = 0.06


def resample(d, closed):
    d = np.array(d, np.float32).reshape(-1, 2)
    if closed:
        d = np.vstack([d, d[:1]])
    seg = np.linalg.norm(np.diff(d, axis=0), axis=1)
    L = seg.sum()
    if L < 1:
        return d
    n = max(3, int(L / STEP) + 1)
    t = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, L, n)
    pts = np.stack([np.interp(u, t, d[:, 0]), np.interp(u, t, d[:, 1])], 1)
    return pts[:-1] if closed else pts


def normals(p, closed):
    tng = np.gradient(p, axis=0) if len(p) > 2 else np.repeat(p[1:] - p[:1], len(p), 0)
    if closed and len(p) > 2:
        tng = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    tng /= (np.linalg.norm(tng, axis=1, keepdims=True) + 1e-6)
    return np.stack([-tng[:, 1], tng[:, 0]], 1)


def snap_stroke(ev, d, closed, w):
    p = resample(d, closed)
    if len(p) < 2:
        return np.array(d, np.float32)
    nrm = normals(p, closed)
    offs = np.arange(-R, R + 1, dtype=np.float32)
    # evidence for every (point, offset)
    cand = p[:, None, :] + nrm[:, None, :] * offs[None, :, None]
    E = T.sample_map(ev, cand.reshape(-1, 2)).reshape(len(p), len(offs))
    E = E / (E.max() + 1e-6)
    # Viterbi: maximise sum E - LAMBDA * (delta offset)^2, mild pull to the original
    pen = LAMBDA * (offs[:, None] - offs[None, :]) ** 2
    prior = 0.004 * offs ** 2
    score = E[0] - prior
    back = np.zeros((len(p), len(offs)), np.int32)
    for i in range(1, len(p)):
        tot = score[:, None] - pen
        back[i] = np.argmax(tot, axis=0)
        score = tot[back[i], np.arange(len(offs))] + E[i] - prior
    k = np.zeros(len(p), np.int32); k[-1] = int(np.argmax(score))
    for i in range(len(p) - 1, 0, -1):
        k[i - 1] = back[i, k[i]]
    out = p + nrm * offs[k][:, None]
    # light smoothing so the path stays a hand-like line
    if len(out) > 4:
        sm = cv2.GaussianBlur(out.reshape(-1, 1, 2), (1, 5), 0).reshape(-1, 2)
        sm[0], sm[-1] = out[0], out[-1]
        out = sm
    return out


def snap(sign_dir, write=False):
    d = sign_dir.rstrip("/") + "/"
    src = d + ("trace_orig.json" if write and _exists(d + "trace_orig.json") else "trace.json")
    tr = json.load(open(src))
    strokes = [s for s in tr.get("strokes", []) if len(s.get("d", [])) >= 2]
    if not strokes:
        return None
    ev = T.evidence(cv2.imread(d + "relief.png", 0))
    evn = T.evidence(cv2.imread(d + "native.png", 0))
    before = (T.lock_ratio(ev, T.samples(strokes)), T.lock_ratio(evn, T.samples(strokes)))
    new = []
    for s in strokes:
        q = snap_stroke(ev, s["d"], bool(s.get("closed")), s.get("w", 6))
        new.append({**s, "d": [[round(float(x), 1), round(float(y), 1)] for x, y in q]})
    after = (T.lock_ratio(ev, T.samples(new)), T.lock_ratio(evn, T.samples(new)))
    keep = after[0] > before[0] and after[1] >= before[1] - 0.005
    res = {"sid": d.split("/")[-2], "before": [round(v, 3) for v in before],
           "after": [round(v, 3) for v in after], "kept": bool(keep)}
    out = {**tr, "strokes": new if keep else strokes, "snap": res}
    json.dump(out, open(d + "trace_snapped.json", "w"), indent=1)
    if write:
        if not _exists(d + "trace_orig.json"):
            shutil.copy(d + "trace.json", d + "trace_orig.json")
        json.dump(out, open(d + "trace.json", "w"), indent=1)
    return res


def _exists(p):
    try:
        open(p).close(); return True
    except OSError:
        return False


if __name__ == "__main__":
    write = "--write" in sys.argv
    if sys.argv[1] == "--all":
        rs = []
        for d in sorted(glob.glob("/home/anna/projects/shabaka-stone/work/signs/*/")):
            if _exists(d + "trace.json"):
                try:
                    r = snap(d, write)
                except Exception as ex:  # a malformed agent trace shouldn't stop the batch
                    print("err", d, ex); continue
                if r:
                    rs.append(r)
        b = np.array([r["before"][0] for r in rs]); a = np.array([r["after"][0] if r["kept"] else r["before"][0] for r in rs])
        bn = np.array([r["before"][1] for r in rs]); an = np.array([r["after"][1] if r["kept"] else r["before"][1] for r in rs])
        print(f"{len(rs)} traces; kept snap on {np.mean([r['kept'] for r in rs]):.0%}")
        print(f"lock (relief) median {np.median(b):.3f} -> {np.median(a):.3f};  native {np.median(bn):.3f} -> {np.median(an):.3f}")
        print(f"traces below 1.0: {np.mean(b < 1):.0%} -> {np.mean(a < 1):.0%}")
    else:
        print(snap(sys.argv[1], write))
