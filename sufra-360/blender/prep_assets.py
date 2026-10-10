"""Turn Poly Haven source glTF into GLBs the browser can actually load.

Poly Haven models are built for offline rendering: island_tree_01 alone is
60 MB of geometry, tree_small_02 is 95 MB. Served raw they would cost more
than the rest of the venue put together. This decimates each asset to a
triangle budget, keeps the foliage material separate from the bark so the
runtime wind shader can still find it, and writes a Draco-compressed GLB.

Run through Blender, never as plain python:

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/prep_assets.py -- --only island_tree_01

Reads from assets_src/polyhaven/<id>/, writes to static/3d/models/<category>/.
"""
import argparse
import json
import pathlib
import re
import sys

import bpy
import mathutils

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets_src" / "polyhaven"
OUT = ROOT / "static" / "3d" / "models"

# id -> (category, target triangles, height in metres, texture size)
# Trees carry their leaves as real geometry rather than alpha cards, so the
# triangle budget is what decides whether a crown reads as foliage or as
# confetti - 26 k left island_tree_01 visibly bald. Textures go the other way:
# a tree is seen from 10 m plus, so 512 is plenty, while a terrace chair is
# seen from arm's length and keeps 1 k.
#   height  metres to scale to, or None to trust Poly Haven's real-world scale
#   keep    only these objects survive (regex on object name)
#   parts   write several GLBs from one source, {output name: regex}
#   loose   split the mesh into loose parts and keep only the biggest
#   lod     also write <name>_lod.glb at this budget, for distant scatter
SPEC = {
    # ---- interior fit-out. Real-world heights: dining chair seat 0.45 with a
    # back to ~0.90, dining table top 0.75, bar stool seat 0.75, counter 1.05.
    # These are what replace the primitive boxes in the dining room, so the
    # texture budget is higher than the far-field props: they are seen close.
    "dining_chair_02":       dict(category="furniture", tris=6000, height=0.92, tex=1024),
    "GreenChair_01":         dict(category="furniture", tris=6000, height=0.90, tex=1024),
    "WoodenChair_01":        dict(category="furniture", tris=5000, height=0.90, tex=1024),
    "ArmChair_01":           dict(category="furniture", tris=7000, height=0.82, tex=1024),
    "Sofa_01":               dict(category="furniture", tris=8000, height=0.84, tex=1024),
    "dining_table":          dict(category="furniture", tris=5000, height=0.75, tex=1024),
    "WoodenTable_02":        dict(category="furniture", tris=4000, height=0.75, tex=1024),
    "coffee_table_round_01": dict(category="furniture", tris=4000, height=0.75, tex=1024),
    "bar_chair_round_01":    dict(category="furniture", tris=5000, height=0.78, tex=1024),
    "metal_stool_02":        dict(category="furniture", tris=4000, height=0.76, tex=512),
    "Shelf_01":              dict(category="furniture", tris=4000, height=1.80, tex=512),
    "modern_wooden_cabinet": dict(category="furniture", tris=5000, height=0.85, tex=512),
    "ceramic_vase_02":       dict(category="tableware", tris=2500, height=0.22, tex=512),
    "brass_vase_01":         dict(category="tableware", tris=2500, height=0.26, tex=512),
    "ceramic_pot":           dict(category="plants",    tris=2500, height=0.34, tex=512),
    "food_pomegranate_01":   dict(category="tableware", tris=1800, height=0.09, tex=512),
    "food_apple_01":         dict(category="tableware", tris=1500, height=0.08, tex=512),
    "desk_lamp_arm_01":      dict(category="lamps",     tris=3500, height=0.42, tex=512),
    "industrial_wall_lamp":  dict(category="lamps",     tris=3000, height=0.30, tex=512),
    "modern_ceiling_lamp_01":dict(category="lamps",     tris=3000, height=0.35, tex=512),

    # The lod pass feeds the parkland scatter filling the ground between the
    # plot and the city. The scatter is ~350 trees, so the budget that matters
    # is the total: 2.5 k each is under a million triangles for the whole park.
    # 700 was the first try and rendered a bald armature - what survives a
    # collapse to 700 is the branch skeleton, not the crown that reads as a
    # tree at distance.
    "island_tree_01": dict(category="trees", tris=60000, height=7.5, tex=512, lod=2500),
    "island_tree_02": dict(category="trees", tris=52000, height=6.2, tex=512, lod=2500),
    "tree_small_02":  dict(category="trees", tris=52000, height=5.4, tex=512, lod=2000),
    # one mesh holding a row of separate plants: normalising the row's total
    # height shrank every plant to a sprig, so take the largest part alone
    "shrub_01":       dict(category="plants", tris=10000, height=0.9, tex=512, loose=True),
    "shrub_03":       dict(category="plants", tris=4000, height=0.5, tex=512,
                           keep=r"shrub_03_a$"),
    "street_lamp_01": dict(category="props", tris=6000, height=4.2, tex=512),
    # a table-and-two-chairs set; the venue places tables and chairs
    # independently against real table ids, so it has to come apart
    "outdoor_table_chair_set_01": dict(
        category="props", tris=8000, height=None, tex=1024,
        parts={"terrace_table": r"_table$", "terrace_chair": r"_chair_01$"}),
    # a modular kit: the assembled bench plus loose spare connectors
    "modular_street_seating": dict(
        category="props", tris=5000, height=None, tex=512,
        keep=r"^(seat|seat_back|legs_double|back_support_[rl]|arm_rest_01|crossbar)$"),
    "planter_box_01":   dict(category="props", tris=3000, height=0.55, tex=512),
    "planter_pot_clay": dict(category="props", tris=2500, height=0.42, tex=512),
    "potted_plant_01":  dict(category="plants", tris=9000, height=0.85, tex=512),
    "potted_plant_02":  dict(category="plants", tris=7000, height=0.7, tex=512),
}

# Only these categories may carry wind. Tagging by transparency alone caught
# the glass in street_lamp_01 and five materials on the benches, which would
# have handed the runtime wind shader a swaying lamp post.
FOLIAGE_CATEGORIES = {"trees", "plants"}

# The runtime picks foliage out by material name (see FoliageWaterRain
# .buildRealTrees), so leaf materials must keep a matching name through export.
LEAF_HINTS = ("leaf", "leaves", "foliage", "needle", "canopy", "frond")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def tri_count():
    n = 0
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.data.calc_loop_triangles()
            n += len(o.data.loop_triangles)
    return n


def import_gltf(asset_id):
    folder = SRC / asset_id
    files = sorted(folder.glob("*.gltf")) + sorted(folder.glob("*.glb"))
    if not files:
        raise FileNotFoundError(f"no glTF in {folder}")
    bpy.ops.import_scene.gltf(filepath=str(files[0]))
    return files[0]


def tag_foliage():
    """Name leaf materials so the runtime wind shader recognises them."""
    tagged = 0
    for m in bpy.data.materials:
        name = (m.name or "").lower()
        alpha = m.blend_method != "OPAQUE" if hasattr(m, "blend_method") else False
        if any(h in name for h in LEAF_HINTS) or alpha:
            if not any(h in name for h in LEAF_HINTS):
                m.name = f"leaves_{m.name}"
            tagged += 1
    return tagged


def shrink_textures(size):
    """Poly Haven ships 1k maps per material; a tree carries nine of them.

    The image has to be packed after scaling. Left unpacked the glTF exporter
    copies the original file off disk and the resize is silently discarded -
    it cost a 5.9 MB tree to notice.
    """
    done = 0
    for img in bpy.data.images:
        if img.size[0] == 0:
            img.reload()
        w, h = img.size
        if not w or max(w, h) <= size:
            continue
        k = size / max(w, h)
        img.scale(max(1, int(w * k)), max(1, int(h * k)))
        img.pack()
        done += 1
    return done


def weld(distance):
    """Merge nearby vertices so the collapse decimator can actually bite.

    A crown is thousands of disconnected leaf islands, and COLLAPSE cannot
    remove a whole island - tree_small_02's needles floored at 42 k triangles
    against a 600 budget. Welding first fuses leaf clusters into blobs, which
    is the right read for far-field massing anyway.
    """
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=distance)
        bpy.ops.object.mode_set(mode="OBJECT")


def decimate(budget):
    before = tri_count()
    if before <= budget:
        return before, before
    ratio = budget / before
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        bpy.context.view_layer.objects.active = o
        mod = o.modifiers.new("decimate", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = ratio
        # symmetry off: tree crowns are asymmetric and forcing it folds branches
        mod.use_symmetry = False
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return before, tri_count()


def keep_only(pattern):
    """Drop everything whose object name does not match, kit parts included."""
    rx = re.compile(pattern)
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        if not rx.search(o.name):
            bpy.data.objects.remove(o, do_unlink=True)


def keep_largest_loose_part():
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in objs:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.mesh.separate(type="LOOSE")
    parts = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(parts) < 2:
        return
    parts.sort(key=lambda o: len(o.data.vertices), reverse=True)
    for o in parts[1:]:
        bpy.data.objects.remove(o, do_unlink=True)


def normalise_height(target_h):
    """Sit the asset on z=0, and scale it to a known height if one is given.

    Poly Haven models are already in metres, so target_h is only about giving
    the runtime a predictable size; passing None keeps the real-world scale.
    """
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    if not objs:
        return 1.0
    zs = [(o.matrix_world @ mathutils.Vector(c)).z for o in objs for c in o.bound_box]
    lo, hi = min(zs), max(zs)
    height = hi - lo
    k = 1.0 if (target_h is None or height <= 0) else target_h / height
    for o in objs:
        if o.parent:
            continue
        o.scale = tuple(s * k for s in o.scale)
        o.location = (o.location[0] * k, o.location[1] * k, (o.location[2] - lo) * k)
    return k


def export(name, category):
    dest = OUT / category
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{name}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )
    return path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="subset of asset ids")
    args = ap.parse_args(argv)

    ids = args.only or list(SPEC)
    report = []
    for asset_id in ids:
        if asset_id not in SPEC:
            print(f"!! {asset_id} not in SPEC, skipping", file=sys.stderr)
            continue
        s = SPEC[asset_id]
        if not (SRC / asset_id).exists():
            print(f"!! {asset_id} not downloaded, run tools/fetch_polyhaven.py", file=sys.stderr)
            continue
        category, budget = s["category"], s["tris"]
        # parts turns one source into several GLBs, each built from a fresh import
        for name, keep in (s.get("parts") or {asset_id: s.get("keep")}).items():
            reset()
            import_gltf(asset_id)
            if keep:
                keep_only(keep)
            if s.get("loose"):
                keep_largest_loose_part()
            leaves = tag_foliage() if category in FOLIAGE_CATEGORIES else 0
            shrink_textures(s["tex"])
            before, after = decimate(budget)
            normalise_height(s["height"])
            path = export(name, category)
            size = path.stat().st_size
            report.append({"id": asset_id, "name": name, "category": category,
                           "file": path.name, "height": s["height"], "tris": after,
                           "tris_source": before, "leaf_materials": leaves, "bytes": size})
            print(f"{name:30} {before:>9,} -> {after:>7,} tris   "
                  f"{size / 1e6:5.2f} MB   {leaves} leaf mats")

            if s.get("lod"):
                # decimate the already-decimated scene again, then re-export;
                # textures are 256 because the whole point is far-field massing.
                # The weld only has to fuse leaves into islands big enough for
                # COLLAPSE to bite on; at 3% of height (22 cm on a 7.5 m tree)
                # it swallowed whole leaf clusters and left a bald armature
                # before the decimator even ran.
                shrink_textures(256)
                weld((s["height"] or 5) * 0.015)
                _, lod_tris = decimate(s["lod"])
                lod_path = export(f"{name}_lod", category)
                report.append({"id": asset_id, "name": f"{name}_lod", "category": category,
                               "file": lod_path.name, "height": s["height"], "tris": lod_tris,
                               "tris_source": after, "leaf_materials": leaves,
                               "bytes": lod_path.stat().st_size})
                print(f"{name + '_lod':30} {after:>9,} -> {lod_tris:>7,} tris   "
                      f"{lod_path.stat().st_size / 1e6:5.2f} MB")

    (ROOT / "blender" / "prep_report.json").write_text(json.dumps(report, indent=1))
    print(f"\n{len(report)} assets written under {OUT}")


if __name__ == "__main__":
    main()
