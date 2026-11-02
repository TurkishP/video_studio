"""Turn paintings into slow 3D camera moves with DepthFlow (local, uses the GPU).

Usage: tools/.venv-depthflow/Scripts/python.exe -I -X utf8 tools/parallax.py shorts/<slug>

Run after tts.py. Every beat whose visual has "parallax": true gets
assets/parallax-NN.mp4, exactly as long as that beat's scene; build_props.py
then uses it instead of the still. Clips are 1080x1920, or 1920x1080 when
beats.json has "format": "long". Optional "focus": [x, y] (about -0.5..0.5)
shifts the vertical crop toward the subject. -X utf8 matters: DepthFlow reads
its shaders with the system encoding, which is cp949 on Korean Windows.

Each clip renders in its own process: DepthFlow 1.0.1 fails to recompile its
shader when one scene renders a second image, and it leaves a non-daemon
thread running afterwards, so every child ends with os._exit.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

FPS = 30
TAIL_S = 0.8  # same hold as build_props.py
FADE_S = 0.3  # covers the crossfade into the next scene


def render_one(image, output, seconds, style, fx, fy, width, height):
    from attrs import define
    from depthflow.scene import DepthScene

    @define
    class Move(DepthScene):
        def update(self):
            t = 0.5 - 0.5 * math.cos(math.pi * self.tau)  # ease in and out
            s = self.state
            s.height, s.steady, s.isometric = 0.25, 0.3, 0.6
            s.center = (fx, fy)
            if style == 0:  # push in
                s.zoom = 1.0 - 0.12 * t
            elif style == 1:  # drift sideways
                s.zoom, s.offset = 0.92, (-0.3 + 0.6 * t, 0.0)
            else:  # rise
                s.zoom, s.offset = 0.92, (0.0, -0.25 + 0.5 * t)

    scene = Move(backend="headless")
    scene.ffmpeg.h264(preset="veryfast")
    scene.input(image=image)
    scene.main(output=output, width=width, height=height, fps=FPS, time=seconds, ssaa=1.5)


if sys.argv[1] == "--one":
    try:
        image, output, seconds, style, fx, fy, width, height = sys.argv[2:]
        render_one(image, output, float(seconds), int(style), float(fx), float(fy), int(width), int(height))
    except Exception as e:
        print(e, flush=True)
        os._exit(1)
    os._exit(0)

folder = Path(sys.argv[1])
config = json.loads((folder / "beats.json").read_text(encoding="utf-8"))
beats = config["beats"]
size = ("1920", "1080") if config.get("format") == "long" else ("1080", "1920")
timings = json.loads((folder / "timings.json").read_text(encoding="utf-8"))

made = 0
for i, (beat, t) in enumerate(zip(beats, timings)):
    visual = beat["visual"]
    if not visual.get("parallax"):
        continue
    end = timings[i + 1]["start"] if i + 1 < len(timings) else t["end"] + TAIL_S
    fx, fy = visual.get("focus", (0.0, 0.0))
    output = folder / "assets" / f"parallax-{i:02d}.mp4"
    image = folder / visual["src"]
    # DepthFlow fits the image height and smears the edges when the image is
    # narrower than the frame (a tall painting in 16:9), so crop it to the frame
    # shape first, centred on the subject: the first close-up's focus.
    iw, ih = map(int, subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(image)], capture_output=True, text=True, check=True).stdout.split(",")[:2])
    if iw / ih < int(size[0]) / int(size[1]) - 0.01:
        ch = round(iw * int(size[1]) / int(size[0]))
        subject_y = next((s["focus"][1] for s in visual.get("shots", []) if s.get("focus")), 0.42)
        y0 = min(max(0, round(subject_y * ih - ch / 2)), ih - ch)
        cropped = folder / "assets" / f"parallax-{i:02d}-src.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(image), "-vf", f"crop={iw}:{ch}:0:{y0}",
                        "-q:v", "2", str(cropped)], check=True)
        image = cropped
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", __file__, "--one", str(image), str(output),
         str(end - t["start"] + FADE_S), str(made % 3), str(fx), str(fy), *size],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    if result.returncode != 0 or not output.exists():
        sys.exit(f"beat {i}: parallax render failed\n{result.stdout[-2000:]}{result.stderr[-2000:]}")
    print(f"parallax-{i:02d}.mp4 ({end - t['start'] + FADE_S:.1f}s)", flush=True)
    made += 1

print(f"parallax: {made} clips")
