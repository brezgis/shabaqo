"""Shared geometry: Breasted plate px <-> main photo frames.

FULL = commons_11448.jpg pixels; A2 = FULL * 0.5 (the working frame for
relief maps and tracing sheets).  plate -> FULL is  H(p + D(p)).
"""
import json
import cv2
import numpy as np

P = "/home/anna/projects/shabaka-stone/"
H = np.array(json.load(open(P + "work/H_plate_to_photo.json"))["H"])
_F = np.load(P + "work/disp_field.npz")
_f = int(_F["f"])
_dx, _dy = _F["dx"], _F["dy"]


def _sample(field, x, y):
    gx = np.clip(np.asarray(x, float) / _f, 0, field.shape[1] - 1.001)
    gy = np.clip(np.asarray(y, float) / _f, 0, field.shape[0] - 1.001)
    x0, y0 = gx.astype(int), gy.astype(int)
    ax, ay = gx - x0, gy - y0
    return (field[y0, x0] * (1 - ax) * (1 - ay) + field[y0, x0 + 1] * ax * (1 - ay)
            + field[y0 + 1, x0] * (1 - ax) * ay + field[y0 + 1, x0 + 1] * ax * ay)


def plate_to_full(xy):
    xy = np.atleast_2d(np.asarray(xy, float))
    q = xy + np.stack([_sample(_dx, xy[:, 0], xy[:, 1]), _sample(_dy, xy[:, 0], xy[:, 1])], 1)
    out = cv2.perspectiveTransform(q[None].astype(np.float64), H)[0]
    return out


def plate_to_a2(xy):
    return plate_to_full(xy) * 0.5


def box_plate_to_a2(b):
    x0, y0, x1, y1 = b
    c = plate_to_a2([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    return [float(c[:, 0].min()), float(c[:, 1].min()), float(c[:, 0].max()), float(c[:, 1].max())]
