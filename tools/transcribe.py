"""Transcribe a long talk (a sermon) with word timings, for cutting clips.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/transcribe.py sermons/<slug> [language] ["hot words"]

Reads the folder's audio.* and writes words.json (segments with every word's
start/end in seconds) and transcript.txt (one timestamped line per segment, to
read when picking clips). Hot words are names and terms to spell right, e.g.
"고상섭 그사랑교회 팀 켈러". Runs large-v3-turbo on the GPU with the CUDA
libraries from tools/.venv-tts's torch (~3 min per hour of audio); falls back
to the CPU, which is several times slower.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).parent
TORCH_LIB = TOOLS / ".venv-tts" / "Lib" / "site-packages" / "torch" / "lib"
if TORCH_LIB.exists():  # cuBLAS 12 + cuDNN 9, which CTranslate2 loads by name
    os.environ["PATH"] = f"{TORCH_LIB}{os.pathsep}{os.environ['PATH']}"
    os.add_dll_directory(str(TORCH_LIB))
from faster_whisper import WhisperModel  # noqa: E402

folder = Path(sys.argv[1])
language = sys.argv[2] if len(sys.argv) > 2 else "ko"
hotwords = sys.argv[3] if len(sys.argv) > 3 else None

# YouTube's HLS audio carries timestamps that run ~0.09% ahead of its samples
# (2.7 s by minute 50), so seeking it with -ss lands early. A WAV's timeline is
# its samples, which match the video; transcribe.py and build_clip.py both use it.
audio = folder / "audio.wav"
if not audio.exists():
    source = next(p for p in folder.glob("audio.*") if p.suffix not in (".part", ".ytdl", ".wav"))
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-c:a", "pcm_s16le", str(audio)], check=True)

# Decode with FFmpeg: faster-whisper's own decoder breaks on PyAV 19.
raw = subprocess.run(["ffmpeg", "-nostdin", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                     capture_output=True, check=True).stdout
samples = np.frombuffer(raw, np.float32)

try:
    model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16",
                         download_root=str(TOOLS / "models" / "whisper"))
    device = "cuda"
except Exception as e:
    print(f"GPU unavailable ({e}); using the CPU")
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8",
                         download_root=str(TOOLS / "models" / "whisper"))
    device = "cpu"

segments, info = model.transcribe(samples, language=language, word_timestamps=True, vad_filter=True,
                                  condition_on_previous_text=False, hotwords=hotwords)
out, lines = [], []
for s in segments:
    words = [[w.word.strip(), round(w.start, 2), round(w.end, 2)] for w in s.words if w.word.strip()]
    if not words:
        continue
    out.append({"start": words[0][1], "end": words[-1][2], "text": s.text.strip(), "words": words})
    t = int(words[0][1])
    lines.append(f"{t // 60}:{t % 60:02d} {s.text.strip()}")
    if len(out) % 100 == 0:
        print(f"{t // 60} min transcribed", flush=True)

(folder / "words.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
(folder / "transcript.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{device}: {len(out)} segments, {sum(len(s['words']) for s in out)} words, "
      f"{info.duration / 60:.0f} min of audio")
