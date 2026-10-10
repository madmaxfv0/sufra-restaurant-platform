# SUFRA 360 asset manifest  (build 7b)

Legend:  IN SCENE = downloaded, licence read, loaded by GLTFLoader/RGBELoader/TextureLoader, placed.
         MANUAL   = the provider is unreachable from the build machine (network policy: host_not_allowed);
                    the loader and folder are ready, drop the files in and they appear with no code change.

## TREES
asset:        (MANUAL) two deciduous species + one shrub from Poly Haven — https://polyhaven.com/models?c=nature
source:       Poly Haven
license:      CC0
poly count:   target ≤ 60k tris per species after Draco; the loader instances them, so 18 trees cost 18× nothing extra
LOD:          not yet — one level; instanced
loader:       static/3d/models/trees/manifest.json → FoliageSystem.buildRealTrees(); hierarchical wind on leaf materials
until then:   card-canopy trees (leaf_card.png alpha cards, one InstancedMesh, per-card phase/height wind)

## CHAIRS
asset:        SheenChair (IN SCENE, 96 instances)
source:       Khronos glTF-Sample-Assets
license:      CC0-1.0
also:         ChairDamaskPurplegold (CC-BY-4.0) available for the lounge

## TABLES
asset:        Table — wood top, steel legs (IN SCENE on rectangular tables)
source:       Sara Vieira via pmndrs market; textures ambientCG Wood027 1K (Color/Normal/Roughness)
license:      CC0
round tables: lathe-turned tops with linen PBR + turned pedestal (no CC0 round table reachable; MANUAL: Poly Haven furniture)

## PEOPLE
asset:        (MANUAL) 8 Mixamo characters + Sitting Idle / Sitting Talking / Sitting Drinking / Standing Idle / Walking
source:       Adobe Mixamo — requires Adobe login; no automated download exists
license:      Mixamo terms (free for use in your own projects)
loader:       static/3d/models/humans/manifest.json → GuestSystem (SkeletonUtils.clone + AnimationMixer, desynchronised)
behaviour:    seats N guests at every OCCUPIED table from the live feed; two waiters walk the venue paths
until then:   no people are drawn — nothing fake stands in for them

## LAMPS
asset:        Lantern (IN SCENE, one per table, Draco, 1K)
source:       Khronos glTF-Sample-Assets (Microsoft)
license:      CC0-1.0
status light: per-table emissive flame + PointLight (green free / red occupied / amber soon-or-held), 300–700 ms fade

## TABLEWARE  (IN SCENE, instanced per cover)
plate-dinner, glass-wine, glass, utensil-fork, utensil-knife, wine-red, cup-saucer
source:       Kenney via pmndrs market            license: CC0
IridescentDishWithOlives (food, appears only where a guest is seated)  Khronos  CC-BY-4.0
WaterBottle, GlassVaseFlowers                                            Khronos  CC0-1.0

## PLANTS
asset:        Plant, 80k verts (IN SCENE in the court planters); leaf cards for hedges and shrubs
source:       Sara Vieira via pmndrs market       license: CC0

## PROPS
asset:        Bench ×3 on the promenade (IN SCENE)   source: Sara Vieira via pmndrs market   license: CC0

## HDRI  (IN SCENE, swapped by time of day, PMREM via scene.environment)
potsdamer_platz_1k.hdr   night      Poly Haven (Greg Zaal)   CC0
kiara_1_dawn_1k.hdr      dawn/dusk  Poly Haven (Greg Zaal)   CC0
lebombo_1k.hdr           day        Poly Haven (Greg Zaal)   CC0
venice_sunset_1k.hdr     fallback   Poly Haven               CC0

## FLOOR / SURFACE TEXTURES
WoodFloor043 1K (Color/Normal/Roughness/AO)   ambientCG  CC0   indoor dining floors
Marble 1K (Color/Normal/Roughness)            ambientCG  CC0   bar counter
Tiles 1K (Color/Normal/Roughness)             ambientCG  CC0   restrooms
cobble / terrace / gravel / plaster / bark    generated PBR sets with normal + roughness (this project, CC0)
hardwood2, brick                              three.js examples  MIT

## WATER
shader/package:  three/examples/jsm/objects/Water.js — reflective + refractive, moving normal map,
                 Fresnel, sun specular; distortion driven by live wind + rain

## RAIN / SNOW
implementation:  RainSystem — GPU LineSegments (rain) / Points (snow), per-drop seed/speed/length,
                 wind lean from live direction, depth fade, additive; wetness → material roughness/albedo/env
