"""Word-level captions with faster-whisper, spelled exactly as the script.

Usage: tools/.venv/Scripts/python.exe -I tools/captions.py shorts/<slug>

Transcribes voice.wav for timing only, then maps the timings back onto the
script's own words so captions never show transcription typos.
Writes captions.json in Remotion's Caption format.
"""
import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

MODELS = Path(__file__).parent / "models" / "whisper"

folder = Path(sys.argv[1])
beats = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
script_words = " ".join(b["text"] for b in beats["beats"]).split()


def norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


# Decode with FFmpeg: faster-whisper's own decoder breaks on PyAV 19.
raw = subprocess.run(
    ["ffmpeg", "-nostdin", "-i", str(folder / "voice.wav"),
     "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
    capture_output=True, check=True,
).stdout
model = WhisperModel("small.en", device="cpu", compute_type="int8", download_root=str(MODELS))
segments, _ = model.transcribe(
    np.frombuffer(raw, np.float32), language="en", word_timestamps=True,
    initial_prompt=" ".join(script_words).replace("*", ""),
)
heard = [(w.start, w.end, norm(w.word)) for s in segments for w in s.words]

times = [None] * len(script_words)
matcher = SequenceMatcher(None, [norm(w) for w in script_words], [h[2] for h in heard], autojunk=False)
for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
        for k in range(i2 - i1):
            times[i1 + k] = heard[j1 + k][:2]
    elif tag == "replace":  # e.g. "3,000" heard as "three thousand": spread evenly
        start, end, n = heard[j1][0], heard[j2 - 1][1], i2 - i1
        for k in range(n):
            times[i1 + k] = (start + (end - start) * k / n, start + (end - start) * (k + 1) / n)

# Script words whisper missed entirely: interpolate between their neighbours.
missed = times.count(None)
i = 0
while i < len(times):
    if times[i] is not None:
        i += 1
        continue
    j = i
    while j < len(times) and times[j] is None:
        j += 1
    start = times[i - 1][1] if i > 0 else 0.0
    end = times[j][0] if j < len(times) else start + 0.3 * (j - i)
    for k in range(i, j):
        times[k] = (start + (end - start) * (k - i) / (j - i), start + (end - start) * (k - i + 1) / (j - i))
    i = j

captions = [
    {
        "text": (" " if n else "") + word,
        "startMs": round(s * 1000),
        "endMs": round(e * 1000),
        "timestampMs": round((s + e) * 500),
        "confidence": None,
    }
    for n, (word, (s, e)) in enumerate(zip(script_words, times))
]
(folder / "captions.json").write_text(json.dumps(captions, indent=2), encoding="utf-8")

# Engines that voice the whole script in one pass (tts_qwen.py) leave no beat
# timings, so derive them from the words: a beat starts just before its first word.
if not (folder / "timings.json").exists():
    timings, i, prev_end = [], 0, 0.0
    for beat in beats["beats"]:
        n = len(beat["text"].split())
        start = max(prev_end, times[i][0] - 0.12)
        prev_end = times[i + n - 1][1]
        timings.append({"start": round(start, 3), "end": round(prev_end, 3)})
        i += n
    (folder / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"timings.json: {len(timings)} beats from word timings")
print(f"captions.json: {len(captions)} words ({missed} interpolated)")
