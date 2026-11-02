"""Voice a short or long video with Qwen3-TTS (local GPU).

Usage: tools/.venv-tts/Scripts/python.exe -I -X utf8 tools/tts_qwen.py shorts/<slug>

beats.json picks the voice:
- "voice_clone": "<name>" clones tools/voices/<name>.wav (transcript in
  <name>.txt) with the Base model, so every video gets the same narrator. Use
  this for a series. Scripts are voiced in chunks of whole beats and joined,
  which keeps long videos stable and only works because the voice is fixed.
- otherwise "voice_design" (a plain-English description, plus "seed") designs a
  voice with the VoiceDesign model, in one pass; it changes between runs.
"language" defaults to English (Korean also works). Writes voice.wav; captions.py
then derives the beat timings from the words. About 3 s of compute per 1 s of
audio on an RTX 4060.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

VOICES = Path(__file__).parent / "voices"
CHUNK_CHARS = 700  # per clone call; long single calls drift
PAUSE_S = 0.35  # silence between chunks
DEFAULT_VOICE = (
    "A bright, curious young female narrator with a friendly conversational tone, as if "
    "explaining a fascinating idea to a close friend over coffee. Expressive, playful "
    "emphasis on key words, natural rhythm and pauses."
)


def load(name):
    return Qwen3TTSModel.from_pretrained(f"Qwen/Qwen3-TTS-12Hz-1.7B-{name}", device_map="cuda:0",
                                         dtype=torch.bfloat16, attn_implementation="sdpa")


folder = Path(sys.argv[1])
beats = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
language = beats.get("language", "English")
# "say" respells words the model mispronounces; *asterisks* only mark caption emphasis.
lines = [b.get("say", b["text"]).replace("*", "") for b in beats["beats"]]
torch.manual_seed(beats.get("seed", 7))

if clone := beats.get("voice_clone"):
    model = load("Base")
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(VOICES / f"{clone}.wav"),
        ref_text=(VOICES / f"{clone}.txt").read_text(encoding="utf-8").strip())
    chunks = [""]
    for line in lines:
        if chunks[-1] and len(chunks[-1]) + len(line) > CHUNK_CHARS:
            chunks.append(line)
        else:
            chunks[-1] = f"{chunks[-1]} {line}".strip()
    parts = []
    for i, chunk in enumerate(chunks, 1):
        wavs, sr = model.generate_voice_clone(text=chunk, language=language, voice_clone_prompt=prompt)
        parts += [wavs[0], np.zeros(int(PAUSE_S * sr), dtype=wavs[0].dtype)]
        print(f"chunk {i}/{len(chunks)}: {len(wavs[0]) / sr:.1f}s", flush=True)
    audio = np.concatenate(parts[:-1])
else:
    model = load("VoiceDesign")
    wavs, sr = model.generate_voice_design(text=" ".join(lines), language=language,
                                           instruct=beats.get("voice_design", DEFAULT_VOICE))
    audio = wavs[0]

sf.write(folder / "voice.wav", audio, sr)
(folder / "timings.json").unlink(missing_ok=True)  # stale timings; captions.py rebuilds them
print(f"voice.wav: {len(audio) / sr:.1f}s")
