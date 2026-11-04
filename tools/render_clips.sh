#!/usr/bin/env bash
# Build, render and sync-check every clip of the given sermons. Clips that
# already have clip.mp4 are skipped, so a stopped run can simply be restarted
# (delete a clip's clip.mp4 to redo it).
#
# Usage: bash tools/render_clips.sh sermons/gospel-again-02 [sermons/...]
# Progress: sermons/render-log.txt. Sync report: sermons/sync-report.txt.
# Finished clips are copied to sermons/upload/ga-02_<id>.mp4 and so on.
# Takes ~4 min per minute of clip. To survive the session ending, start it as
# its own process (Start-Process from PowerShell).
cd "$(dirname "$0")/.." || exit 1
export PY="tools/.venv/Scripts/python.exe -I -X utf8"
export LOG=sermons/render-log.txt
echo "start $(date '+%F %T')" > $LOG

# Windows Python prints \r\n; tr keeps the clip ids clean.
list=$(for S in "$@"; do
  $PY -c "import json,sys; [print(sys.argv[1], c['id']) for c in json.load(open(sys.argv[1] + '/clips.json', encoding='utf-8'))['clips']]" "$S" | tr -d '\r'
done)
echo "$(echo "$list" | wc -l) clips" >> $LOG

# 1. Cut, track and write props, three clips at a time.
build() {
  [ -f "$1/clips/$2/clip.mp4" ] && return
  mkdir -p "$1/clips/$2"
  if $PY tools/build_clip.py "$1" "$2" > "$1/clips/$2/build.log" 2>&1; then echo "built $1 $2" >> $LOG
  else echo "BUILD FAILED $1 $2" >> $LOG; fi
}
export -f build
echo "$list" | xargs -P 3 -n 2 bash -c 'build "$0" "$1"'

# 2. Render one at a time; retry once with a longer timeout (Korean fonts can be slow to load).
# The list is read on fd 3: npx and ffmpeg read stdin and would swallow clip names.
while read -r S id <&3; do
  C=$S/clips/$id
  [ -f "$C/clip.mp4" ] || [ ! -f "$C/props.json" ] && continue
  ok=
  for t in 90000 180000; do
    npx remotion render SermonClip "$C/raw.mp4" --props="$C/props.json" --public-dir="$C" --timeout=$t --log=error \
      > "$C/render.log" 2>&1 && ok=1 && break
  done
  if [ -n "$ok" ] && $PY tools/loudnorm.py "$C/raw.mp4" "$C/clip.mp4" > /dev/null; then
    ffmpeg -nostdin -v error -y -i "$C/clip.mp4" -c:v libx264 -crf 27 -preset fast -c:a copy "$C/preview.mp4"
    # Every finished clip also goes to sermons/upload as ga-<sermon no.>_<id>.mp4, ready to post.
    mkdir -p sermons/upload && cp -f "$C/clip.mp4" "sermons/upload/ga-${S##*-}_$id.mp4"
    echo "rendered $S $id $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$C/clip.mp4")s" >> $LOG
  else
    echo "RENDER FAILED $S $id" >> $LOG
  fi
done 3<<< "$list"

# 3. Subtitle sync on everything finished.
dirs=$(echo "$list" | while read -r S id; do [ -f "$S/clips/$id/clip.mp4" ] && echo "$S/clips/$id"; done)
$PY tools/check_sync.py $dirs 2>&1 | grep -E "^==|median" > sermons/sync-report.txt
echo "done $(date '+%F %T'): $(echo "$dirs" | grep -c .) of $(echo "$list" | wc -l) clips finished, $(grep -c FAILED $LOG) failures" >> $LOG
