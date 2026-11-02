"""Runs inside Blender: set up the render, build a scene script's scene, render PNG frames.

Called by tools/blender_render.py, not by hand:
  blender -b --factory-startup -P tools/blender/harness.py -- <scene.py> <out_dir> <seconds> <width> <height> <engine> [still_frame]
"""
import importlib.util
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))  # lets scene scripts `import lib`
import lib

FPS = 30

scene_path, out_dir, seconds, width, height, engine, *still = sys.argv[sys.argv.index("--") + 1:]
s = bpy.context.scene
lib.reset()
s.render.fps = FPS
s.frame_start, s.frame_end = 1, max(1, round(float(seconds) * FPS))
s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage = int(width), int(height), 100
s.render.use_motion_blur = True
if engine == "cycles":
    # OptiX needs a newer NVIDIA driver than 555; CUDA works on the RTX 4060.
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "CUDA"
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == "CUDA"
    s.render.engine = "CYCLES"
    s.cycles.device = "GPU"
    s.cycles.samples = 128
    s.cycles.use_denoising = True
else:
    s.render.engine = "BLENDER_EEVEE"
    s.eevee.taa_render_samples = 64
    s.eevee.use_raytracing = True

spec = importlib.util.spec_from_file_location("scene_script", scene_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.build(s)

s.render.image_settings.file_format = "PNG"
if still:
    s.frame_set(int(still[0]))
    s.render.filepath = str(Path(out_dir) / "still.png")
    bpy.ops.render.render(write_still=True)
else:
    s.render.filepath = str(Path(out_dir) / "f_")
    bpy.ops.render.render(animation=True)
