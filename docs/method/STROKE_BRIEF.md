# Stroke-tracing brief: one hieroglyph at a time

You are tracing the CARVED STROKES of individual hieroglyphs on the Shabaka Stone (British Museum EA
498) from photographs. The goal is an epigraphic tracing that is faithful to the stone: only what is
cut into the stone, where it is cut. Not a textbook drawing of the sign.

## Each sign has a kit folder `work/signs/<sid>/`
- `photo.png`: the stone, contrast-enhanced. Crop = the sign's box plus margin, upscaled 3×.
- `relief.png`: computed relief of the same crop. Carved grooves show as a dark edge paired with
  a bright edge (light comes from above). Often the clearest view.
- `native.png`: relief from other, NON-upscaled photographs (softer). The main photo was AI-upscaled,
  so a stroke that appears ONLY in photo/relief but has no trace at all in native may be an artefact.
- `grid.png`: the photo with coordinates (ticks every 10 px, labels every 50). GREEN box = where
  this sign is believed to be. RED boxes = neighbouring signs: do not trace into them.
- `meta.json`: identity (Gardiner code, name), which way the sign faces, the tracer's note, crop size.
- **Rothöhler's 2005 facsimile is the preferred reference** (see "Reference priority" at the end):
  `roth.png` in every kit shows his drawing in red over this kit's photo, and
  `work/signs/roth_col<unit>.png` is his whole column. His drawing is only approximately aligned, so
  never copy its geometry: trace the stone.

All files in a kit share one pixel coordinate system (crop px, origin top-left).

## What to produce: `work/signs/<sid>/trace.json`
```json
{
  "strokes": [
    {"d": [[x,y],[x,y],...], "w": 6, "closed": false, "conf": "clear"}
  ],
  "box": [x0, y0, x1, y1],
  "identity_ok": true,
  "notes": "short: what you saw, anything that disagrees with the identity or the box"
}
```
- Each stroke is a polyline along the CENTRE LINE of one carved groove, with enough points to
  follow curves (every ~8–15 px on curves). `w` = groove width in crop px (typically 4–10).
  `closed: true` for closed outlines (e.g. a loop, an oval sign).
- `conf`: `clear` (unambiguous cut), `faint` (worn but real: visible in relief AND native),
  `restored` (you are completing a stroke you cannot actually see; use sparingly, and say why).
- `box`: the tight bounding box of the sign as actually carved (it may differ from the green box).
- `identity_ok`: false if the carving clearly is not the sign named in meta.json; explain in notes.
- If the sign shares its green box with other signs (e.g. three flags in one box), trace ONLY the
  one this sid refers to (they are numbered in reading order: the first flag = the top / the
  first in the reading direction) and say which one you traced.

## Lessons from the method trial (read these)
- The most common fault: strokes drawn 5–12 px too LOW, in the middle of the bright lit-wall band.
  The groove centre is the dark→bright BOUNDARY (top light), not the bright band.
- A lens/mouth sign's two outlines usually MERGE into one tail groove at each tip; don't draw two
  parallel lines out to the tip.
- Pale smooth patches, broad pale streaks and diagonal wiping marks are not cuts. A stroke needs
  a groove edge, visible in relief AND native.
- The green box is sometimes misplaced by tens of px (it came from an old hand copy). If the sign
  is clearly beside the box, trace it where it actually is and give its real `box`. If it lies
  outside the crop entirely, trace nothing and say so in notes ("box misplaced: sign is above/below").
- `context.png` (if present) shows the column at lower zoom: this sign's box GREEN, neighbours RED
  labelled n:Gardiner. Look at it first.
- Objective check: `python3 scripts/trace_score.py work/signs/<sid>` prints lock/native (>1.15 good,
  <1.0 mostly off the cuts). Use it as a check, not a target: never add or move strokes onto
  something your eye can't see just to raise it.

## Method (do this for every sign)
1. Look at context.png, grid.png, relief.png and native.png. Find the carved sign inside or near the green box.
2. Write trace.json.
3. Run `python3 scripts/render_trace.py work/signs/<sid>` and LOOK at the resulting check.png
   (trace over photo | over relief | trace alone).
4. Fix misplaced or missing strokes and re-render. Iterate until each stroke sits on its groove.
   Usually 2–4 rounds.
5. WHERE the groove centre is: the gallery light comes from above. A carved groove therefore shows
   as a DARK band (its shadowed upper wall) directly above a BRIGHT band (its lit lower wall); the
   centre line runs along the boundary between them, not on the dark band. Vertical grooves show
   only a weak light/dark pairing left-right; look for the faint parallel edge in relief AND native.
   Trace every part of a sign you can actually see (e.g. a flag's full pole, not just its top), but
   nothing you can't.
6. Do not trace stone texture, pits, diagonal wiping marks, or column rules (long straight vertical
   lines between columns). Hieroglyphs on this stone are incised outlines and simple strokes.

Be faithful over complete: a short accurate fragment beats a plausible full sign.

Work alone: do not spawn subagents. Keep any helper scripts in work/scratch/<your-batch-name>/ (not a shared scratchpad).

## Seed signs (wide kits)
Some kits are SEED kits: their crop has an extra-wide margin (meta.json crop.size is large) because
the green box may be off by up to ~150 FULL px (450 crop px). For these, finding the right carving
matters more than anything: use context.png and the column's reading order to identify which
carving is this sid (the n-th sign of its column, matching its Gardiner code), trace it, and give
an accurate `box`. Other signs' positions will be re-estimated from yours.

## v2 kits (touch-up and remaining signs)
v2 kits (`meta.json` has `"kit": "v2"`) fix a common fault of the first round: signs traced only as far as
the green box, leaving out parts that lay outside it (a bird's legs and feet, the end of a tail, a bar).
- The GREEN box is now grown to the typical size of this sign type (`typical_size_crop` in meta.json),
  but it is still only an estimate. Trace the WHOLE carved sign, wherever its parts are.
- RED boxes are neighbours that are already traced (their traced extent): do not trace into them.
- ORANGE DASHED boxes are untraced neighbours placed from the 1901 copy: approximate only. Part of this
  sign may lie inside one (e.g. a bird's feet inside a box labelled `?`). If so, trace it and say in notes
  which neighbour box it fell in.
- If `trace_prev.json` exists, start from it: render it, keep strokes that sit on grooves, add what it
  missed, fix what is off. Do not delete good strokes just to redraw them.
- Before stopping, check completeness: compare your trace with the sign's expected shape (and the
  Rothöhler strip if given). If a part of the sign is genuinely not visible on the stone, say so in notes
  ("legs not visible: surface lost") rather than leaving it unexplained.
- Run `python3 scripts/trace_qa.py <sid>` at the end; if it says `clipped`, the sign may continue past
  the crop: say so in notes.

## Notes from the first Opus round (read these too)
- **Close-ups.** check.png is large and gets downscaled when you view it. For detail use
  `python3 scripts/zoom_sign.py work/signs/<sid> x0 y0 x1 y1 [scale]` (relief | photo | native of a crop
  region, 10 px grid, your trace overlaid) and `python3 scripts/evidence_sign.py work/signs/<sid> x0 y0 x1 y1
  [scale]` (the scorer's groove-evidence map). Both write into the sign's own folder (zoom.png, evid.png).
- **Sunk signs.** Some signs are cut as sunk hollows or silhouettes (loaves, baskets, some birds and arches)
  rather than incised outlines. Trace the RIM of the hollow as a closed or open outline, and say "sunk" in
  notes. On a sunk shape the lower edge reads the opposite way (bright → dark), so place it by eye and with
  evidence_sign.py, not by the dark→bright rule. trace_score's lock is lower for rims; that is expected.
- **Steep and vertical grooves** get weak evidence in trace_score (the light comes from above). A low lock
  on a steep stroke you can see in relief AND native is not a reason to delete it; say so in notes.
- **Grouped boxes and order.** The text is RETROGRADE: signs face right but are read left to right, like
  the columns. Side-by-side signs within a column are therefore read LEFT TO RIGHT, then top to bottom,
  and the sid numbering follows that (e.g. 56.4/5/6 left to right). Line 2 is the exception: its signs
  face left and it reads left to right as well; line 1 is a mirrored pair reading outward from the centre. When one green box covers a group (three flags,
  two small birds), trace only the one this sid's position in that order refers to, and give the
  coordinates of the others in notes.
- **typical_size_crop is unreliable** for `?` signs and for signs whose 1901 box covered a group; a QA
  `incomplete` flag on those is not by itself a reason to add strokes.
- **Disagreements with the label** (e.g. a "water line" that is a cobra) belong in notes with
  `identity_ok: false` when clear, so the reading can be corrected later.

## Reference priority (the stone first, then Rothöhler, then the rest)
1. **The stone** (photo / relief / native) is the authority for what is cut and where.
2. **Rothöhler 2005** (Heidelberg dissertation, Tafel 1 facsimile) is the best available copy. Look at
   `roth.png` for EVERY sign: his drawing aligned COLUMN BY COLUMN from his printed column labels
   (work/roth_columns.json): his first and last signs of each column land on ours, so it is usually
   within a few tens of crop px, but can drift mid-column: confirm by shape and sequence.
   `roth_col<unit>.png` is his drawing of exactly this unit, cut by his own labels (regenerated
   2026-11-07; strips made before that were often one or more columns off).
   Use it to decide which sign this is, what shape it has here and where its parts are, and to confirm
   faint strokes.
3. **Breasted 1901** (the source of the green/orange boxes and of many `gardiner` labels in meta.json) and
   the other old copies are less reliable. When Rothöhler and the 1901-derived label or box disagree,
   follow Rothöhler unless the stone clearly shows otherwise.
- If the stone and Rothöhler agree on a different sign than meta.json's `gardiner`, trace it, set
  `identity_ok: false`, and put `"roth": "<Gardiner code or description of his sign>"` in trace.json
  (an extra key is fine) plus a short note.
- If Rothöhler draws something the stone does not show (he restored it, or the photo is worse there),
  do not trace it; say "Rothöhler draws X here; not visible on the photo" in notes.
- Put `"roth_agrees": true|false` in every trace.json: does his drawing agree with what you traced?

## Sign ids are positional (decided 2026-11-07)
A sid is the n-th sign of its column in reading order (left to right, then top to bottom). If the sign
at that position doesn't match meta.json's `gardiner` label (e.g. the labels of a side-by-side pair look
swapped), trace the sign AT THE POSITION anyway, set `identity_ok: false`, and give the correct reading in
notes (and `"roth"` if Rothöhler shows it). Never trace a different position just to match a label.
