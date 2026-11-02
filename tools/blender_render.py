"""Render Blender scene scripts into video clips (local, uses the GPU).

Usage:
  python -I tools/blender_render.py shorts/<slug>
  python -I tools/blender_render.py <scene.py> <out.mp4|out.png> --seconds 6 [--format long] [--engine cycles] [--still 90]

The first form renders every beat whose visual is {"type": "blender", "scene":
"scenes/x.py"} to assets/blender-NN.mp4, exactly as long as that beat's scene
(run it after captions.py, like parallax.py); build_props.py then plays the clip.
Optional "engine": "cycles" on the visual trades speed for realistic light.
The second form renders one scene on its own; --still renders a single frame
to a PNG, for checking a shot in seconds. Clips are 1080x1920, or 1920x1080
for "format": "long". Scene scripts are documented in tools/blender/lib.py.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).parent
BLENDER = TOOLS / "blender-5.2" / "blender.exe"
HARNESS = TOOLS / "blender" / "harness.py"
FPS = 30
TAIL_S = 0.8  # same hold as build_props.py
FADE_S = 0.3  # covers the crossfade into the next scene
SIZES = {"short": (1080, 1920), "long": (1920, 1080)}


def render(scene, out, seconds, size, engine="eevee", still=None):
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [str(BLENDER), "-b", "--factory-startup", "--python-exit-code", "1", "-P", str(HARNESS), "--",
             str(scene), tmp, str(seconds), str(size[0]), str(size[1]), engine, *([str(still)] if still else [])],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            sys.exit(f"{scene}: Blender failed\n{(result.stdout + result.stderr)[-3000:]}")
        out.parent.mkdir(parents=True, exist_ok=True)
        if still:
            shutil.copy(Path(tmp) / "still.png", out)
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(Path(tmp) / "f_%04d.png"),
                            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", str(out)],
                           check=True)
    print(f"{out} ({seconds:.1f}s, rendered in {time.time() - started:.0f}s)", flush=True)


p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("out", nargs="?")
p.add_argument("--seconds", type=float, default=6)
p.add_argument("--format", choices=SIZES, default="short")
p.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
p.add_argument("--still", type=int)
args = p.parse_args()

if args.out:
    render(Path(args.target), Path(args.out), args.seconds, SIZES[args.format], args.engine, args.still)
    sys.exit()

folder = Path(args.target)
config = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
timings = json.loads((folder / "timings.json").read_text(encoding="utf-8"))
made = 0
for i, (beat, t) in enumerate(zip(config["beats"], timings)):
    visual = beat["visual"]
    if visual["type"] != "blender":
        continue
    end = timings[i + 1]["start"] if i + 1 < len(timings) else t["end"] + TAIL_S
    render(folder / visual["scene"], folder / "assets" / f"blender-{i:02d}.mp4", end - t["start"] + FADE_S,
           SIZES[config.get("format", "short")], visual.get("engine", "eevee"))
    made += 1
print(f"blender: {made} clips")
