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
The card also names the source sermon: the first two " | " parts of the top-level "sermon".

Writes clips/<id>/: source.mp4 (the section, upscaled to 1440p), speaker.json (where
the speaker is), track.json (the camera), plate.jpg (the empty stage, filling in when
the window runs past the frame edge), subs.json and props.json. subs.json is drafted from the
transcript on the first run. Replace it with your own lines, in order, as
{"text": "...", "en": "...", "hand": true} without times (they are matched to
the spoken words): fix the text, break lines with \\n, mark key words with
*stars*, then rerun. The picture punches in only on "hand" lines; set
"zoom": true or false on a line to override. Delete source.mp4, speaker.json and
plate.jpg after changing a clip's start, end or cuts.
"""
import json
import shutil
import subprocess
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

PAD = 0.5  # seconds of source kept either side of the clip
TRACK_STEP = 0.1  # track.json resolution, seconds
ZOOM_IN = 1.18  # punch-in for the lines that carry the point
ZOOM_MIN = 2.2  # seconds a punch-in lasts at least
EDGE = 0.12  # of the window width: margin kept between the speaker and the side of the shot
PAN_AFTER = 0.6  # seconds he must be outside the shot before the camera moves
PAN_TIME = 0.8  # seconds a pan takes, eased
HOLD = 3.0  # seconds: a stay shorter than this is him walking, not a new place to frame
STILL = 2.0  # seconds a box may sit on exactly the same pixels before it counts as part of the set
REACH = 0.25  # of the window width: how far the window may run past the frame edge
STEP = 0.06  # of the frame width: how far the speaker can move between two detections (0.2 s apart)
JUMP_AFTER = 2.4  # seconds a detection far from him must hold before the camera believes it
SUB_LEAD = 0.15  # seconds each subtitle appears before its first word
SR = 16000

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

pcm = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", str(sec0), "-to", str(sec1),
                                    "-i", str(folder / "audio.wav"), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                   capture_output=True, check=True).stdout, np.float32)


def onset(a, b):
    """When the word a-b starts to sound. Whisper stretches a word's start back over the pause
    before it, so the window can also hold the last of the previous word: the word is the
    longest run of sound in it (dips under 0.1 s, like a stop consonant, don't break a run)."""
    x = pcm[max(0, int((a - sec0) * SR)):max(0, int((b - sec0) * SR))]
    n = len(x) // 320
    if n < 2:
        return a
    db = 20 * np.log10(np.sqrt(np.mean(x[:n * 320].reshape(n, 320) ** 2, axis=1)) + 1e-9)
    loud = db >= min(db.min() + 15, db.max() - 20)  # well above the pause, even for a soft first syllable
    runs, k = [], 0
    while k < n:
        if loud[k]:
            j = k
            while j < n and loud[j:j + 5].any():
                j += 1
            runs.append((j - k, k))
            k = j
        else:
            k += 1
    return a + 0.02 * max(runs)[1] if runs else a

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

probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(source)], capture_output=True, text=True, check=True).stdout
src_w, src_h = map(int, probe.strip().split(",")[:2])

# 2. Where people are, 5 times a second (speaker.json, boxes in 1280x720 pixels):
# faces (frontal and profile) and OpenCV's person detector. Faces still find him
# when he stands half out of the shot.
speaker_file = out / "speaker.json"
if not speaker_file.exists():
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    faces = [cv2.CascadeClassifier(cv2.data.haarcascades + f"haarcascade_{n}.xml")
             for n in ("frontalface_default", "profileface")]
    every = max(1, round(fps / 5))
    boxes_at, n = [], 0  # per sample: candidate boxes in 1280x720 pixels
    while cap.grab():
        if n % every == 0:
            _, frame = cap.retrieve()
            gray = cv2.cvtColor(cv2.resize(frame, (1280, 720)), cv2.COLOR_BGR2GRAY)
            found = [tuple(b) for f in faces for b in f.detectMultiScale(gray[:520], 1.1, 5, minSize=(24, 24))]
            bodies, _ = hog.detectMultiScale(cv2.resize(frame, (640, 360)), winStride=(8, 8), padding=(8, 8), scale=1.05)
            found += [(2 * x, 2 * y, 2 * w, 2 * h) for x, y, w, h in bodies if 110 <= h <= 330]  # a standing adult
            boxes_at.append([[int(v) for v in b] for b in found])
        n += 1
    cap.release()
    speaker_file.write_text(json.dumps(boxes_at), encoding="utf-8")
boxes_at = json.loads(speaker_file.read_text(encoding="utf-8"))
# A box that sits in exactly the same place for STILL s in all is part of the set
# (a pattern, a face on a slide or a book cover); a speaking head never keeps that still.
key = lambda b: tuple(round(v / 4) for v in b)  # noqa: E731
counts = Counter(key(b) for found in boxes_at for b in found)
# Faces (square boxes) far from his usual face size are the wall or the slide, not him.
sizes = [h for found in boxes_at for x, y, w, h in found if w == h]
face = float(np.median(sizes)) if sizes else 0.0
cands = [[(x + w / 2) / 1280 for x, y, w, h in found if counts[key((x, y, w, h))] < STILL * 5
          and (w != h or 0.6 * face <= h <= 1.5 * face)] for found in boxes_at]
print(f"speaker.json: speaker found in {sum(bool(c) for c in cands)}/{len(cands)} samples")

# He walks, so from one sample to the next he moves only a little (STEP). A box
# far from him (a face on a slide, someone in the front row) counts only if it
# stays put for JUMP_AFTER s: then he really is over there.
pool = [x for c in cands for x in c]
last = float(np.median(pool)) if pool else 0.5
seen, found, pending = [], 0, None
for c in cands:
    near = [x for x in c if abs(x - last) < STEP]
    if near:
        last, pending = min(near, key=lambda x: abs(x - last)), None
        found += 1
    elif c:
        x = min(c, key=lambda x: abs(x - (pending[0] if pending else last)))
        pending = (x, pending[1] + 1) if pending and abs(x - pending[0]) < STEP else (x, 1)
        if pending[1] >= JUMP_AFTER * 5:
            last, pending = pending[0], None
            found += 1
    seen.append(last if found else None)  # lost him: hold where he was last seen
first = next((x for x in seen if x is not None), 0.5)
xs = np.array([x if x is not None else first for x in seen])
xs = [float(np.median(xs[max(0, i - 2):i + 3])) for i in range(len(xs))]  # ~1 s median

# 3. The virtual camera (track.json) holds still and moves only when he leaves
# the shot. His path is split into holds, each lasting while every place he
# stands fits in one shot (EDGE clear of its sides), framed on the middle of them;
# a step outside shorter than PAN_AFTER s (a gesture, a missed detection) doesn't
# end a hold. Holds under HOLD s are him walking: the camera moves through them
# in one go instead of stepping, and otherwise pans in PAN_TIME s.
crop_w = (src_h * 9 / 16) / src_w
cam_lo, cam_hi = crop_w / 2 - REACH * crop_w, 1 - crop_w / 2 + REACH * crop_w
frame_on = lambda x: min(max(x, cam_lo), cam_hi)  # noqa: E731
fit, n_xs, holds, k = (1 - 2 * EDGE) * crop_w, len(xs), [], 0
while k < n_xs:
    lo, hi, j, first_out = xs[k], xs[k], k + 1, None
    while j < n_xs:
        if max(hi, xs[j]) - min(lo, xs[j]) <= fit:
            lo, hi, first_out = min(lo, xs[j]), max(hi, xs[j]), None
        elif first_out is None:
            first_out = j
        elif (j - first_out + 1) / 5 >= PAN_AFTER:
            break
        j += 1
    end = first_out if first_out is not None and j < n_xs else n_xs
    holds.append((k / 5, end / 5, frame_on((lo + hi) / 2)))
    k = end
holds = [h for i, h in enumerate(holds) if i in (0, len(holds) - 1) or h[1] - h[0] >= HOLD]
track = []
for i in range(int((sec1 - sec0) / TRACK_STEP) + 1):
    t, cam = i * TRACK_STEP, holds[-1][2]
    for (_, a_end, a_cam), (b_start, _, b_cam) in zip(holds, holds[1:]):
        if t < b_start + PAN_TIME:
            p0, p1 = (a_end, b_start) if b_start - a_end >= PAN_TIME else (b_start, b_start + PAN_TIME)
            u = min(max((t - p0) / (p1 - p0), 0.0), 1.0)
            cam = a_cam + (b_cam - a_cam) * u * u * (3 - 2 * u)
            break
    track.append(round(cam, 4))
(out / "track.json").write_text(json.dumps(track), encoding="utf-8")

# The stage without the speaker (the median of frames across the clip): mirrored
# and blurred, it fills in where the window runs past the frame edge.
plate = out / "plate.jpg"
if not plate.exists():
    cap = cv2.VideoCapture(str(source))
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    frames = []
    for k in range(15):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(count * (k + 0.5) / 15))
        ok, frame = cap.read()
        if ok:
            frames.append(cv2.resize(frame, (960, 540)))
    cap.release()
    cv2.imwrite(str(plate), np.median(frames, axis=0).astype(np.uint8))

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

# 4. Phrases: subtitle-sized runs of words, broken at pauses, sentence ends and length.
chunks, cur = [], []
for k, (w, s, e) in enumerate(kept_words):
    cur.append((w, s, e))
    chars = sum(len(x[0]) for x in cur)
    nxt = kept_words[k + 1] if k + 1 < len(kept_words) else None
    pause = nxt is None or nxt[1] - e > 0.45 or to_out(nxt[1]) is None
    if pause or chars >= 16 or (chars >= 13 and w[-1] in ".?!,"):
        chunks.append(cur)
        cur = []

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

# Each line is matched to the words it quotes: lines written by hand without
# times get them from those words, and the zoom below lands on them.
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
if any("startMs" not in s for s in subs):
    for i, s in enumerate(subs):
        if "startMs" in s:
            continue
        if i not in spans:
            sys.exit(f"subs.json line {i + 1} matches nothing in the transcript: {s['text']}")
        # A line shown slightly early reads as in sync; a late one doesn't.
        s["startMs"] = max(0, round((to_out(onset(*owner[spans[i][0]]), clamp=True) - SUB_LEAD) * 1000))
        s["endMs"] = round((to_out(owner[spans[i][1]][1], clamp=True) + 0.3) * 1000)
    if subs[0]["startMs"] < 1000:
        subs[0]["startMs"] = 0
    for s, nxt in zip(subs, subs[1:]):
        s["endMs"] = min(s["endMs"], nxt["startMs"])

# 6. Segments: the kept ranges, punched in only while the marked lines are spoken.
zooms, prev = [], None
for i, s in enumerate(subs):
    if s.get("zoom", s.get("hand")) and i in spans:
        a = quietest(onset(*owner[spans[i][0]]) - 0.1, 0.1)
        b = max(quietest(owner[spans[i][1]][1], 0.15), quietest(a + ZOOM_MIN))
        # Consecutive lines, or ones under a second apart once cuts are out, share one punch-in.
        if zooms and (i == prev + 1 or to_out(a, clamp=True) - to_out(zooms[-1][1], clamp=True) < 1.0):
            zooms[-1][1] = b
        else:
            zooms.append([a, b])
        prev = i
segments = []
for a, b in keep:
    edges = sorted({a, b, *(t for z in zooms for t in z if a + 1.0 < t < b - 1.0)})
    for x, y in zip(edges, edges[1:]):
        zoomed = any(za <= (x + y) / 2 <= zb for za, zb in zooms)
        segments.append((x, y, ZOOM_IN if zoomed else 1.0))
props_segments = [{"fromMs": round((a - sec0) * 1000), "toMs": round((b - sec0) * 1000), "zoom": z}
                  for a, b, z in segments]

# Ending card: the logo files are copied in because the clip folder is Remotion's public dir.
outro = clip.get("outro", config.get("outro"))
if outro:
    for key, name in (("logo", "logo.png"), ("logoLight", "logo-light.png")):
        shutil.copy(folder / outro[key], out / name)
    outro = {"style": outro.get("style", "bar"), "logo": "logo.png", "logoLight": "logo-light.png",
             "lines": outro["lines"]}
    if config.get("sermon"):  # e.g. ["은혜는 자기합리화를 내려놓게 한다", "The Gospel Again (8)"]
        outro["sermon"] = [part.strip() for part in config["sermon"].split("|")[:2]]

subtitles = [{k: v for k, v in s.items() if k != "zoom"} for s in subs]
props = {"video": "source.mp4", "plate": "plate.jpg", "srcW": src_w, "srcH": src_h, "segments": props_segments,
         "track": track, "title": clip["title"], "credit": config.get("credit", ""),
         "bar": config.get("bar", "#2b1418"), "subtitles": subtitles, "outro": outro}
(out / "props.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
total = sum(b - a for a, b in keep)
print(f"props.json: {total:.1f}s, {len(segments)} segments, {len(zooms)} punch-ins, {len(subs)} subtitle lines")
