"""Import every shipped GLB into one .blend, organised by collection, so it
can be opened and hand-edited in the Blender GUI.

Each asset is imported at the origin, offset along a grid so nothing overlaps,
and placed in a collection matching its static/3d/models/ subfolder (which
also matches the venue's Blender collection names: TREES, PLANTS, PROPS,
PEOPLE). LOD variants get their own collection so they are not mixed in with
the full-detail models on the same grid.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/build_master_blend.py

Writes blender/sufra_assets_master.blend.
"""
import pathlib

import bpy

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "static" / "3d" / "models"
OUT = ROOT / "blender" / "sufra_assets_master.blend"

# folder name -> (Blender collection name, grid spacing in metres)
FOLDERS = {
    "trees": ("TREES", 10),
    "plants": ("PLANTS", 3),
    "props": ("PROPS", 3),
    "humans": ("PEOPLE", 2),
}


def collection(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    for folder, (coll_name, spacing) in FOLDERS.items():
        d = MODELS / folder
        if not d.exists():
            continue
        full = collection(coll_name)
        lod = collection(coll_name + "_LOD") if any(f.stem.endswith("_lod") for f in d.glob("*.glb")) else None

        files = sorted(d.glob("*.glb"))
        gi = 0
        for f in files:
            is_lod = f.stem.endswith("_lod")
            before = set(bpy.context.scene.objects)
            bpy.ops.import_scene.gltf(filepath=str(f))
            new_objs = [o for o in bpy.context.scene.objects if o not in before]
            if not new_objs:
                continue

            target = lod if is_lod else full
            for o in new_objs:
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                target.objects.link(o)

            # only move the root objects (no parent among the new set), so
            # children keep their relative transform
            roots = [o for o in new_objs if o.parent not in new_objs]
            gx = (gi % 6) * spacing
            gz = (gi // 6) * spacing
            for o in roots:
                o.location.x += gx
                o.location.y += gz
                o.name = f.stem
            gi += 1
            print(f"  {f.relative_to(ROOT)}  ->  {target.name}  at ({gx}, {gz})")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
