# Close-up revision pass (2026-11-10)

Read work/OPUS_TRACER_TASK.md, work/STROKE_BRIEF.md and work/ROTH_FRAME_TRACING.md in full first. Their
conventions (groove centre lines, widths, conf grades, faithful over complete, never trace a neighbour)
all still apply. Where they disagree with this file, this file wins.

What is new: for the signs at the top of columns 54-59 the kit now holds `closeup.png`. It is cut from an
independent close-up photograph (raw/commons_2024w.jpg) with about 8x the real optical resolution of the
main photograph. photo.png is an AI upscale of a much coarser frame, so until now tracers could not see
the fine shape of these signs. closeup.png has exactly the crop geometry of photo.png: the same pixel
coordinates. Light comes from above as in the main photo (a groove = dark upper wall, pale lower wall);
the stone looks grey and grainy, and pale flat patches are abrasion, not carving.

Your job, per sign (each already has trace.json, made WITHOUT the close-up):
1. Run `python3 scripts/render_closeup.py work/signs/<folder>` and look at check_closeup.png
   ([close-up] [close-up + current trace] [photo + current trace]). Also look at closeup.png itself,
   roth.png and grid.png (neighbours) as usual. zoom_sign.py does not show the close-up; to zoom, crop
   closeup.png yourself with a few lines of Python into work/scratch/<batch>/.
2. Decide what the close-up shows and revise trace.json so that it is the best faithful trace of THIS sign:
   - keep strokes that sit on a groove in the close-up; nudge points that are off the groove;
   - add strokes for parts of the sign that are clearly carved in the close-up but missing (heads, legs,
     inner details, the second wall of a wide sign, closing an outline that is really closed);
   - remove or downgrade strokes for which the close-up shows no groove (say so in notes);
   - if the whole trace is on the wrong feature, re-trace it.
   Do not "complete" the sign from Rothöhler or from the typeset shape: only what is cut in the stone.
3. Position check: closeup.png was registered to the crop to within a few px. If the close-up and
   photo.png/relief.png disagree by a small constant offset, photo.png is the coordinate reference: take
   the shape from the close-up and the position from photo/relief.
4. Re-render (render_closeup.py and render_trace.py), iterate 1-3 rounds, run trace_score.py as a check
   (not a target).
5. In trace.json keep every existing field, and add "closeup": one of "kept", "adjusted", "extended",
   "reduced", "retraced", "emptied", "newly_traced". Append to "notes": " | closeup: <one or two
   sentences on what the close-up showed and what you changed>". If the close-up shows that the sign is
   not the one labelled, set "identity_ok": false and say what it is.
6. Signs listed to you as EMPTY or LOST have no strokes: check whether the close-up shows the sign after
   all. If it clearly does, trace it ("newly_traced"); otherwise leave it and note "closeup: confirms".

The previous trace is saved as trace_pre_closeup.json in each folder: do not edit or delete it.
Findings worth the coordinator's attention (wrong identity, a carved sign that is in nobody's list, a
neighbour's trace that is clearly wrong, an empty/lost sign that is there) go to
work/scratch/findings/<batch>.md as short bullets citing rids.

Rules: write only to work/signs/<folder>/ for YOUR folders, work/scratch/findings/<batch>.md and
work/scratch/<batch>/. No subagents. Do not run build_data.py, renumber_roth.py or any queue script.
Final reply: at most 6 lines: counts per "closeup" outcome, number of findings, any tool problem.
