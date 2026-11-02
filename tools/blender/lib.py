"""Helpers for scene scripts (they run inside Blender; see harness.py).

A scene script defines build(scene) and uses these to place Poly Haven models,
light the world and move the camera across scene.frame_start..frame_end:

    import lib
    def build(scene):
        lamp = lib.model("vintage_oil_lamp", location=(0, 0, 0.8))
        lib.hdri("studio_small_09", strength=0.2)
        cam, target = lib.camera(lens=50, fstop=2.0)
        lib.key(cam, scene.frame_start, location=(0, -2, 1.2))
        lib.key(cam, scene.frame_end, location=(0.3, -1.2, 1.1))

Keyframes ease in and out by default (Bezier), so two keys make a smooth move.
"""
from pathlib import Path

import bpy

ASSETS = Path(__file__).parent.parent / "blender-assets"


def reset():
    """Empty the factory scene but keep its world."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def model(asset_id, res="2k", location=(0, 0, 0), rotation_z=0.0, scale=1.0):
    """Append a downloaded Poly Haven model; returns an empty that carries all its parts."""
    path = ASSETS / asset_id / f"{asset_id}_{res}.blend"
    if not path.exists():
        raise SystemExit(f"{path} missing: run tools/polyhaven.py get {asset_id}")
    images_before = set(bpy.data.images)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    # Textures sit next to the .blend; point relative paths there.
    for img in set(bpy.data.images) - images_before:
        if img.filepath.startswith("//"):
            img.filepath = str(path.parent / img.filepath[2:])
    root = bpy.data.objects.new(asset_id, None)
    bpy.context.scene.collection.objects.link(root)
    for ob in dst.objects:
        # Poly Haven files also carry a 2 m preview sphere ("Sphere_stash_0").
        if ob is None or ob.type in ("CAMERA", "LIGHT") or "stash" in ob.name:
            continue
        bpy.context.scene.collection.objects.link(ob)
        if ob.parent is None:
            ob.parent = root
    root.location, root.rotation_euler.z, root.scale = location, rotation_z, (scale,) * 3
    return root


def hdri(asset_id, res="2k", strength=1.0, rotation_z=0.0):
    """Light the scene (and fill the background) with a downloaded Poly Haven HDRI."""
    path = ASSETS / asset_id / f"{asset_id}_{res}.hdr"
    if not path.exists():
        raise SystemExit(f"{path} missing: run tools/polyhaven.py get {asset_id}")
    nodes, links = _world_nodes()
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(path))
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = rotation_z
    coords = nodes.new("ShaderNodeTexCoord")
    links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], nodes["Background"].inputs["Color"])
    nodes["Background"].inputs["Strength"].default_value = strength


def world_color(rgb, strength=1.0):
    """Plain background colour instead of an HDRI (dark rooms, studio voids)."""
    nodes, _ = _world_nodes()
    nodes["Background"].inputs["Color"].default_value = (*rgb, 1)
    nodes["Background"].inputs["Strength"].default_value = strength


def haze(density=0.02, size=30):
    """Fill the air with thin fog so lights throw visible beams."""
    bpy.ops.mesh.primitive_cube_add(size=size)
    box = bpy.context.object
    box.name = "Haze"
    mat = bpy.data.materials.new("Haze")
    nodes = mat.node_tree.nodes
    nodes.remove(nodes["Principled BSDF"])
    vol = nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = density
    mat.node_tree.links.new(vol.outputs["Volume"], nodes["Material Output"].inputs["Volume"])
    box.data.materials.append(mat)
    return box


def camera(lens=35, fstop=None):
    """Active camera that always looks at a target empty; move either to frame the shot."""
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    target = bpy.data.objects.new("CameraTarget", None)
    for ob in (cam, target):
        scene.collection.objects.link(ob)
    scene.camera = cam
    cam.data.lens = lens
    track = cam.constraints.new("TRACK_TO")
    track.target, track.track_axis, track.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    if fstop:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = fstop
        cam.data.dof.focus_object = target
    return cam, target


def light(kind, location, energy, color=(1, 1, 1), size=0.1):
    """Add a POINT, AREA or SPOT light."""
    data = bpy.data.lights.new(kind.title(), kind)
    data.energy, data.color = energy, color
    if kind == "AREA":
        data.size = size
    else:
        data.shadow_soft_size = size
    ob = bpy.data.objects.new(data.name, data)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    return ob


def flicker(light_ob, amount=0.15):
    """Make a light waver like a flame (a driver, so it needs no keyframes)."""
    base = light_ob.data.energy
    driver = light_ob.data.driver_add("energy").driver
    # Simple expressions run without Python, so this works with scripts auto-run off.
    driver.expression = f"{base} * (1 + {amount} * (0.6 * sin(frame * 0.9) + 0.4 * sin(frame * 2.3 + 1)))"


def key(ob, frame, **props):
    """Keyframe properties at a frame, e.g. key(cam, 1, location=(0, -2, 1))."""
    for name, value in props.items():
        setattr(ob, name, value)
        ob.keyframe_insert(name, frame=frame)


def _world_nodes():
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    tree = scene.world.node_tree
    tree.nodes.clear()
    bg = tree.nodes.new("ShaderNodeBackground")
    bg.name = "Background"
    out = tree.nodes.new("ShaderNodeOutputWorld")
    tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return tree.nodes, tree.links
