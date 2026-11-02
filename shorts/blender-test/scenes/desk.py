"""A writer's desk at night: oil lamp, leather books, candlestick; the camera drifts in to the flame."""
import bpy
from mathutils import Vector

import lib

TOP = 1.004  # table height (m)


def bounds_center(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return sum(pts, Vector()) / len(pts)


def build(scene):
    lib.model("round_wooden_table_01")
    lamp = lib.model("vintage_oil_lamp", location=(0.12, 0.12, TOP), rotation_z=0.4)
    lib.model("book_encyclopedia_set_01", location=(-0.66, 0.22, TOP), rotation_z=0.5)  # spines to camera
    lib.model("wooden_candlestick", location=(-0.3, -0.12, TOP))

    floor = bpy.data.objects.new("Floor", bpy.data.meshes.new("Floor"))
    floor.data.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    scene.collection.objects.link(floor)

    # The room is lit only by the flame; the HDRI adds faint warm reflections.
    lib.hdri("fireplace", strength=0.04, rotation_z=2.2)
    bpy.context.view_layer.update()
    flame = next(ob for ob in lamp.children_recursive if ob.name.endswith("_flame"))
    glow = lib.light("POINT", bounds_center(flame), energy=40, color=(1.0, 0.62, 0.32), size=0.02)
    lib.flicker(glow, 0.12)
    lib.light("AREA", (-1.6, 1.8, 2.2), energy=60, color=(0.55, 0.65, 1.0), size=1.5)  # cool moonlight rim
    lib.haze(density=0.006)
    scene.eevee.volumetric_tile_size = "4"  # finer fog, no blotchy halo round the flame

    cam, target = lib.camera(lens=50, fstop=1.8)
    f0, f1 = scene.frame_start, scene.frame_end
    focus = bounds_center(flame)
    lib.key(cam, f0, location=(1.15, -1.55, 1.42))
    lib.key(cam, f1, location=(0.42, -0.62, 1.30))
    lib.key(target, f0, location=focus + Vector((-0.25, 0.1, -0.1)))
    lib.key(target, f1, location=focus + Vector((0, 0, -0.04)))

    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
