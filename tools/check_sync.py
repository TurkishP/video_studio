"""Check a rendered sermon clip's subtitles against what is actually heard.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/check_sync.py sermons/<slug>/clips/<id> [...]

Transcribes clip.mp4 again and prints, for each subtitle, when it appears and
when its first words are heard. Offsets should sit within about ±0.3 s; a
steady offset on every line means the audio was cut from the wrong place.
Repeated phrases can show a false offset on the second occurrence.
"""
import json
import os
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
TORCH_LIB = TOOLS / ".venv-tts" / "Lib" / "site-packages" / "torch" / "lib"
if TORCH_LIB.exists():  # same CUDA libraries as transcribe.py
    os.environ["PATH"] = f"{TORCH_LIB}{os.pathsep}{os.environ['PATH']}"
    os.add_dll_directory(str(TORCH_LIB))
from faster_whisper import WhisperModel  # noqa: E402

def onset(x, a, b):
    """When speech starts in the word a-b (same rule as build_clip.py): whisper's word starts swallow pauses."""
    x = x[int(a * 16000):int(b * 16000)]
    n = len(x) // 320
    if n < 2:
        return a
    db = 20 * np.log10(np.sqrt(np.mean(x[:n * 320].reshape(n, 320) ** 2, axis=1)) + 1e-9)
    loud = db >= min(db.min() + 15, db.max() - 20)
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


model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16",
                     download_root=str(TOOLS / "models" / "whisper"))
for folder in map(Path, sys.argv[1:]):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-i", str(folder / "clip.mp4"), "-f", "f32le", "-ac", "1",
                          "-ar", "16000", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)
    segments, _ = model.transcribe(audio, language="ko", word_timestamps=True, condition_on_previous_text=False)
    heard, when = [], []
    for s in segments:
        for w in s.words:
            t = onset(audio, w.start, w.end)
            for ch in w.word:
                if ch.isalnum():
                    heard.append(ch)
                    when.append(t)
    subs = json.loads((folder / "props.json").read_text(encoding="utf-8"))["subtitles"]
    shown, line_of = [], []
    for i, s in enumerate(subs):
        for ch in s["text"]:
            if ch.isalnum():
                shown.append(ch)
                line_of.append(i)
    first = {}
    for a, b, size in SequenceMatcher(None, shown, heard, autojunk=False).get_matching_blocks():
        for k in range(size):
            first.setdefault(line_of[a + k], when[b + k])
    offsets = []
    print(f"== {folder.name}")
    for i, s in enumerate(subs):
        t = first.get(i)
        if t is not None:
            offsets.append(s["startMs"] / 1000 - t)
        mark = "  (not heard)" if t is None else f"{s['startMs'] / 1000 - t:+6.2f}s"
        print(f"{s['startMs'] / 1000:6.2f}  {mark}  {s['text'].replace(chr(10), ' ')[:28]}")
    print(f"median offset {np.median(offsets):+.2f}s, {sum(abs(o) > 0.3 for o in offsets)} lines beyond ±0.3 s")
