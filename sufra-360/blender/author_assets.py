"""Author the venue's own furniture and fixtures in Blender, from scratch.

Everything here is modelled procedurally at real-world dimensions rather than
downloaded, so the venue owns its look outright and nothing depends on a
third-party licence. Each piece is built, given PBR materials, and exported as
a Draco-compressed GLB.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/author_assets.py

Writes into static/3d/models/authored/.
"""
import math
import pathlib

import bpy

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "3d" / "models" / "authored"


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough=0.6, metal=0.0, alpha=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
    return m


def put(obj, material):
    obj.data.materials.append(material)
    return obj


def cube(x, y, z, sx, sy, sz, material, name=""):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    o = bpy.context.active_object
    o.scale = (sx / 2, sy / 2, sz / 2)
    if name:
        o.name = name
    return put(o, material)


def cyl(x, y, z, r, h, material, name="", verts=20, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=(x, y, z))
    o = bpy.context.active_object
    if rot:
        o.rotation_euler = rot
    if name:
        o.name = name
    return put(o, material)


def torus(x, y, z, R, r, material, rot=None, name=""):
    bpy.ops.mesh.primitive_torus_add(location=(x, y, z), major_radius=R, minor_radius=r,
                                     major_segments=24, minor_segments=10)
    o = bpy.context.active_object
    if rot:
        o.rotation_euler = rot
    if name:
        o.name = name
    return put(o, material)


def export(name):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.glb"
    bpy.ops.export_scene.gltf(filepath=str(p), export_format="GLB",
                              export_draco_mesh_compression_enable=True,
                              export_draco_mesh_compression_level=6,
                              export_apply=True, export_yup=True,
                              export_cameras=False, export_lights=False)
    n = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print(f"{name:22} {n:>6} faces   {p.stat().st_size/1e6:5.2f} MB")


# ---------------------------------------------------------------- umbrella
def build_umbrella():
    """A market umbrella: eight fabric panels that sag between the ribs, a
    scalloped hem, real ribs, a two-part pole and a finial. Built as panels
    rather than a lathe so the segment seams and the hem scallop are actual
    geometry and catch light."""
    reset()
    canvas = mat("umbrella_canvas", (0.90, 0.86, 0.78), rough=0.92)
    poleM = mat("umbrella_pole", (0.36, 0.28, 0.18), rough=0.55)
    ribM = mat("umbrella_rib", (0.30, 0.24, 0.16), rough=0.6)
    brass = mat("umbrella_brass", (0.72, 0.56, 0.26), rough=0.3, metal=0.9)

    R, SEG, RINGS = 1.5, 8, 6
    verts, faces = [], []
    for ri in range(RINGS + 1):
        t = ri / RINGS
        for si in range(SEG * 4 + 1):
            a = si / (SEG * 4) * math.tau
            # 1 on a rib, 0 midway between two ribs
            ribness = (math.cos(a * SEG) + 1) / 2
            sag = (1 - ribness) * 0.13 * t * t          # fabric drops between ribs
            rr = t * R * (1 + (1 - ribness) * 0.02)
            z = 0.40 * (1 - t * t) - sag
            if ri == RINGS:                              # hem: dips, flicks up on ribs
                z -= 0.06 * (1 - ribness) - 0.03 * ribness
            verts.append((math.cos(a) * rr, math.sin(a) * rr, z))
    row = SEG * 4 + 1
    for ri in range(RINGS):
        for si in range(SEG * 4):
            a0 = ri * row + si
            faces.append((a0, a0 + row, a0 + row + 1, a0 + 1))
    me = bpy.data.meshes.new("canopy")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("canopy", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location.z = 2.30
    put(ob, canvas)

    cyl(0, 0, 1.15, 0.028, 2.30, poleM, "pole")
    for i in range(SEG):
        a = i / SEG * math.tau
        bpy.ops.mesh.primitive_cube_add(size=1, location=(math.cos(a) * R * 0.5,
                                                          math.sin(a) * R * 0.5, 2.52))
        rib = bpy.context.active_object
        rib.scale = (R * 0.5, 0.012, 0.012)
        rib.rotation_euler = (0, -0.16, a)
        put(rib, ribM)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.055, location=(0, 0, 2.76))
    put(bpy.context.active_object, brass)
    # a weighted base so it does not appear to grow out of the paving
    cyl(0, 0, 0.05, 0.34, 0.10, mat("umbrella_base", (0.16, 0.16, 0.18), rough=0.5, metal=0.3), "base")
    export("umbrella")


# ------------------------------------------------------------ kitchen suite
def build_kitchen():
    """A commercial prep run that reads as real cabinetry, not a slab: a
    panelled base with visible door seams and handles, a twin-bowl sink with
    a gooseneck mixer, an overshelf with plate stacks and trays, and a wall
    extraction hood over the run so it reads as a kitchen from any angle.
    Dimensions are catering-standard: 0.90 counter, 0.70 depth, hood at 2.0.
    The earlier version's standalone fridge block floated on the floor at
    the wrong scale relative to the room and was cut rather than fixed."""
    reset()
    steel = mat("kit_steel", (0.74, 0.76, 0.79), rough=0.28, metal=0.9)
    dark = mat("kit_dark", (0.13, 0.14, 0.16), rough=0.45, metal=0.35)
    panel = mat("kit_panel", (0.20, 0.21, 0.23), rough=0.4, metal=0.5)
    white = mat("kit_plate", (0.93, 0.93, 0.91), rough=0.25)
    tray = mat("kit_tray", (0.32, 0.30, 0.28), rough=0.6)
    handle = mat("kit_handle", (0.68, 0.68, 0.70), rough=0.3, metal=0.85)

    L, D, H = 3.6, 0.70, 0.90
    cube(0, 0, H - 0.02, L, D, 0.04, steel, "counter_top")
    # a solid carcass first, THEN doors flush on its front face - without a
    # body behind them the door panels were unsupported slabs floating in
    # front of nothing, which is what made the counter read as loose debris
    cube(0, 0, (H - 0.06) / 2, L - 0.06, D - 0.06, H - 0.10, dark, "counter_body")
    n_doors = 6
    dw = (L - 0.10) / n_doors
    for i in range(n_doors):
        cx = -L / 2 + 0.05 + dw * (i + 0.5)
        cube(cx, D / 2 - 0.005, (H - 0.06) / 2, dw - 0.02, 0.02, H - 0.14, panel, "cab_door")
        cube(cx, D / 2 + 0.010, H - 0.28, dw * 0.5, 0.015, 0.03, handle, "cab_handle")
    for sx in (-L / 2 + 0.08, L / 2 - 0.08):          # kick rails
        cyl(sx, 0, 0.06, 0.02, 0.12, steel, "foot")

    # twin sink bowls: rims sunk into the top, with a drainer groove between
    for bx in (-1.15, -0.55):
        cube(bx, 0, H - 0.06, 0.42, 0.42, 0.02, steel, "sink_rim")
        cube(bx, 0, H - 0.22, 0.38, 0.38, 0.30, dark, "sink_bowl")
    # gooseneck mixer tap: column, curved spout, two levers
    tapx, tapy = -0.85, -0.24
    cyl(tapx, tapy, H + 0.12, 0.022, 0.24, steel, "tap_column")
    for i in range(9):                                 # the arc of the gooseneck
        t = i / 8
        a = t * math.pi * 0.85
        cyl(tapx + math.sin(a) * 0.17, tapy + (1 - math.cos(a)) * 0.17 * 0.15,
            H + 0.24 + math.cos(a) * 0.10 + 0.06, 0.017, 0.05, steel, "tap_arc",
            verts=10, rot=(math.pi / 2 - a, 0, 0))
    cyl(tapx + 0.165, tapy + 0.02, H + 0.20, 0.020, 0.06, steel, "tap_outlet")
    for lx in (-0.06, 0.06):
        cyl(tapx + lx, tapy, H + 0.235, 0.010, 0.09, steel, "tap_lever",
            verts=8, rot=(0, math.pi / 2.6, 0))

    # overshelf on posts, with plate stacks and trays on it
    cube(0, -0.10, 1.45, L - 0.2, 0.34, 0.03, steel, "overshelf")
    for sx in (-L / 2 + 0.14, 0, L / 2 - 0.14):
        cyl(sx, -0.10, 1.18, 0.018, 0.52, steel, "shelf_post")
    for i, px in enumerate((-1.3, -0.95, 0.55)):
        for k in range(7):
            cyl(px, -0.10, 1.475 + k * 0.017, 0.115, 0.014, white, "plate", verts=18)
    for tx in (1.05, 1.35):
        cube(tx, -0.10, 1.49, 0.26, 0.30, 0.025, tray, "tray")

    # extraction hood on the wall side, the single detail that makes a run
    # of counters read as a KITCHEN from across the room rather than a bar
    cube(0, D / 2 + 0.18, 2.05, L * 0.7, 0.5, 0.5, panel, "hood_body")
    hood_pts = [
        (-L * 0.35, D / 2 + 0.18 - 0.25, 1.80), (L * 0.35, D / 2 + 0.18 - 0.25, 1.80),
        (-L * 0.28, D / 2 + 0.18 + 0.25, 1.80), (L * 0.28, D / 2 + 0.18 + 0.25, 1.80),
    ]
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, D / 2 + 0.18, 1.72))
    skirt = bpy.context.active_object
    skirt.scale = (L * 0.32, 0.24, 0.001)
    skirt.rotation_euler = (0.5, 0, 0)
    put(skirt, panel)
    for sx in (-L * 0.3, L * 0.3):
        cyl(sx, D / 2 + 0.18, 1.90, 0.02, 0.30, steel, "hood_strap")
    # a warm task light under the hood lip
    lamp_glow = mat("kit_lamp", (1.0, 0.92, 0.75), rough=0.4)
    cube(0, D / 2 + 0.02, 1.79, L * 0.6, 0.03, 0.02, lamp_glow, "hood_light")

    export("kitchen_run")


# --------------------------------------------------------- bathroom suite
def build_bathroom():
    """A wall-hung pan with a real seat and cistern, and a vanity basin with a
    mixer tap and mirror. Standard heights: pan rim 0.40, basin rim 0.85."""
    reset()
    porc = mat("bath_porcelain", (0.95, 0.95, 0.94), rough=0.14)
    chrome = mat("bath_chrome", (0.80, 0.82, 0.85), rough=0.12, metal=0.95)
    seatM = mat("bath_seat", (0.90, 0.90, 0.89), rough=0.3)
    stone = mat("bath_stone", (0.30, 0.29, 0.28), rough=0.5)
    glassM = mat("bath_mirror", (0.85, 0.89, 0.93), rough=0.04, metal=1.0)

    # --- pan: tapered pedestal, oval bowl, seat ring, lid-less cistern
    cyl(0, 0.02, 0.16, 0.15, 0.32, porc, "pan_foot", verts=24)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.20, location=(0, 0, 0.36))
    bowl = bpy.context.active_object
    bowl.scale = (1.0, 1.25, 0.55)
    put(bowl, porc)
    torus(0, 0, 0.41, 0.19, 0.022, seatM, name="seat_ring")
    cube(0, 0.30, 0.55, 0.36, 0.14, 0.42, porc, "cistern")
    cube(0, 0.30, 0.77, 0.38, 0.16, 0.03, porc, "cistern_lid")
    cyl(0.10, 0.30, 0.79, 0.022, 0.02, chrome, "flush", verts=14)

    # --- vanity: stone top, undercounter, basin, mixer tap, mirror
    cube(1.30, 0.12, 0.83, 1.00, 0.50, 0.05, stone, "vanity_top")
    cube(1.30, 0.12, 0.41, 0.94, 0.46, 0.78, mat("bath_cab", (0.22, 0.18, 0.15), rough=0.5), "vanity_cab")
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.19, location=(1.30, 0.12, 0.845))
    basin = bpy.context.active_object
    basin.scale = (1.0, 0.85, 0.34)
    put(basin, porc)
    cyl(1.30, -0.08, 0.94, 0.020, 0.18, chrome, "basin_tap")
    cyl(1.30, -0.03, 1.02, 0.016, 0.11, chrome, "basin_spout", verts=12,
        rot=(math.pi / 2.2, 0, 0))
    cyl(1.30, -0.12, 1.03, 0.011, 0.07, chrome, "basin_lever", verts=10,
        rot=(0, math.pi / 2.4, 0))
    cube(1.30, 0.34, 1.42, 0.86, 0.02, 0.66, glassM, "mirror")
    cube(1.30, 0.345, 1.42, 0.92, 0.015, 0.72, mat("bath_frame", (0.18, 0.16, 0.14), rough=0.4), "mirror_frame")

    # a floor tile plane and a partition between the pan and the vanity - the
    # earlier version shipped only the fixtures, which floated against
    # whatever material happened to be under the wc room in the venue
    tile = mat("bath_tile", (0.86, 0.85, 0.82), rough=0.35)
    cube(0.65, 0.10, 0.005, 2.6, 1.1, 0.01, tile, "bath_floor")
    for row in range(6):
        cube(-0.55, row * 0.18 - 0.35, 0.011, 2.55, 0.01, 0.002,
             mat("bath_grout", (0.6, 0.59, 0.56), rough=0.7), "grout_line")
    cube(0.62, -0.02, 0.95, 0.03, 1.05, 1.9, mat("bath_partition", (0.94, 0.93, 0.90), rough=0.4), "partition")
    export("bathroom_suite")


# --------------------------------------------------------------- banquette
def build_banquette():
    """Upholstered wall-seating bench: a plinth, a seat cushion, a tufted
    back cushion against the wall, and two bolster-style arms. Modelled 1.2 m
    long so it tiles along a wall in whatever multiple the room needs."""
    reset()
    frame = mat("bnq_frame", (0.14, 0.10, 0.07), rough=0.4)
    velvet = mat("bnq_velvet", (0.20, 0.26, 0.42), rough=0.85)
    piping = mat("bnq_piping", (0.68, 0.56, 0.28), rough=0.35, metal=0.5)

    W, D, seatH, backH = 1.2, 0.55, 0.46, 1.05
    cube(0, 0, 0.08, W, D, 0.16, frame, "plinth")
    cube(0, 0.02, seatH - 0.06, W - 0.04, D - 0.08, 0.14, velvet, "seat_cushion")
    # back cushion, tufted look via a shallow grid of diamond dimples
    cube(0, D / 2 - 0.06, (seatH + backH) / 2, W - 0.06, 0.10, backH - seatH, velvet, "back_cushion")
    for gx in range(3):
        for gy in range(2):
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=0.03,
                location=(-W / 2 + 0.2 + gx * (W - 0.4) / 2, D / 2 - 0.01,
                          seatH + 0.12 + gy * (backH - seatH - 0.24)))
            dimple = bpy.context.active_object
            dimple.scale.y = 0.3
            put(dimple, frame)
    # brass piping along the seat edge
    for sx in (-1, 1):
        cube(sx * (W / 2 - 0.02), 0.02, seatH - 0.005, 0.02, D - 0.08, 0.02, piping, "seat_edge")
    # bolster arms at each end
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.11, depth=D - 0.1,
                                            location=(sx * (W / 2 - 0.02), 0, seatH + 0.14))
        arm = bpy.context.active_object
        arm.rotation_euler = (math.pi / 2, 0, 0)
        put(arm, velvet)
    export("banquette")


# ------------------------------------------------------------ dining table
def build_dining_table():
    """A 1.6 x 0.9 m walnut dining table on tapered legs with an apron - the
    indoor standard. Top at 0.75."""
    reset()
    wood = mat("tbl_walnut", (0.28, 0.16, 0.09), rough=0.35)
    W, D, H = 1.6, 0.9, 0.75
    cube(0, 0, H - 0.02, W, D, 0.045, wood, "top")
    cube(0, 0, H - 0.11, W - 0.18, D - 0.18, 0.10, wood, "apron")
    for sx in (-1, 1):
        for sy in (-1, 1):
            bpy.ops.mesh.primitive_cone_add(radius1=0.032, radius2=0.022, depth=H - 0.16,
                                            vertices=10,
                                            location=(sx * (W / 2 - 0.10), sy * (D / 2 - 0.10),
                                                      (H - 0.16) / 2))
            put(bpy.context.active_object, wood)
    export("dining_table")


def build_plated_dish():
    """A plated main course: a white plate, a mound of food with visible
    texture variation (not one flat blob), a sauce swirl, and a herb sprig.
    Colour is parameterised so the same geometry ships as three dishes."""
    for variant, (food_rgb, sauce_rgb, name) in enumerate([
        ((0.62, 0.42, 0.22), (0.35, 0.10, 0.08), "dish_meat"),
        ((0.85, 0.72, 0.35), (0.55, 0.30, 0.10), "dish_grain"),
        ((0.30, 0.45, 0.20), (0.70, 0.55, 0.20), "dish_veg"),
    ]):
        reset()
        plate = mat("food_plate", (0.94, 0.93, 0.90), rough=0.2)
        rim = mat("food_rim", (0.72, 0.60, 0.30), rough=0.3, metal=0.7)
        food = mat(f"food_{name}", food_rgb, rough=0.6)
        sauce = mat(f"sauce_{name}", sauce_rgb, rough=0.15)
        herb = mat("food_herb", (0.20, 0.42, 0.16), rough=0.7)

        cyl(0, 0, 0.008, 0.14, 0.016, plate, "plate_base", verts=32)
        torus(0, 0, 0.014, 0.135, 0.006, rim, name="plate_rim")
        # the food itself: several overlapping irregular lumps, not one dome -
        # a single sphere reads as a scoop of ice cream, not a cooked dish
        for i in range(5):
            a = i / 5 * math.tau
            r = 0.02 + (i % 3) * 0.01
            bpy.ops.mesh.primitive_ico_sphere_add(
                radius=0.028 + (i % 2) * 0.008, subdivisions=1,
                location=(math.cos(a) * r, math.sin(a) * r, 0.024 + (i % 2) * 0.006))
            lump = bpy.context.active_object
            lump.scale = (1.1, 1.0, 0.7)
            put(lump, food)
        # a sauce swirl: a thin flattened torus arc
        torus(0.01, -0.01, 0.017, 0.05, 0.006, sauce, rot=(0, 0, 0.4), name="sauce_swirl")
        # a herb sprig on top
        bpy.ops.mesh.primitive_cone_add(radius1=0.006, radius2=0.001, depth=0.03,
                                        location=(0.015, 0.02, 0.05))
        put(bpy.context.active_object, herb)
        export(name)


if __name__ == "__main__":
    build_umbrella()
    build_kitchen()
    build_bathroom()
    build_dining_table()
    build_banquette()
    build_plated_dish()
    print("\nauthored assets written to", OUT)
