"""evidence_sign.py <sign_dir> x0 y0 x1 y1 [scale=2] : trace_score's evidence map (photo | native) for a crop region,
with the trace overlaid if trace.json exists. Bright = groove edge evidence. Writes <sign_dir>/evid.png."""
import sys, json, os
sys.path.insert(0, "/home/anna/projects/shabaka-stone/scripts")
import cv2, numpy as np
from trace_score import evidence
d = sys.argv[1].rstrip("/") + "/"; x0, y0, x1, y1 = map(int, sys.argv[2:6]); sc = float(sys.argv[6]) if len(sys.argv) > 6 else 2.0
tr = json.load(open(d + "trace.json")) if os.path.exists(d + "trace.json") else {"strokes": []}
pan = []
for nm in ("photo.png", "native.png"):
    e = evidence(cv2.imread(d + nm, 0))[y0:y1, x0:x1]
    e = np.clip(e / np.percentile(e, 99) * 255, 0, 255).astype(np.uint8)
    e = cv2.cvtColor(cv2.resize(e, None, fx=sc, fy=sc), cv2.COLOR_GRAY2BGR)
    for s in tr["strokes"]:
        p = (np.array(s["d"], np.float32) - [x0, y0]) * sc
        cv2.polylines(e, [np.round(p).astype(np.int32)], bool(s.get("closed")), (0, 0, 255), 1)
    for gx in range((x0 // 50 + 1) * 50, x1, 50):
        cv2.putText(e, str(gx), (int((gx - x0) * sc), 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for gy in range((y0 // 50 + 1) * 50, y1, 50):
        cv2.putText(e, str(gy), (2, int((gy - y0) * sc)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    pan += [e, np.full((e.shape[0], 6, 3), 255, np.uint8)]
out = os.path.join(d, "evid.png")
cv2.imwrite(out, np.hstack(pan[:-1])); print(out)
