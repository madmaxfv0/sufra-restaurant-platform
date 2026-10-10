# Asset credits — SUFRA 360

Every third-party file in `static/3d/`, its creator, source and licence.
Nothing here is hotlinked; all files are shipped with the project.

## 3D models (glTF-Binary, Draco-compressed, textures resized to 1K or 512)

| File | Asset | Creator / source | Licence |
|---|---|---|---|
| chairs/sheen_chair.glb | SheenChair | Khronos Group, glTF-Sample-Assets | CC0-1.0 |
| chairs/damask_chair.glb | ChairDamaskPurplegold | Khronos Group, glTF-Sample-Assets | CC-BY-4.0 |
| lamps/lantern.glb | Lantern | Khronos Group, glTF-Sample-Assets (Microsoft) | CC0-1.0 |
| tableware/water_bottle.glb | WaterBottle | Khronos Group, glTF-Sample-Assets (Microsoft) | CC0-1.0 |
| tableware/dish_olives.glb | IridescentDishWithOlives | Khronos Group, glTF-Sample-Assets | CC-BY-4.0 |
| decor/vase_flowers.glb | GlassVaseFlowers | Khronos Group, glTF-Sample-Assets | CC0-1.0 |

Source: https://github.com/KhronosGroup/glTF-Sample-Assets (licence read from each model's metadata.json)

## Vegetation, street furniture and planters (Poly Haven, all CC0-1.0)

Downloaded by `python3 tools/fetch_polyhaven.py` into `assets_src/polyhaven/`
(git-ignored), then decimated and re-exported by
`blender/prep_assets.py`. Poly Haven builds these for offline rendering —
island_tree_01 alone is 1.6 M triangles and tree_small_02 is 2.1 M — so none
of them is servable as downloaded. The table below records what ships.

| File | Poly Haven asset | Source triangles | Shipped | Size |
|---|---|---|---|---|
| models/trees/island_tree_01.glb | Island Tree 01 | 1,599,403 | 60,000 | 1.54 MB |
| models/trees/island_tree_02.glb | Island Tree 02 | 1,072,212 | 52,000 | 1.33 MB |
| models/trees/tree_small_02.glb | Tree Small 02 | 2,062,487 | 52,000 | 1.39 MB |
| models/plants/shrub_01.glb | Shrub 01 | 156,012 | 284 | 0.44 MB |
| models/plants/shrub_03.glb | Shrub 03 | 8,287 | 2,385 | 0.45 MB |
| models/plants/potted_plant_01.glb | Potted Plant 01 | 176,226 | 8,997 | 0.59 MB |
| models/plants/potted_plant_02.glb | Potted Plant 02 | 69,806 | 6,997 | 0.56 MB |
| models/props/street_lamp_01.glb | Street Lamp 01 | 30,610 | 6,000 | 0.35 MB |
| models/props/terrace_table.glb | Outdoor Table Chair Set 01 (table) | 9,828 | 2,324 | 0.42 MB |
| models/props/terrace_chair.glb | Outdoor Table Chair Set 01 (chair) | 9,828 | 3,752 | 0.42 MB |
| models/props/modular_street_seating.glb | Modular Street Seating (bench only) | 25,156 | 4,996 | 0.31 MB |
| models/props/planter_box_01.glb | Planter Box 01 | 8,094 | 3,000 | 0.14 MB |
| models/props/planter_pot_clay.glb | Planter Pot Clay | 3,080 | 2,499 | 0.09 MB |

Source: https://polyhaven.com/models — every Poly Haven asset is CC0-1.0, no
attribution required, no account needed to download. Individual asset pages
are `https://polyhaven.com/a/<id>`, e.g. https://polyhaven.com/a/island_tree_01

The outdoor set is split into a separate table and chair because the venue
places tables against real SUFRA table ids and seats chairs around them
independently; the modular bench keeps only its assembled parts, discarding
the kit's loose spare connectors.

## Additional models (via the pmndrs CC0 market mirror on GitHub)

| File | Asset | Creator | Licence |
|---|---|---|---|
| models/tableware/glass-wine.gltf, glass.gltf, plate-dinner.gltf, plate.gltf, utensil-fork.gltf, utensil-knife.gltf, utensil-spoon.gltf, wine-red.gltf, cup-saucer.gltf | Kenney Food Kit | Kenney (kenney.nl) | CC0 |
| models/props/table.gltf | Table (ambientCG Wood027 PBR) | Sara Vieira | CC0 |
| models/props/bench.gltf | Bench | Sara Vieira | CC0 |
| models/props/plant.gltf | Plant | Sara Vieira | CC0 |

Source: https://github.com/pmndrs/market-assets ("free ready-to-use CC0 models/textures/hdris")

## Scanned materials (ambientCG, CC0, via the same mirror)

textures/wood/WoodFloor043_* · textures/marble/Marble_* · textures/tiles/Tiles_*

## HDRIs (Poly Haven / HDRI Haven, Greg Zaal, CC0, via the same mirror)

hdri/potsdamer_platz_1k.hdr · hdri/kiara_1_dawn_1k.hdr · hdri/lebombo_1k.hdr · hdri/venice_sunset_1k.hdr

## Textures and environment maps

| File | Source | Licence |
|---|---|---|
| water/waternormals.jpg | three.js examples (mrdoob/three.js) | MIT |
| hdr/venice_sunset_1k.hdr | three.js examples, originally Poly Haven | CC0 |
| hdr/royal_esplanade_1k.hdr | three.js examples, originally Poly Haven | CC0 |
| textures/hardwood2_* | three.js examples | MIT |
| textures/brick_* | three.js examples | MIT |
| textures/cobble_*, terrace_*, gravel_*, plaster_*, marble_*, herringbone_*, linen_*, bark_*, leaf_card.png, flower_card.png | generated in-project by tools/texture_gen.py | CC0 (this project) |

## Library

| File | Source | Licence |
|---|---|---|
| static/vendor/three/ | three.js r170 (build + selected examples/jsm) | MIT |
| static/vendor/three/three-mesh-bvh.module.js | three-mesh-bvh 0.8.3 | MIT |

## Upgrading the look

Drop better CC0 models into the same folders and update `CATALOG` in
`static/js/sufra360/AssetManager.js`. Poly Haven (polyhaven.com, all CC0),
Kenney (kenney.nl, CC0) and Quaternius (quaternius.com, CC0) are the
recommended sources. Add a line here for each file.

## Interior fit-out (Poly Haven, all CC0-1.0)

Downloaded by `python3 tools/fetch_polyhaven.py`, prepped by
`blender/prep_assets.py`. These replaced the primitive box chairs, cylinder
tables and untextured decor in the dining rooms.

| File | Poly Haven asset | Use |
|---|---|---|
| models/furniture/dining_chair_02.glb | Dining Chair 02 | main + private room seating |
| models/furniture/GreenChair_01.glb | Green Chair 01 | window / east room seating |
| models/furniture/WoodenChair_01.glb | Wooden Chair 01 | garden court + terrace |
| models/furniture/ArmChair_01.glb | Arm Chair 01 | the lounge |
| models/furniture/Sofa_01.glb | Sofa 01 | banquette / wall seating |
| models/furniture/dining_table.glb | Dining Table | rectangular tables |
| models/furniture/WoodenTable_02.glb | Wooden Table 02 | square tables |
| models/furniture/coffee_table_round_01.glb | Coffee Table Round 01 | round / lounge tables |
| models/furniture/bar_chair_round_01.glb | Bar Chair Round 01 | bar stools |
| models/furniture/metal_stool_02.glb | Metal Stool 02 | second stool variant |
| models/furniture/Shelf_01.glb | Shelf 01 | back-bar shelving |
| models/furniture/modern_wooden_cabinet.glb | Modern Wooden Cabinet | room-edge sideboards |
| models/tableware/ceramic_vase_02.glb | Ceramic Vase 02 | table setting variant A |
| models/tableware/brass_vase_01.glb | Brass Vase 01 | table setting variant B |
| models/tableware/food_pomegranate_01.glb | Food Pomegranate 01 | table food |
| models/tableware/food_apple_01.glb | Food Apple 01 | table food |
| models/plants/ceramic_pot.glb | Ceramic Pot | indoor planting |
| models/lamps/desk_lamp_arm_01.glb | Desk Lamp Arm 01 | table setting variant C |
| models/lamps/industrial_wall_lamp.glb | Industrial Wall Lamp | wall sconces |
| models/lamps/modern_ceiling_lamp_01.glb | Modern Ceiling Lamp 01 | pendants over the bar |

## Imported from the other SUFRA build (exactly two features)

Only the moving-people system and the Menu were taken; nothing else.

| File | Feature | Licence |
|---|---|---|
| static/js/sufra360/ClothedPeopleSystem.js | moving people | project code |
| static/models/clothed_people/ (men_pack, women_pack) | moving people, rigged characters with Walk/Idle | see each pack's bundled License file |
| venue/menu.json, assets/menu/*.jpg | the Menu | see assets/menu/PHOTO_CREDITS.txt |

## Authored (round 2)

| File | Purpose |
|---|---|
| models/authored/banquette.glb | upholstered wall seating, the lounge's back wall |
| models/authored/dish_meat.glb, dish_grain.glb, dish_veg.glb | plated main courses, shown only on occupied tables, cycled per seat |

## ProVis3D 034 Restaurant (user-supplied)

Supplied as a 1.25 GB FBX / 3.9 GB OBJ archviz scene plus a separate 385 MB
Maps folder. 36.5 M triangles across 567 meshes, built for stills - the
ceiling alone is 13.4 M triangles. Extracted by `blender/extract_provis.py`
and given materials by `blender/dress_provis.py`.

| Shipped | Source object | Source tris | Shipped | Real size |
|---|---|---|---|---|
| models/provis/chair.glb | crp_Chair | 339,328 | 9,000 | 0.81 m |
| models/provis/table.glb | Dining_table_Holiday* | 187,104 | 7,136 | 0.75 m |
| models/provis/bar_counter.glb | Bar_301 | 76,656 | 14,000 | 1.20 m |
| models/provis/bar_back.glb | Bar_10 | 8,452 | 8,000 | 4.90 m (unused) |
| models/provis/palm.glb | palm_04 | 57,744 | 7,000 | 3.32 m |
| models/provis/plant.glb | Hanging_plants___indoor_plant00 | 26,586 | 8,346 | 0.36 m |

The export carries no textures: the .mtl has no `map_Kd` on any of its 206
materials and every `Kd` is the default 0.8 grey, so nothing records which of
the 157 supplied maps belongs to which material and the link cannot be
recovered. The material NAMES did survive and are descriptive - `Gỗ` (wood),
`Mây tre` (rattan), `Kim loai` / `Kim loai vang` (metal / brass),
`stone-iland`, `leaf`, `palm_bark`, `stem` - so dress_provis.py matches on
those and applies the project's own scanned wood and marble where grain is
needed, and PBR constants where metal and upholstery read by roughness and
metalness instead.

Source units are centimetres and that did not survive the FBX -> GLB round
trip; the first export put the 0.81 m chair on screen at 80.94 m, so the
pipeline normalises to metres and re-seats each piece on the floor.

bar_back is 4.9 m tall - a full-height unit from a double-height room - and
is not placed: in a 3.2 m dining room it filled the view as a wall of boxes.

## Not included in this repository

| Files | Why | What happens without them |
|---|---|---|
| `models/provis/*.glb` (six files derived from the ProVis3D 034 Restaurant scene) | A licensed third-party product; the derived models are not redistributed here. | `provisChair` and `provisTable` fall back to the Poly Haven dining chair and dining table (`fallback` in `AssetManager.js`). The bar, palm and hanging-plant models are skipped. Copy the six files into `static/3d/models/provis/` to use them. |
| `static/models/clothed_people/` beyond the six characters named in `manifest.json` | The full Quaternius packs are 486 MB; only the six glTF files the scene loads are kept, with each pack's `License.txt` (CC0). | Nothing: these six are the only ones loaded. |
| `assets_src/`, `blender/*.blend` | Source downloads and Blender scenes (about 2 GB), some containing the ProVis geometry. | The `blender/*.py` scripts document the pipeline but cannot be re-run without them. |
