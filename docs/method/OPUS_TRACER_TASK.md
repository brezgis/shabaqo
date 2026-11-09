# Standing task for an Opus tracing agent (Shabaka Stone)

You trace carved hieroglyphs on the Shabaka Stone (British Museum EA 498) from photographs, one sign
at a time, for an epigraphic facsimile. Project root: /home/anna/projects/shabaka-stone. You are given
a batch name (e.g. `rest-07`) and a list of sign ids (sids) in your launch message.

1. Read work/STROKE_BRIEF.md in full and follow it exactly. Especially read "v2 kits", "Notes from the
   first Opus round", "Reference priority" and "Sign ids are positional".
2. Per sign, in the given order:
   - Look at the kit in work/signs/<sid>/: context.png, grid.png, relief.png, native.png, roth.png
     (Rothöhler 2005, aligned column by column) and meta.json. Also look at his column strip
     work/signs/roth_col<unit>.png, which is cut from his printed labels.
   - Write trace.json, including "roth_agrees".
   - Run `python3 scripts/render_trace.py work/signs/<sid>` and look at check.png. Use
     scripts/zoom_sign.py and scripts/evidence_sign.py for close-ups. Iterate 2–4 rounds.
   - Run `python3 scripts/trace_score.py work/signs/<sid>` and `python3 scripts/trace_qa.py <sid>` as
     checks, never as targets.
3. Authority: the stone first, then Rothöhler, then the 1901-derived boxes and labels. Side-by-side signs
   read LEFT TO RIGHT. Sids are positional. Faithful over complete. Write honest notes. An empty trace
   with a reason is valid where the surface is lost. Match Rothöhler by sequence when roth.png drifts.
4. Write findings worth fixing to work/scratch/findings/<batch>.md as short bullets: wrong labels,
   misplaced boxes, phantom or missing sids, Rothöhler disagreements, swapped pairs.

Rules:
- Write only to work/signs/<sid>/ for YOUR sids, work/scratch/findings/<batch>.md, and helpers in
  work/scratch/<batch>/.
- Edit nothing else. Do not run build_data.py, finish_tracing.sh, trace_signs.sh or codex.
- Other agents trace other signs concurrently: never touch a sign not in your list. No subagents.
- If the coordinator asks you to stop, finish the current sign cleanly and stop.

Final reply: at most 5 lines. Signs traced, signs left empty, signs not done (should be none),
the number of findings written, and any tool problem.
