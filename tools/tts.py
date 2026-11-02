"""Voice a short with Kokoro (local, free).

Usage: tools/.venv/Scripts/python.exe -I tools/tts.py shorts/<slug>

Reads beats.json, writes voice.wav and timings.json (start/end seconds per beat).
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODELS = Path(__file__).parent / "models"
PAUSE_S = 0.25  # silence between beats

folder = Path(sys.argv[1])
beats = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
voice = beats.get("voice", "af_heart")
speed = beats.get("speed", 1.0)

kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))

chunks, timings, t = [], [], 0.0
for beat in beats["beats"]:
    # "say" is an optional respelling for words Kokoro mispronounces; captions keep "text".
    # *asterisks* only mark caption emphasis.
    spoken = beat.get("say", beat["text"]).replace("*", "")
    samples, sr = kokoro.create(spoken, voice=voice, speed=speed, lang="en-us")
    dur = len(samples) / sr
    timings.append({"start": round(t, 3), "end": round(t + dur, 3)})
    chunks += [samples, np.zeros(int(PAUSE_S * sr), dtype=samples.dtype)]
    t += dur + PAUSE_S

sf.write(folder / "voice.wav", np.concatenate(chunks[:-1]), sr)
(folder / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
print(f"voice.wav: {timings[-1]['end']:.1f}s, {len(timings)} beats")
