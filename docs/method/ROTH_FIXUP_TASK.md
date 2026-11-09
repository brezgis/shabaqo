# Fix-up pass after tracing in Rothöhler's frame (2026-11-08)

Read work/OPUS_TRACER_TASK.md, work/STROKE_BRIEF.md and work/ROTH_FRAME_TRACING.md first; they still apply.
This pass repairs OLD traces (mostly from the 1901-numbered rounds) that the tracing batches found to be
wrong, and re-checks a few signs that were left empty or marked lost under a misplaced kit. Every kit in your
list was rebuilt on 2026-11-08 with the corrected Rothöhler alignment; existing traces were converted into the
new crop (backups of the old kits: work/scratch/kit_rebuild_backup/<folder>/).

For each folder in your launch message:
1. Read its item note (in your launch message), the batch finding it cites (work/scratch/findings/roth-*.md,
   which often gives FULL-px positions and which strokes to keep), meta.json ("rid", "roth"), trace.json and
   check.png, and the neighbouring traces it overlaps (look only, don't edit neighbours not in your list).
2. Before changing anything, copy trace.json to trace_pre_fixup.json (only if that file does not exist yet).
3. Make the fix:
   - "trim": remove the strokes that belong to the named other sign (that sign has its own trace now). Keep
     the rest unchanged.
   - "re-trace": trace the sign named by the folder's rid from scratch on the right carving.
   - "re-check": look again with the rebuilt kit; trace the sign if it is on the stone, else write an empty
     trace with the reason (status of a "lost" sign becomes traced/empty from your trace).
   - "add": add the missing part to the existing trace.
   - "notes": fix notes / gardiner / roth_agrees only.
   Set "rid", "roth_agrees", and add a line to "notes": "fixup 2026-11-08: <what changed>".
4. Run render_trace.py, trace_score.py and trace_qa.py; look at check.png.

Write only to the folders in your list, work/scratch/findings/<batch>.md and work/scratch/<batch>/. Don't edit
inventories, signlist, scripts or web/. No subagents. Don't run build_data.py, renumber_roth.py, roth_align.py
or the kit scripts.

Final reply: at most 6 lines: folders fixed, folders unchanged (and why), anything you could not resolve.
