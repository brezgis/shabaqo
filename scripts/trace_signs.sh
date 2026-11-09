#!/usr/bin/env bash
# Trace signs with Codex, one sign per run, N in parallel.
# usage: trace_signs.sh <parallelism> <sid> [sid...]     (kits must exist: scripts/sign_kit.py)
#        trace_signs.sh <parallelism> --file <list.txt>  (whitespace-separated sids)
#
# - Skips signs that already have trace.json (so a re-run resumes where it stopped).
# - If Codex reports a usage/rate limit, writes work/signs/STOP and every job stops before
#   starting another sign; the limited sign keeps no trace.json, so the next run retries it.
#   Delete work/signs/STOP (the script does this at start) to run again after the reset.
# - After each trace, scripts/trace_qa.py runs and its line is appended to work/signs/qa_log.jsonl.
set -u
cd /home/anna/projects/shabaka-stone
PAR="$1"; shift
if [ "${1:-}" = "--file" ]; then set -- $(cat "$2"); fi
STOP=work/signs/STOP
rm -f "$STOP"
export STOP

one() {
  sid="$1"; k="work/signs/$sid"
  [ -f "$STOP" ] && { echo "stopped $sid"; return 0; }
  [ -f "$k/trace.json" ] && { echo "skip $sid"; return 0; }
  [ -d "$k" ] || { echo "no kit $sid"; return 0; }
  unit="${sid%%.*}"
  roth=""; [ -f "work/signs/roth_col$unit.png" ] && roth="Rothöhler's column strip for shape reference: work/signs/roth_col$unit.png."
  v2=""; grep -q '"kit": "v2"' "$k/meta.json" 2>/dev/null && v2="This is a v2 kit: read the section 'v2 kits' in the brief."
  prev=""; [ -f "$k/trace_prev.json" ] && prev="An earlier trace of this sign is in $k/trace_prev.json (already in this kit's coordinates; render it with: python3 scripts/render_trace.py $k trace_prev.json). Keep what is right, complete what it missed, fix what is off."
  echo "Read work/STROKE_BRIEF.md and follow it for exactly one sign: sid $sid (kit: $k/). $v2 $prev $roth To look at any image file (context.png, check.png after each render, native.png, the Rothöhler strip) use your image-viewing tool on the file path. Iterate until the trace sits on the grooves and covers the whole carved sign, then stop and reply with a two-line summary." \
    | timeout 900 codex exec -s workspace-write --skip-git-repo-check -C "$PWD" -i "$k/grid.png" -i "$k/relief.png" - > "$k/codex_log.txt" 2>&1
  if grep -qiE "usage limit|rate limit|quota exceeded|too many requests" "$k/codex_log.txt" && [ ! -f "$k/trace.json" ]; then
    echo "$(date '+%F %T') $sid: $(grep -iE -m1 'usage limit|rate limit|quota|too many' "$k/codex_log.txt")" > "$STOP"
    mv "$k/codex_log.txt" "$k/codex_log_limit.txt"
    echo "LIMIT $sid (batch stopping; see $STOP)"
    return 0
  fi
  if [ -f "$k/trace.json" ]; then
    q=$(python3 scripts/trace_qa.py "$sid" 2>/dev/null | tail -1)
    echo "$q" >> work/signs/qa_log.jsonl
    echo "done $sid $q"
  else
    echo "FAIL $sid"
  fi
}
export -f one
printf '%s\n' "$@" | xargs -P "$PAR" -I{} bash -c 'one "$@"' _ {}
if [ -f "$STOP" ]; then echo "Stopped early: $(cat "$STOP")"; exit 3; fi
