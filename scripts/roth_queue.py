"""Batch queue for tracing in Rothöhler's frame (Anna, 2026-11-08: continue through completion).

usage: python3 scripts/roth_queue.py next [n_batches=1]   build kits for the next batch(es), mark them launched,
                                                          and print each batch's launch brief (separated by ====)
       python3 scripts/roth_queue.py status               what is left

A batch = up to 13 untraced signs (status "untraced" in work/signlist_roth.json, with a box), in reading order,
possibly spanning consecutive units. Column 57 goes first (already started), then signlist order.
Launched batches are recorded in work/scratch/roth_launched.json {batch: [rids]}; a sign is never queued twice.
Run roth_align.py + renumber_roth.py between rounds so new kits use the latest mapping.
"""
import json
import os
import subprocess
import sys

P = "/home/anna/projects/shabaka-stone/"
LOG = P + "work/scratch/roth_launched.json"
SIZE = 13
L = json.load(open(P + "work/signlist_roth.json"))
launched = json.load(open(LOG)) if os.path.exists(LOG) else {}
done = {r for rs in launched.values() for r in rs}
# the three pilot/first batches
done |= {f"57.R{k}" for k in range(1, 50)}

order = ["57"] + [u for u in L["units"] if u != "57"]
todo = []
for u in order:
    for e in L["units"][u]:
        if e["status"] == "untraced" and e.get("box_full") and e["rid"] not in done:
            todo.append(e)


def batches():
    out, cur = [], []
    for e in todo:
        if cur and len(cur) == SIZE:  # batches may span units (small leftovers cost a whole brief otherwise)
            out.append(cur); cur = []
        cur.append(e)
    if cur:
        out.append(cur)
    return out


BRIEF = """You are an Opus tracing agent for the Shabaka Stone project (root /home/anna/projects/shabaka-stone). Batch name: {name}.

Read, in this order and in full: work/OPUS_TRACER_TASK.md, work/STROKE_BRIEF.md, and work/ROTH_FRAME_TRACING.md (the addendum for tracing in Rothöhler's numbering; it overrides the other two where they differ). For what a finished batch looks like, see work/scratch/findings/roth-57b.md and the traces in work/signs/57.R5, 57.R7 and 57.4. Then trace these {n} signs in this order (rid -> kit folder in work/signs/ : his reading):

{rows}

Before you start, fix the sequence against his column strip(s) {strips} and work/roth_inventory/<unit>.json. Side-by-side signs read LEFT TO RIGHT (line 2 and L1R signs face left; see the briefs). Other agents trace other signs at the same time: touch only your folders. Write only to the {n} kit folders above, work/scratch/findings/{name}.md and helpers in work/scratch/{name}/. No subagents. Don't run build_data.py, renumber_roth.py, roth_align.py or the kit scripts.

Final reply: at most 5 lines. Signs traced, signs left empty, signs not done, findings written, and any kit problem."""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    bs = batches()
    if cmd == "status":
        print(f"{len(todo)} signs left in {len(bs)} batches; {len(launched)} batches launched so far")
        for b in bs[:8]:
            print("  ", b[0]["rid"], "...", b[-1]["rid"], len(b))
        sys.exit(0)
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for b in bs[:k]:
        name = f"roth-{len(launched):03d}"
        rids = [e["rid"] for e in b]
        subprocess.run([sys.executable, P + "scripts/rid_kit.py", *rids], check=True, capture_output=True)
        launched[name] = rids
        json.dump(launched, open(LOG, "w"), indent=1)
        rows = "\n".join(f"{e['rid']} -> {e['alias'] or e['rid']}{'' if e['alias'] else ' (new)'} : "
                         f"{e['gardiner']} {e.get('desc', '')[:70]}" for e in b)
        units = sorted({e["unit"] for e in b}, key=order.index)
        strips = ", ".join(f"work/signs/roth_col{u}.png" for u in units)
        print(BRIEF.format(name=name, n=len(b), rows=rows, strips=strips))
        print("====")
