# Addendum: tracing in Rothöhler's frame (from 2026-11-08)

Read together with work/OPUS_TRACER_TASK.md and work/STROKE_BRIEF.md. Where they disagree, this file wins.

The canonical sign list is now Rothöhler 2005's sequence, in work/signlist_roth.json. Each sign has a
rid "<unit>.R<k>" (k = his k-th sign in the unit, in reading order).

- You are given rids. Each rid's kit folder is work/signs/<alias>/ if the sign has a 1901 alias (e.g.
  57.R4 -> work/signs/57.4/), else work/signs/<rid>/ (e.g. work/signs/57.R5/). Your launch message lists
  the pairs. All tools (render_trace.py, trace_score.py, trace_qa.py, zoom_sign.py, evidence_sign.py) take
  the folder.
- Identity: meta.json "gardiner" and the "roth" block (gardiner, desc, note) are Rothöhler's reading.
  "roth.old_gardiner_1901" is the old label, for reference only. Trace the sign HE draws at this place;
  the green box is a starting estimate (1901 box, trace extent, or his plate box mapped to the photo,
  which can be off by tens of px), so follow the carving.
- grid.png and context.png label neighbours with their Rothöhler number (R<k>:code). RED = traced (do not
  trace into it), ORANGE DASHED = untraced, approximate.
- New signs (no 1901 alias) were often covered by a neighbour's 1901 box or lie in a group; take care to
  trace only this sign's strokes, and say in notes how you separated it from its neighbours.
- In trace.json add "rid": "<rid>". "roth_agrees" means: your trace matches his drawing of THIS sign.
- If his sign is not on the stone at all (surface lost or he restored it), write an empty trace with a
  reason, as before.
- Findings (wrong identity in his list, a sign he omits, sequence problems) go to
  work/scratch/findings/<batch>.md as before, citing rids.
- Placement: since 2026-11-08 roth.png and the boxes of new signs use a per-region drift correction
  fitted from existing traces (scripts/roth_align.py; typically within ~15-25 FULL px, worse in regions
  with few traces). Still match his signs by SEQUENCE when roth.png and the carving disagree.
- If the sign runs past the crop edge, trace it anyway in kit coordinates (points may be negative or
  beyond the image size), say so in notes ("past crop edge") and add a finding so the kit gets re-cut.
  Never leave a sign empty only because it lies outside the crop.
