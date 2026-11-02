"""Cut one clip out of a sermon for the vertical SermonClip template.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/build_clip.py sermons/<slug> <clip-id>

Needs, in the sermon folder: video.mp4 (yt-dlp), audio.wav + words.json
(transcribe.py) and clips.json:
  {"credit": "고상섭 목사 · 그사랑교회", "bar": "#2b1418",
   "clips": [{"id": "love-freedom", "start": 1063.2, "end": 1190.4,
              "cut": [[1101.0, 1104.5]], "title": ["사랑하면", "자유를 잃는다"]}]}
start/end/cut are seconds of sermon time; cut ranges are dropped (filler, asides).
Optional "outro" (top level, or per clip to override) adds a 3 s ending card:
  {"style": "bar" | "card" | "blur", "logo": "../brand/logo.png",
   "logoLight": "../brand/logo-light.png", "lines": ["주일설교 · 고상섭 목사", "..."]}
(logo paths relative to the sermon folder; logoLight has cream text for dark backgrounds).
Optional per clip "punch": [sermon seconds, ...] picks where the zoom changes
(default: once under 60 s, else twice; [] for never).

Writes clips/<id>/: source.mp4 (the section, upscaled to 1440p), track.json (where
the speaker is), subs.json and props.json. subs.json is drafted from the
transcript on the first run. Replace it with your own lines, in order, as
{"text": "...", "en": "...", "hand": true} without times (they are matched to
the spoken words): fix the text, break lines with \\n, mark key words with
*stars*, then rerun. Delete source.mp4 and track.json after changing a
clip's start, end or cuts.
"""
import json
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

PAD = 0.5  # seconds of source kept either side of the clip
TRACK_STEP = 0.1  # track.json resolution, seconds
ZOOMS = (1.0, 1.18)  # the clip holds the first; each zoom change flips to the other
PUNCH_AT = {False: (0.5,), True: (0.4, 0.75)}  # where the 1-2 changes aim, as fractions of a clip (False: under 60 s)
PUNCH_FIRST = 15.0  # no zoom change in a clip's first 15 s,
PUNCH_GAP = 15.0  # within 15 s of another change,
PUNCH_END = 8.0  # or in the last 8 s
PUNCH_NEAR_CUT = 8.0  # a cut this close to the aim takes the change (it hides the jump)
SUB_LEAD = 0.15  # seconds each subtitle appears before its first word

folder, clip_id = Path(sys.argv[1]), sys.argv[2]
config = json.loads((folder / "clips.json").read_text(encoding="utf-8"))
clip = next(c for c in config["clips"] if c["id"] == clip_id)
out = folder / "clips" / clip_id
out.mkdir(parents=True, exist_ok=True)


def quietest(t, radius=0.25):
    """The quietest 20 ms near t: whisper's word edges touch, so cutting on them can clip a syllable."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t - radius), "-t", str(2 * radius),
                          "-i", str(folder / "audio.wav"), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    rms = [np.sqrt(np.mean(x[i:i + 320] ** 2)) for i in range(0, len(x) - 320, 80)]
    return round(t - radius + (int(np.argmin(rms)) * 80 + 160) / 16000, 3)


clip["start"], clip["end"] = quietest(clip["start"]), quietest(clip["end"])
clip["cut"] = [[quietest(a), quietest(b)] for a, b in clip.get("cut", [])]
sec0, sec1 = clip["start"] - PAD, clip["end"] + PAD

# Kept ranges (sermon seconds): the clip minus its cuts.
keep, at = [], clip["start"]
for a, b in sorted(clip.get("cut", [])):
    if a > at:
        keep.append((at, a))
    at = max(at, b)
keep.append((at, clip["end"]))

# 1. The section, upscaled with Lanczos so the 9:16 window isn't a soft 405x720.
source = out / "source.mp4"
if not source.exists():
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-ss", str(sec0), "-to", str(sec1), "-i", str(folder / "video.mp4"),
                    "-ss", str(sec0), "-to", str(sec1), "-i", str(folder / "audio.wav"),
                    "-map", "0:v", "-map", "1:a",
                    "-vf", "scale=2560:1440:flags=lanczos,unsharp=5:5:0.6",
                    "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", str(source)], check=True)
    print("source.mp4 cut")

# 2. Where the speaker stands: OpenCV's person detector at 10 fps, then a
# virtual camera that only moves when he walks out of the middle of the frame.
track_file = out / "track.json"
if not track_file.exists():
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    src_w, src_h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    every = max(1, round(fps / 10))
    seen, last, n = [], None, 0
    while cap.grab():
        if n % every == 0:
            _, frame = cap.retrieve()
            small = cv2.resize(frame, (640, 360))
            boxes, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
            best = None
            for (x, y, w, h), score in zip(boxes, np.ravel(weights)):
                if not 110 <= h <= 330:  # a standing adult, not a face on a slide
                    continue
                cx = (x + w / 2) / 640
                value = score - (4 * abs(cx - last) if last is not None else 0)
                if best is None or value > best[0]:
                    best = (value, cx)
            if best:
                last = best[1]
            seen.append(last)
        n += 1
    cap.release()
    first = next((x for x in seen if x is not None), 0.5)
    xs = np.array([x if x is not None else first for x in seen])
    xs = np.array([np.median(xs[max(0, i - 4):i + 5]) for i in range(len(xs))])  # ~1 s median
    crop_w = (src_h * 9 / 16) / src_w
    deadzone = 0.22 * crop_w
    cam, track = xs[0], []
    for i in range(int((sec1 - sec0) / TRACK_STEP) + 1):
        target = xs[min(len(xs) - 1, int(i * TRACK_STEP * 10))]
        if abs(target - cam) > deadzone:
            cam += 0.08 * (target - cam - np.sign(target - cam) * deadzone)
        cam = min(max(cam, crop_w / 2), 1 - crop_w / 2)
        track.append(round(float(cam), 4))
    track_file.write_text(json.dumps(track), encoding="utf-8")
    print(f"track.json: speaker found in {sum(x is not None for x in seen)}/{len(seen)} samples")
track = json.loads(track_file.read_text(encoding="utf-8"))

# Words inside the kept ranges, on the output timeline.
words = [w for s in json.loads((folder / "words.json").read_text(encoding="utf-8")) for w in s["words"]]


def to_out(t, clamp=False):
    """Sermon seconds -> output seconds; None if t falls in a cut, unless clamp moves it to the nearest kept edge."""
    done, edges = 0.0, []
    for a, b in keep:
        if a <= t <= b:
            return done + t - a
        edges += [(abs(t - a), done), (abs(t - b), done + b - a)]
        done += b - a
    return min(edges)[1] if clamp else None


kept_words = [(w, s, e) for w, s, e in words if to_out((s + e) / 2) is not None]

# 3. Phrases: subtitle-sized runs of words, broken at pauses, sentence ends and length.
chunks, cur = [], []
for k, (w, s, e) in enumerate(kept_words):
    cur.append((w, s, e))
    chars = sum(len(x[0]) for x in cur)
    nxt = kept_words[k + 1] if k + 1 < len(kept_words) else None
    pause = nxt is None or nxt[1] - e > 0.45 or to_out(nxt[1]) is None
    if pause or chars >= 16 or (chars >= 13 and w[-1] in ".?!,"):
        chunks.append(cur)
        cur = []

# 4. Segments and zoom. The frame stays on the preacher at one zoom and changes
# it only once (clips under 60 s) or twice, so the eye stays on him. A change
# lands on a cut when one is near (it hides the jump), else on a pause between
# phrases. clips.json can set the moments itself: "punch": [sermon seconds, ...]
# ([] for none); each snaps to the nearest cut or pause.
lengths = [b - a for a, b in keep]
total = sum(lengths)
cut_points = [sum(lengths[:k]) for k in range(1, len(keep))]  # output seconds where a cut joins two ranges
pauses = [t for t in (to_out(c[-1][2]) for c in chunks[:-1])
          if t is not None and all(abs(t - u) >= 0.5 for u in [0.0, total, *cut_points])]


def nearest(t, options):
    return min(options, key=lambda u: abs(u - t)) if options else None


if "punch" in clip:
    switches = [nearest(to_out(t, clamp=True), cut_points + pauses) for t in clip["punch"]]
else:
    switches = []
    for aim in PUNCH_AT[total >= 60]:
        def ok(t):
            return PUNCH_FIRST <= t <= total - PUNCH_END and all(abs(t - u) >= PUNCH_GAP for u in switches)
        near = [t for t in cut_points if ok(t) and abs(t - aim * total) <= PUNCH_NEAR_CUT]
        switches.append(nearest(aim * total, near or [t for t in pauses if ok(t)]))
switches = sorted({t for t in switches if t is not None})


def to_sermon(t):
    """Output seconds -> sermon seconds (the end of a kept range, at a cut)."""
    done = 0.0
    for a, b in keep:
        if t <= done + b - a + 1e-6:
            return a + t - done
        done += b - a
    return keep[-1][1]


switch_ranges = {k for k, c in enumerate(cut_points, 1) if c in switches}  # kept ranges that open with a change
splits = sorted(quietest(to_sermon(t), 0.15) for t in switches if t not in cut_points)
segments = []  # (sermon start, sermon end, zoom changes here)
for k, (a, b) in enumerate(keep):
    start, change = a, k in switch_ranges
    for g in splits:
        if start < g < b:
            segments.append((start, g, change))
            start, change = g, True
    segments.append((start, b, change))
props_segments, zoom = [], 0
for a, b, change in segments:
    zoom += change
    props_segments.append({"fromMs": round((a - sec0) * 1000), "toMs": round((b - sec0) * 1000),
                           "zoom": ZOOMS[zoom % 2]})

# 5. Subtitles: drafted once from the phrases, then hand-edited.
subs_file = out / "subs.json"
if not subs_file.exists():
    subs = []
    for k, c in enumerate(chunks):
        start = to_out(c[0][1], clamp=True)
        end = to_out(c[-1][2], clamp=True) + 0.6
        if k + 1 < len(chunks):
            end = min(end, to_out(chunks[k + 1][0][1], clamp=True))
        subs.append({"startMs": round(start * 1000), "endMs": round(end * 1000),
                     "text": " ".join(x[0] for x in c), "en": None, "hand": False})
    subs_file.write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"subs.json drafted ({len(subs)} lines): edit it, then rerun")
subs = json.loads(subs_file.read_text(encoding="utf-8"))

# Lines written by hand without times get them from the words they match.
if any("startMs" not in s for s in subs):
    def norm(text):
        return [ch for ch in text if ch.isalnum()]

    ref, owner = [], []
    for w, s, e in kept_words:
        for ch in norm(w):
            ref.append(ch)
            owner.append((s, e))
    hyp, line_of = [], []
    for i, s in enumerate(subs):
        for ch in norm(s["text"]):
            hyp.append(ch)
            line_of.append(i)
    hit = {}
    for a, b, size in SequenceMatcher(None, hyp, ref, autojunk=False).get_matching_blocks():
        for k in range(size):
            hit[a + k] = b + k
    spans = {}
    for k, i in enumerate(line_of):
        if k in hit:
            lo, hi = spans.get(i, (hit[k], hit[k]))
            spans[i] = (min(lo, hit[k]), max(hi, hit[k]))
    for i, s in enumerate(subs):
        if "startMs" in s:
            continue
        if i not in spans:
            sys.exit(f"subs.json line {i + 1} matches nothing in the transcript: {s['text']}")
        # A line shown slightly early reads as in sync; a late one doesn't.
        s["startMs"] = max(0, round((to_out(owner[spans[i][0]][0], clamp=True) - SUB_LEAD) * 1000))
        s["endMs"] = round((to_out(owner[spans[i][1]][1], clamp=True) + 0.3) * 1000)
    if subs[0]["startMs"] < 1000:
        subs[0]["startMs"] = 0
    for s, nxt in zip(subs, subs[1:]):
        s["endMs"] = min(s["endMs"], nxt["startMs"])

probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(source)], capture_output=True, text=True, check=True).stdout
src_w, src_h = map(int, probe.strip().split(",")[:2])
# Ending card: the logo files are copied in because the clip folder is Remotion's public dir.
outro = clip.get("outro", config.get("outro"))
if outro:
    for key, name in (("logo", "logo.png"), ("logoLight", "logo-light.png")):
        shutil.copy(folder / outro[key], out / name)
    outro = {"style": outro.get("style", "bar"), "logo": "logo.png", "logoLight": "logo-light.png",
             "lines": outro["lines"]}

props = {"video": "source.mp4", "srcW": src_w, "srcH": src_h, "segments": props_segments, "track": track,
         "title": clip["title"], "credit": config.get("credit", ""), "bar": config.get("bar", "#2b1418"),
         "subtitles": subs, "outro": outro}
(out / "props.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
stamps = ", ".join(f"{t:.0f}s" for t in switches) or "none"
print(f"props.json: {total:.1f}s, {len(segments)} segments, zoom changes at {stamps}, {len(subs)} subtitle lines")
