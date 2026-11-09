#!/usr/bin/env bash
# Finish the per-sign stroke tracing in safe phases. Re-run it after a usage-limit stop: every
# phase skips signs that already have trace.json, so it resumes where it stopped.
#
# usage: nice bash scripts/finish_tracing.sh [parallelism=3] [--dry-run]
#
#   1. seeds   untraced seed signs (work/signs/seeds.txt) get wide v2 kits and are traced first,
#              because the other signs' positions are re-estimated from them
#   2. rebuild web/data/stone.json (positions re-fitted around the new traces)
#   3. rest    every other untraced sign gets a v2 kit (box grown to the typical size of its sign
#              type, untraced neighbours shown as approximate) and is traced
#   4. touchup first-round traces flagged clipped / incomplete / off_cut by scripts/trace_qa.py get a
#              v2 kit with their old trace as a starting point (old kit backed up) and one re-trace
#   5. rebuild + QA report; work/review.txt lists what a person should look at
# Exit 3 = stopped by a Codex usage limit (see work/signs/STOP); run again after the reset.
set -u
cd /home/anna/projects/shabaka-stone
PAR="${1:-3}"; DRY=""; [ "${2:-}" = "--dry-run" ] && DRY=1
S=work/signs
mkdir -p work/scratch/kit_touchup/runs
backup_data() { cp web/data/stone.json "work/scratch/kit_touchup/runs/stone.$(date +%Y%m%d-%H%M%S).json"; }
untraced() {  # untraced() <only-file|-> <exclude-file|->: sids with a box and no trace.json, reading order
  python3 - "$1" "$2" <<'EOF'
import json, os, sys
D = json.load(open("web/data/stone.json"))
only = set(open(sys.argv[1]).read().split()) if sys.argv[1] != "-" else None
excl = set(open(sys.argv[2]).read().split()) if sys.argv[2] != "-" else set()
for s in D["signs"]:
    sid = s["sid"]
    if not s.get("box") or os.path.exists(f"work/signs/{sid}/trace.json"):
        continue
    if (only is None or sid in only) and sid not in excl:
        print(sid)
EOF
}
run() {  # trace a list; stop the whole script on a usage limit
  [ $# -eq 0 ] && return 0
  if [ -n "$DRY" ]; then echo "  would trace $# signs: $* " | cut -c1-300; return 0; fi
  bash scripts/trace_signs.sh "$PAR" "$@"; rc=$?
  if [ $rc -eq 3 ]; then echo "Usage limit: stopping. Run this script again after the reset."; exit 3; fi
}

echo "== 1. seeds"
SEEDS=$(untraced $S/seeds.txt -)
echo "$(echo $SEEDS | wc -w) untraced seeds"
[ -n "$SEEDS" ] && [ -z "$DRY" ] && python3 scripts/sign_kit.py --sids $SEEDS --v2 --seed > /dev/null
run $SEEDS

echo "== 2. rebuild positions"
[ -z "$DRY" ] && { backup_data; python3 scripts/build_data.py | tail -1; }

echo "== 3. remaining untraced signs"
REST=$(untraced - $S/seeds.txt)
echo "$(echo $REST | wc -w) signs"
[ -n "$REST" ] && [ -z "$DRY" ] && python3 scripts/sign_kit.py --sids $REST --v2 > /dev/null
run $REST

echo "== 4. touch-up of first-round traces"
RQ=$(python3 scripts/trace_qa.py --requeue)
echo "$(echo $RQ | wc -w) signs to re-trace"
[ -n "$RQ" ] && [ -z "$DRY" ] && python3 scripts/sign_kit.py --sids $RQ --v2 --retrace > /dev/null
run $RQ

echo "== 5. rebuild + QA"
if [ -z "$DRY" ]; then
  backup_data; python3 scripts/build_data.py | tail -1
  python3 scripts/trace_qa.py --all --write
  python3 scripts/trace_qa.py --review | tr ' ' '\n' > work/review.txt
  echo "$(wc -l < work/review.txt) signs listed in work/review.txt for a person to check"
fi
