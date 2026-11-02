"""Check hand-written subtitles against the transcript, without audio or video.

Usage: python tools/check_subs.py sermons/<slug> [clip-id ...]

For each clip in clips.json: the kept length (start-end minus cuts) and, for
every subs.json line, how much of it matches the words spoken in that range.
build_clip.py times each line from the words it matches, so a line under 70%
was reworded too far from what was said, or falls inside a cut. Standard
library only, so it runs anywhere, cloud sessions included.
"""
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

folder = Path(sys.argv[1])
config = json.loads((folder / "clips.json").read_text(encoding="utf-8"))
words = [w for s in json.loads((folder / "words.json").read_text(encoding="utf-8")) for w in s["words"]]
wanted = set(sys.argv[2:])


def norm(text):
    return [ch for ch in text if ch.isalnum()]


problems = 0
for clip in config["clips"]:
    if wanted and clip["id"] not in wanted:
        continue
    keep, at = [], clip["start"]
    for a, b in sorted(clip.get("cut", [])):
        if a > at:
            keep.append((at, a))
        at = max(at, b)
    keep.append((at, clip["end"]))
    spoken = norm("".join(w for w, s, e in words if any(a <= (s + e) / 2 <= b for a, b in keep)))
    length = sum(b - a for a, b in keep)
    print(f"== {clip['id']}: {length:.0f} s, title {' / '.join(clip['title'])}")
    if not 25 <= length <= 125:
        problems += 1
        print(f"   length {length:.0f} s is outside 30 s - 2 min")
    subs_file = folder / "clips" / clip["id"] / "subs.json"
    if not subs_file.exists():
        print("   no subs.json yet")
        continue
    subs = json.loads(subs_file.read_text(encoding="utf-8"))
    shown, line_of = [], []
    for i, s in enumerate(subs):
        for ch in norm(s["text"]):
            shown.append(ch)
            line_of.append(i)
    hits = [0] * len(subs)
    for a, b, size in SequenceMatcher(None, shown, spoken, autojunk=False).get_matching_blocks():
        for k in range(size):
            hits[line_of[a + k]] += 1
    for i, s in enumerate(subs):
        n = len(norm(s["text"]))
        if not n or hits[i] / n < 0.7:
            problems += 1
            print(f"   line {i + 1} matches {hits[i] / max(n, 1):.0%} of the speech: {s['text']!r}")
    covered = sum(hits) / len(spoken) if spoken else 0
    print(f"   {len(subs)} lines cover {covered:.0%} of the words spoken")
    if covered < 0.85:
        problems += 1
        print("   subtitles skip too much of what is said (want 85%+)")
sys.exit(1 if problems else 0)
