"""Build the ENTIRE restaurant in Blender: floors, walls, bar, every real
table/chair from the live venue data, planters, trees, and people at tables
and on the promenade - all coloured to match the live app, not grey blockouts.

This is a full rebuild FROM the venue's own data (venue/floor.json + the
running server's /api/public/tables), not a re-export of the Three.js scene -
Blender and Three.js are two different renderers, so the geometry is
regenerated here using the same coordinate transform (X/Z/units_to_m) the app
uses, and coloured with the same palettes (CHAIR_STYLE, LAMP) read out of
RestaurantBuilder.js / TableManager.js by hand.

Run (server must be running on :8013 for live table state):
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/build_full_venue.py

Writes blender/sufra_full_venue.blend.
"""
import json
import math
import pathlib
import urllib.request

import bpy
import mathutils

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "static" / "3d" / "models"
OUT = ROOT / "blender" / "sufra_full_venue.blend"

venue = json.loads((ROOT / "venue" / "floor.json").read_text())
MAP = venue["map"]
G = venue["geometry"]
U = MAP["units_to_m"]
W, H = MAP["width"], MAP["height"]

try:
    tables = json.loads(urllib.request.urlopen("http://127.0.0.1:8013/api/public/tables", timeout=5).read())
    print(f"loaded {len(tables)} live tables from the server")
except Exception as e:
    tables = []
    print(f"!! server not reachable ({e}); building the shell without tables")


def X(u): return (u - W / 2) * U
def Z(u): return (u - H / 2) * U


CHAIR_STYLE = {
    "window":  {"cushion": (0.18, 0.24, 0.42), "frame": (0.23, 0.15, 0.09)},
    "east":    {"cushion": (0.18, 0.24, 0.42), "frame": (0.23, 0.15, 0.09)},
    "main":    {"cushion": (0.18, 0.24, 0.42), "frame": (0.23, 0.15, 0.09)},
    "private": {"cushion": (0.43, 0.17, 0.20), "frame": (0.17, 0.10, 0.07)},
    "garden":  {"cushion": (0.90, 0.85, 0.75), "frame": (0.69, 0.53, 0.34)},
    "lounge":  {"cushion": (0.79, 0.64, 0.41), "frame": (0.16, 0.16, 0.18)},
    "terrace": {"cushion": (0.91, 0.87, 0.81), "frame": (0.12, 0.12, 0.14)},
    "bar":     {"cushion": (0.54, 0.39, 0.25), "frame": (0.16, 0.16, 0.18)},
}
LAMP = {
    "AVAILABLE": (0.37, 0.95, 0.66), "OCCUPIED": (1.0, 0.36, 0.29),
    "RESERVED_SOON": (1.0, 0.72, 0.29), "HELD": (1.0, 0.72, 0.29), "UNKNOWN": (1.0, 0.85, 0.65),
}


def mat(name, color, rough=0.6, metal=0.0, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = 3.0
    return m


def collection(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def box(name, coll, cx, cy, cz, sx, sy, sz, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx / 2, sy / 2, sz / 2)
    o.data.materials.append(material)
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)
    return o


def slab(name, coll, x1, y1, x2, y2, ybase, thick, material):
    cx, cz = (X(x1) + X(x2)) / 2, (Z(y1) + Z(y2)) / 2
    sx, sz = abs(X(x2) - X(x1)), abs(Z(y2) - Z(y1))
    return box(name, coll, cx, ybase + thick / 2, cz, sx, thick, sz, material)


def wall(name, coll, x1, y1, x2, y2, height, thick, material):
    cx, cz = (X(x1) + X(x2)) / 2, (Z(y1) + Z(y2)) / 2
    length = math.hypot(X(x2) - X(x1), Z(y2) - Z(y1))
    ang = math.atan2(Z(y2) - Z(y1), X(x2) - X(x1))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, height / 2, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (length / 2, height / 2, thick / 2)
    o.rotation_euler = (0, -ang, 0)
    o.data.materials.append(material)
    for c in list(o.users_collection): c.objects.unlink(o)
    coll.objects.link(o)
    return o


def import_glb_at(path, coll, x, y, z, scale=1.0, yaw=0.0, name=None):
    if not path.exists():
        return None
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.context.scene.objects if o not in before]
    if not new:
        return None
    roots = [o for o in new if o.parent not in new]
    grp = roots[0] if len(roots) == 1 else None
    if grp is None:
        bpy.ops.object.select_all(action="DESELECT")
        for o in roots: o.select_set(True)
        bpy.context.view_layer.objects.active = roots[0]
        bpy.ops.object.join() if False else None  # keep separate; just parent under an empty
        grp = bpy.data.objects.new((name or path.stem) + "_root", None)
        bpy.context.scene.collection.objects.link(grp)
        for o in roots: o.parent = grp
    grp.location = (x, y, z)
    grp.rotation_euler = (0, yaw, 0)
    grp.scale = (scale, scale, scale)
    if name: grp.name = name
    for o in [grp] + new:
        for c in list(o.users_collection): c.objects.unlink(o)
        coll.objects.link(o)
    return grp


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    BUILDING = collection("BUILDING")
    WALLS = collection("WALLS")
    FLOORS = collection("FLOORS")
    BAR = collection("BAR")
    KITCHEN = collection("KITCHEN")
    TABLES = collection("TABLES")
    CHAIRS = collection("CHAIRS")
    LAMPS = collection("LAMPS")
    PLANTS = collection("PLANTS")
    TREES = collection("TREES")
    TERRACE = collection("TERRACE")
    PROMENADE = collection("PROMENADE")
    PEOPLE = collection("PEOPLE")

    m_wall = mat("Wall_Plaster", (0.82, 0.78, 0.70), rough=0.85)
    m_floor_wood = mat("Floor_Wood", (0.42, 0.28, 0.16), rough=0.4)
    m_floor_stone = mat("Floor_Stone", (0.55, 0.52, 0.47), rough=0.85)
    m_floor_gravel = mat("Floor_Grass", (0.30, 0.42, 0.20), rough=0.9)
    m_promenade = mat("Promenade_Paving", (0.42, 0.39, 0.36), rough=0.85)
    m_bar_dark = mat("Bar_Panel", (0.09, 0.08, 0.07), rough=0.5, metal=0.1)
    m_marble = mat("Bar_Marble", (0.85, 0.83, 0.78), rough=0.2)
    m_steel = mat("Steel", (0.78, 0.79, 0.82), rough=0.3, metal=0.85)
    m_water = mat("Water", (0.08, 0.24, 0.42), rough=0.1)

    # ---- shells: land, promenade, plot, rooms, bar, pass
    slab("water", FLOORS, *G["water"], -0.1, 0.2, m_water)
    slab("promenade", PROMENADE, *G["promenade"], 0, 0.12, m_promenade)
    slab("plot", FLOORS, *G["plot"], 0, 0.1, m_floor_gravel)
    for rname, coords in G["rooms"].items():
        m = m_floor_wood if rname in ("window", "main", "east", "private") else \
            (m_promenade if rname == "terrace" else m_floor_stone)
        slab("floor_" + rname, FLOORS, *coords, 0.02, 0.08, m)

    bx1, by1, bx2, by2 = G["building"]
    Hh = 3.2
    wall("wall_south", WALLS, bx1, by2, bx2, by2, Hh, 0.3, m_wall)
    wall("wall_west", WALLS, bx1, by1, bx1, by2, Hh, 0.3, m_wall)
    wall("wall_east", WALLS, bx2, by1, bx2, by2, Hh, 0.3, m_wall)
    wall("wall_north_low", WALLS, bx1, by1, bx2, by1, 1.1, 0.3, m_wall)

    C, B, K = G["bar_counter"], G["back_bar"], G["pass"]
    slab("bar_counter_base", BAR, *C, 0, 0.95, m_bar_dark)
    slab("bar_counter_top", BAR, C[0]-4, C[1]-4, C[2]+4, C[3]+4, 0.95, 0.06, m_marble)
    slab("back_bar", BAR, *B, 0, 2.1, m_bar_dark)
    slab("kitchen_pass", KITCHEN, *K, 0, 0.85, m_bar_dark)
    slab("kitchen_pass_steel", KITCHEN, K[0]-3, K[1]-3, K[2]+3, K[3]+3, 0.85, 0.05, m_steel)

    # ---- lamps (posts)
    m_lamp_post = mat("Lamp_Iron", (0.08, 0.08, 0.09), rough=0.4, metal=0.7)
    for i, (mx, my, on) in enumerate(G.get("lamps", [])):
        if not on: continue
        box(f"lamp_post_{i}", LAMPS, X(mx), 1.1, Z(my), 0.07, 2.2, 0.07, m_lamp_post)

    # ---- trees: real prepped GLBs, scattered at the venue's own tree spots
    tree_files = sorted((MODELS / "trees").glob("*.glb"))
    tree_files = [f for f in tree_files if not f.stem.endswith("_lod")]
    for i, (mx, my, r) in enumerate(G.get("trees", [])):
        f = tree_files[i % len(tree_files)] if tree_files else None
        if f:
            import_glb_at(f, TREES, X(mx), 0, Z(my), scale=(r * U * 1.5) / 3.0,
                          yaw=(mx * 0.7) % 6.28, name=f"tree_{i:02d}")

    # ---- planters
    planter = MODELS / "props" / "planter_pot_clay.glb"
    spots = [[268, 316, 11], [268, 836, 11], [676, 316, 10], [676, 836, 10], [128, 292, 13],
             [128, 660, 13], [128, 1010, 13], [272, 1024, 12], [668, 1024, 12], [272, 1226, 11],
             [668, 1226, 11], [470, 1010, 10], [204, 300, 10], [204, 760, 10], [300, 108, 10], [660, 108, 10]]
    for i, (mx, my, r) in enumerate(spots):
        import_glb_at(planter, TERRACE, X(mx), 0, Z(my), scale=(r * U * 1.55) / 0.5,
                      name=f"planter_{i:02d}")

    # ---- street furniture on the promenade
    lamp_glb = MODELS / "props" / "street_lamp_01.glb"
    bench_glb = MODELS / "props" / "modular_street_seating.glb"
    px1, py1, px2, py2 = G["promenade"]
    n = 10
    for i in range(n):
        t = i / (n - 1)
        my = py1 + (py2 - py1) * t
        import_glb_at(lamp_glb, PROMENADE, X(140), 0, Z(my), scale=1.0, name=f"streetlamp_{i:02d}")
        if i % 2 == 0:
            import_glb_at(bench_glb, PROMENADE, X(170), 0, Z(my + 20), scale=1.0,
                          yaw=math.pi / 2, name=f"bench_{i:02d}")

    # ---- tables + chairs + status lamps, from the LIVE venue data
    table_glb = MODELS / "props" / "terrace_table.glb"
    chair_glb = MODELS / "props" / "terrace_chair.glb"
    for t in tables:
        wx, wy, wz = t["world"]["x"], t["world"]["y"], t["world"]["z"]
        radius = (t["w"] * U) / 2
        zone = t.get("zone", "main")
        style = CHAIR_STYLE.get(zone, CHAIR_STYLE["main"])
        m_cushion = mat(f"Chair_{zone}_cushion", style["cushion"], rough=0.55)
        m_frame = mat(f"Chair_{zone}_frame", style["frame"], rough=0.4, metal=0.3)

        grp = import_glb_at(table_glb, TABLES, wx, 0, wz, scale=radius / 0.45, name=f"TABLE_{t['id'].upper()}")
        if grp is None:
            box(f"TABLE_{t['id'].upper()}", TABLES, wx, 0.38, wz, radius * 1.6, 0.06, radius * 1.6, m_marble)

        seats = t.get("max_party", 4)
        for s in range(seats):
            ang = (2 * math.pi / seats) * s
            cx = wx + math.cos(ang) * (radius + 0.42)
            cz = wz + math.sin(ang) * (radius + 0.42)
            yaw = math.atan2(wx - cx, wz - cz)         # face the table centre
            cg = import_glb_at(chair_glb, CHAIRS, cx, 0, cz, scale=0.86, yaw=yaw,
                               name=f"CHAIR_{t['id'].upper()}_{s}")
            if cg:
                for o in cg.children:
                    if o.data:
                        o.data.materials.clear()
                        o.data.materials.append(m_frame if s % 2 else m_cushion)

        # status lamp: a small emissive sphere over the table, coloured live
        live_state = t.get("live", {}).get("state") if isinstance(t.get("live"), dict) else None
        lamp_color = LAMP.get(live_state, LAMP["AVAILABLE"])
        m_status = mat(f"Lamp_{t['id']}", lamp_color, emit=lamp_color)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(wx, 0.95, wz))
        lo = bpy.context.active_object
        lo.name = f"STATUSLAMP_{t['id'].upper()}"
        lo.data.materials.append(m_status)
        for c in list(lo.users_collection): c.objects.unlink(lo)
        LAMPS.objects.link(lo)

    # ---- people: one guest per table (seated proxy - capsule, since the rig
    # has no sitting pose yet) plus a few walkers on the promenade, using the
    # real character GLB so scale/materials match
    guest_glb = MODELS / "humans" / "guest_casual.glb"
    seat_i = 0
    for t in tables[:12]:                      # a sample, not all 25: keeps the file light
        wx, wy, wz = t["world"]["x"], t["world"]["y"], t["world"]["z"]
        radius = (t["w"] * U) / 2
        ang = 0.6
        px = wx + math.cos(ang) * (radius + 0.42)
        pz = wz + math.sin(ang) * (radius + 0.42)
        yaw = math.atan2(wx - px, wz - pz)
        import_glb_at(guest_glb, PEOPLE, px, 0, pz, scale=1.74 / 1.87, yaw=yaw,
                      name=f"guest_seated_{t['id']}")
        seat_i += 1

    for i, path in enumerate(G.get("walk_paths", [])[:6]):
        mx, my = path[len(path) // 2]
        import_glb_at(guest_glb, PEOPLE, X(mx), 0, Z(my), scale=1.7 / 1.87,
                      yaw=(i * 1.3) % 6.28, name=f"guest_walking_{i:02d}")

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
    print(f"\nwrote {OUT}  ({len(tables)} tables, {len(G.get('trees', []))} trees)")


if __name__ == "__main__":
    main()
