"""Build, render and loudness-normalise every clip of a sermon, or the ones named.

Usage: tools/.venv/Scripts/python.exe -I -X utf8 tools/render_clips.py sermons/<slug> [clip-id ...]

Per clip: build_clip.py (props.json), remotion render (raw.mp4), loudnorm.py
(clip.mp4). A clip that fails is skipped and the rest still render; the
summary names each failed clip and step, so no clip is silently left out.
Rerun with just the failed ids after fixing them.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).parent
folder = Path(sys.argv[1]).resolve()
config = json.loads((folder / "clips.json").read_text(encoding="utf-8"))
ids = sys.argv[2:] or [c["id"] for c in config["clips"]]
unknown = sorted(set(ids) - {c["id"] for c in config["clips"]})
if unknown:
    sys.exit(f"not in clips.json: {', '.join(unknown)}")
npx = shutil.which("npx") or sys.exit("npx not found: install Node.js")
py = [sys.executable, "-I", "-X", "utf8"]

failed = []
for n, clip_id in enumerate(ids, 1):
    out = folder / "clips" / clip_id
    steps = [
        ("build", py + [str(TOOLS / "build_clip.py"), str(folder), clip_id]),
        ("render", [npx, "remotion", "render", "SermonClip", str(out / "raw.mp4"), f"--props={out / 'props.json'}",
                    f"--public-dir={out}", "--timeout=90000", "--log=error"]),
        ("loudnorm", py + [str(TOOLS / "loudnorm.py"), str(out / "raw.mp4"), str(out / "clip.mp4")]),
    ]
    print(f"[{n}/{len(ids)}] {clip_id}", flush=True)
    began = time.time()
    for step, cmd in steps:
        if subprocess.run(cmd, cwd=TOOLS.parent).returncode:
            failed.append(f"{clip_id} ({step})")
            print(f"   {step} failed", flush=True)
            break
    else:
        print(f"   {out / 'clip.mp4'} in {time.time() - began:.0f} s", flush=True)

print(f"{len(ids) - len(failed)}/{len(ids)} clips rendered")
if failed:
    sys.exit("failed: " + ", ".join(failed))
