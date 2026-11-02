"""Two-pass loudness normalisation to -14 LUFS, copying the video stream.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/loudnorm.py in.mp4 out.mp4

One-pass loudnorm undershoots on speech with pauses (sermon clips landed at
-15 to -17 LUFS); measuring first and applying linearly hits the target.
"""
import json
import re
import subprocess
import sys

TARGET = "I=-14:TP=-1.5:LRA=11"
src, dst = sys.argv[1], sys.argv[2]

log = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", src, "-af", f"loudnorm={TARGET}:print_format=json",
                      "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
m = json.loads(re.findall(r"\{[^{}]*\}", log)[-1])
apply = (f"loudnorm={TARGET}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
         f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", apply, "-ar", "48000",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", dst], check=True)
print(f"{dst}: {m['input_i']} -> -14 LUFS")
