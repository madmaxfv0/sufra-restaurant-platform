"""Pull the usable furniture out of the ProVis restaurant FBX.

The source is a 1.25 GB archviz scene: 36.5 M triangles across 567 meshes,
built for stills, not for a browser. Almost all of it is scenery we already
have (ceiling alone is 13.4 M triangles). What it does carry, at correct
real-world scale, is a proper dining chair, a bar counter, a dining table and
real plants - which is what SUFRA 360 has been missing.

Each piece is isolated, decimated to a browser budget, its textures shrunk
and packed, and written as a Draco GLB.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/extract_provis.py
"""
import pathlib
import re

import bpy

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets_src" / "provis" / "FBX.fbx"
OUT = ROOT / "static" / "3d" / "models" / "provis"

# output name -> (regex matching source object names, triangle budget, texture px)
WANT = {
    "chair":       (r"^crp_Chair$",                    9000, 1024),
    "bar_counter": (r"^Bar_301$",                     14000, 1024),
    "bar_back":    (r"^Bar_10$",                       8000, 1024),
    "table":       (r"^Dining_table_Holiday",          7000, 1024),
    "palm":        (r"^palm_04$",                      7000,  512),
    "plant":       (r"^Hanging_plants___indoor_plant00$", 5000, 512),
}


def only(pattern):
    """Delete everything whose name does not match, leaving one piece."""
    rx = re.compile(pattern)
    for o in list(bpy.data.objects):
        if o.type != "MESH" or not rx.search(o.name):
            bpy.data.objects.remove(o, do_unlink=True)


def tri_count():
    n = 0
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data:
            o.data.calc_loop_triangles()
            n += len(o.data.loop_triangles)
    return n


def decimate(budget):
    before = tri_count()
    if before <= budget or not before:
        return before, before
    ratio = budget / before
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        if len(o.data.polygons) < 8:
            continue
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("dec", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = ratio
        m.use_symmetry = False
        bpy.ops.object.modifier_apply(modifier=m.name)
    return before, tri_count()


def shrink_textures(size):
    """Same trap as the Poly Haven pipeline: an image must be packed after
    scaling or the exporter re-reads the original off disk."""
    for img in bpy.data.images:
        try:
            if img.size[0] == 0:
                img.reload()
            w, h = img.size
            if not w or max(w, h) <= size:
                continue
            k = size / max(w, h)
            img.scale(max(1, int(w * k)), max(1, int(h * k)))
            img.pack()
        except Exception:
            pass


def drop_to_floor():
    """Sit the piece on z=0 so the runtime can place it by its feet."""
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    if not objs:
        return
    zs = [(o.matrix_world @ c.to_4d().to_3d()).z if False else
          (o.matrix_world @ __import__("mathutils").Vector(c)).z
          for o in objs for c in o.bound_box]
    lo = min(zs)
    for o in objs:
        if not o.parent:
            o.location.z -= lo


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (pattern, budget, tex) in WANT.items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(SRC), use_custom_normals=False,
                                 ignore_leaf_bones=True)
        only(pattern)
        if not any(o.type == "MESH" for o in bpy.data.objects):
            print(f"!! {name}: nothing matched {pattern}", flush=True)
            continue
        shrink_textures(tex)
        before, after = decimate(budget)
        drop_to_floor()
        path = OUT / f"{name}.glb"
        bpy.ops.export_scene.gltf(
            filepath=str(path), export_format="GLB",
            export_draco_mesh_compression_enable=True,
            export_draco_mesh_compression_level=6,
            export_apply=True, export_yup=True,
            export_cameras=False, export_lights=False)
        print(f"{name:14} {before:>9,} -> {after:>7,} tris   "
              f"{path.stat().st_size/1e6:5.2f} MB", flush=True)


if __name__ == "__main__":
    main()
