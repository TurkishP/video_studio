"""Merge beats.json + timings.json + captions.json into props.json for Remotion.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/build_props.py shorts/<slug>
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

TAIL_S = 0.8  # hold the last frame after the voice ends
MIN_SHOT_MS = 900  # never cut to a new shot sooner than this
TOOLS = Path(__file__).parent


def image_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def shot_starts(n, start_ms, end_ms, word_starts):
    """Split a scene into up to n shots, cutting on the word onset nearest each even split."""
    starts = [start_ms]
    for k in range(1, n):
        target = start_ms + (end_ms - start_ms) * k / n
        options = [w for w in word_starts if starts[-1] + MIN_SHOT_MS <= w <= end_ms - MIN_SHOT_MS]
        if options:
            starts.append(min(options, key=lambda w: abs(w - target)))
    return starts


folder = Path(sys.argv[1])
beats = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
timings = json.loads((folder / "timings.json").read_text(encoding="utf-8"))
captions = json.loads((folder / "captions.json").read_text(encoding="utf-8"))
word_starts = [c["startMs"] for c in captions]

duration_ms = round((timings[-1]["end"] + TAIL_S) * 1000)
scenes, chapters = [], []
for i, (beat, t) in enumerate(zip(beats["beats"], timings)):
    # Each scene runs until the next beat starts, so there are no gaps.
    start_ms = round(t["start"] * 1000)
    end_ms = round(timings[i + 1]["start"] * 1000) if i + 1 < len(timings) else duration_ms
    visual = dict(beat["visual"])
    if visual["type"] == "image":
        visual["w"], visual["h"] = image_size(folder / visual["src"])
        shots = [dict(s) for s in visual.get("shots") or [{}]]
        if visual.pop("parallax", False):
            clip = f"assets/parallax-{i:02d}.mp4"
            if not (folder / clip).exists():
                sys.exit(f"missing {clip}: run tools/parallax.py first")
            shots[0]["clip"] = clip  # the 3D move opens the beat; later shots are punch-ins
        for shot, ms in zip(shots, shot_starts(len(shots), start_ms, end_ms, word_starts)):
            shot["startMs"] = ms
        visual["shots"] = [s for s in shots if "startMs" in s]
    elif visual["type"] == "blender":
        clip = f"assets/blender-{i:02d}.mp4"
        if not (folder / clip).exists():
            sys.exit(f"missing {clip}: run tools/blender_render.py first")
        visual = {"type": "video", "src": clip}
    chapter = None
    if beat.get("chapter"):
        chapters.append((start_ms, beat["chapter"].replace("*", "")))
        chapter = {"index": len(chapters), "title": beat["chapter"]}
    scenes.append({"startMs": start_ms, "endMs": end_ms, "visual": visual,
                   "kicker": beat.get("kicker"), "headline": beat.get("headline"),
                   "cite": beat.get("cite"), "transition": beat.get("transition"),
                   "chapter": chapter})

music = beats.get("music")
if music and not (folder / music).exists():
    sys.exit(f"music file not found: {folder / music}")

sfx = None
if any(s["transition"] in ("zoom", "flash") for s in scenes):
    (folder / "sfx").mkdir(exist_ok=True)
    shutil.copy(TOOLS / "sfx" / "whoosh.wav", folder / "sfx" / "whoosh.wav")
    sfx = "sfx/whoosh.wav"

if chapters:
    # YouTube chapters for the description: the first must be 0:00, at least
    # three, each at least 10 s long.
    if chapters[0][0] > 1000:
        chapters.insert(0, (0, "Intro"))
    chapters[0] = (0, chapters[0][1])
    stamp = lambda ms: f"{ms // 60000}:{ms // 1000 % 60:02d}"
    (folder / "chapters.txt").write_text(
        "\n".join(f"{stamp(ms)} {title}" for ms, title in chapters) + "\n", encoding="utf-8")
    bounds = [ms for ms, _ in chapters] + [duration_ms]
    if len(chapters) < 3 or min(b - a for a, b in zip(bounds, bounds[1:])) < 10000:
        print("warning: YouTube needs 3+ chapters of 10 s or more; chapters.txt won't show as chapters")

if thumb := beats.get("thumbnail"):
    tw, th = image_size(folder / thumb["src"])
    (folder / "thumb.json").write_text(json.dumps({
        "theme": beats.get("theme", "museum"), "src": thumb["src"], "w": tw, "h": th,
        "focus": thumb.get("focus", [0.5, 0.5]), "zoom": thumb.get("zoom", 1),
        "text": thumb["text"], "label": thumb.get("label")}, indent=2), encoding="utf-8")

props = {
    "format": beats.get("format", "short"),
    "theme": beats.get("theme", "bold"),
    "captionsOn": beats.get("captions", True),
    "durationMs": duration_ms,
    "voice": "voice.wav",
    "music": music,
    "musicVolume": beats.get("musicVolume", 0.12),
    "sfx": sfx,
    "scenes": scenes,
    "captions": captions,
    "sources": beats.get("sources", []),
}
(folder / "props.json").write_text(json.dumps(props, indent=2), encoding="utf-8")
print(f"props.json: {duration_ms / 1000:.1f}s, {len(scenes)} scenes, "
      f"{sum(len(s['visual'].get('shots', [1])) for s in scenes)} shots")
