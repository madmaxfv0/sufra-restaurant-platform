"""Give the ProVis furniture real materials.

The FBX/OBJ export lost every texture assignment - the .mtl has no map_Kd at
all and every Kd is the default 0.8 grey - so the geometry arrived as flat
grey plastic. The 157 supplied maps have nothing recording which material
they belong to, so the linkage cannot be recovered.

What did survive is the material NAMES, and they are descriptive:
Gỗ (wood), Mây tre (rattan), Kim loai (metal), Kim loai vang (brass),
stone-iland, leaf, palm_bark, stem. That is enough to dress each piece
properly: scanned wood and marble off the project's own texture library for
the surfaces that need grain, and correct PBR constants for metal, brass and
upholstery, which read by their roughness and metalness rather than a map.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/dress_provis.py
"""
import pathlib
import re

import bpy

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "static" / "3d" / "models" / "provis"
TEX = ROOT / "static" / "3d" / "textures"

# matched in order against the lowercased material name
# (base colour RGB, roughness, metalness, texture stem or None)
RULES = [
    (r"leaf",                  ((0.16, 0.34, 0.13), 0.72, 0.0, None)),
    (r"palm_bark|bark|stem",   ((0.27, 0.21, 0.15), 0.85, 0.0, "bark")),
    (r"mây tre|may tre|rattan",((0.62, 0.46, 0.26), 0.68, 0.0, None)),
    (r"gỗ|go$|wood",           ((0.26, 0.15, 0.09), 0.45, 0.0, "herringbone")),
    (r"kim loai vang|vang|brass|gold", ((0.72, 0.55, 0.24), 0.28, 0.95, None)),
    (r"kim loai|metal",        ((0.30, 0.31, 0.34), 0.38, 0.90, None)),
    (r"stone|marble|iland",    ((0.80, 0.78, 0.74), 0.25, 0.0, "marble")),
    (r"glass",                 ((0.85, 0.90, 0.92), 0.08, 0.0, None)),
]
# Anything unmatched on a chair or sofa is upholstery: these scenes leave the
# fabric on a bare "Material #NNNN". Deep green velvet, matching the venue.
FALLBACK = {
    "chair": ((0.13, 0.24, 0.18), 0.88, 0.0, None),
    "table": ((0.24, 0.14, 0.08), 0.42, 0.0, "herringbone"),
    "bar_counter": ((0.13, 0.12, 0.12), 0.42, 0.1, None),
    "bar_back": ((0.16, 0.13, 0.11), 0.50, 0.1, None),
    "plant": ((0.18, 0.36, 0.15), 0.74, 0.0, None),
    "palm": ((0.18, 0.36, 0.15), 0.74, 0.0, None),
}


def image(stem):
    p = TEX / f"{stem}_albedo.jpg"
    if not p.exists():
        return None
    return bpy.data.images.load(str(p), check_existing=True)


def dress(mat, spec):
    rgb, rough, metal, tex = spec
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes.get("Principled BSDF")
    if not b:
        return
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if tex:
        img = image(tex)
        if img:
            img.pack()
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = img
            # the source has no UVs worth trusting on every part; box-project
            # so grain appears at a sane scale whatever the mapping
            n.projection = "BOX"
            n.projection_blend = 0.25
            nt.links.new(n.outputs["Color"], b.inputs["Base Color"])


def main():
    for glb in sorted(MODELS.glob("*.glb")):
        if glb.stem.endswith("_dressed"):
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(glb))
        named = []
        for mat in bpy.data.materials:
            low = (mat.name or "").lower()
            spec = next((s for rx, s in RULES if re.search(rx, low)), None)
            if spec is None:
                spec = FALLBACK.get(glb.stem, ((0.45, 0.42, 0.38), 0.6, 0.0, None))
                named.append(mat.name + "->fallback")
            else:
                named.append(mat.name + "->rule")
            dress(mat, spec)
        # The source is in centimetres and that did not survive the FBX ->
        # GLB round trip: the first export put a 0.81 m chair on screen at
        # 80.94 m. Normalise to metres and re-seat on the floor.
        import mathutils
        for o in bpy.data.objects:
            if not o.parent:
                o.scale = tuple(v * 0.01 for v in o.scale)
                o.location = tuple(v * 0.01 for v in o.location)
        bpy.context.view_layer.update()
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        if meshes:
            zs = [(o.matrix_world @ mathutils.Vector(c)).z
                  for o in meshes for c in o.bound_box]
            lo = min(zs)
            for o in bpy.data.objects:
                if not o.parent:
                    o.location.z -= lo
            bpy.context.view_layer.update()
            zs = [(o.matrix_world @ mathutils.Vector(c)).z
                  for o in meshes for c in o.bound_box]
            print(f"   {glb.stem}: height {max(zs) - min(zs):.2f} m", flush=True)

        bpy.ops.export_scene.gltf(
            filepath=str(glb), export_format="GLB",
            export_draco_mesh_compression_enable=True,
            export_draco_mesh_compression_level=6,
            export_apply=True, export_yup=True,
            export_cameras=False, export_lights=False)
        print(f"{glb.stem:14} {glb.stat().st_size/1e6:5.2f} MB   {', '.join(named)}", flush=True)


if __name__ == "__main__":
    main()
