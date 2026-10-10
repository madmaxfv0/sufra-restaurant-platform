"""Render a prepped GLB so the decimation can be judged, not assumed.

The Poly Haven trees model every leaf as real geometry - island_tree_01 is
1.6 M triangles - so a heavy decimate can quietly turn a crown into confetti.
This renders the exported GLB on a plain backdrop with Cycles on CPU, which is
the only renderer that works reliably with no GPU and no display.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/preview_asset.py -- static/3d/models/trees/island_tree_01.glb

Writes captures/assets/<name>.png.
"""
import math
import pathlib
import sys

import bpy
import mathutils

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "assets"


def bounds():
    lo = mathutils.Vector((1e9, 1e9, 1e9))
    hi = mathutils.Vector((-1e9, -1e9, -1e9))
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector((min(lo[i], w[i]) for i in range(3)))
            hi = mathutils.Vector((max(hi[i], w[i]) for i in range(3)))
    return lo, hi


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print("usage: preview_asset.py -- <glb> [<glb> ...]", file=sys.stderr)
        return
    OUT.mkdir(parents=True, exist_ok=True)

    for rel in argv:
        path = (ROOT / rel).resolve()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(path))

        lo, hi = bounds()
        centre = (lo + hi) / 2
        extent = max(hi[i] - lo[i] for i in range(3)) or 1.0

        # ground plane, so a floating or sunken asset is obvious
        bpy.ops.mesh.primitive_plane_add(size=extent * 8, location=(centre.x, centre.y, lo.z))

        cam_data = bpy.data.cameras.new("cam")
        cam = bpy.data.objects.new("cam", cam_data)
        bpy.context.scene.collection.objects.link(cam)
        d = extent * 2.4
        cam.location = (centre.x + d * 0.72, centre.y - d * 0.72, centre.z + d * 0.42)
        direction = centre - mathutils.Vector(cam.location)
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = cam

        sun_data = bpy.data.lights.new("sun", type="SUN")
        sun_data.energy = 4.0
        sun = bpy.data.objects.new("sun", sun_data)
        sun.rotation_euler = (math.radians(52), 0, math.radians(38))
        bpy.context.scene.collection.objects.link(sun)

        world = bpy.data.worlds.new("w")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.58, 0.75, 1)
        bpy.context.scene.world = world

        sc = bpy.context.scene
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = 24
        sc.cycles.use_denoising = True
        sc.render.resolution_x = 700
        sc.render.resolution_y = 700
        sc.render.filepath = str(OUT / f"{path.stem}.png")
        bpy.ops.render.render(write_still=True)
        print("wrote", sc.render.filepath, f"(extent {extent:.2f} m)")


if __name__ == "__main__":
    main()
