#!/bin/bash
# Re-downloads the third-party assets listed in static/3d/ASSET_CREDITS.md.
# Run from the project folder if static/3d/ is ever empty.
set -e
cd "$(dirname "$0")/.."
A=static/3d; mkdir -p $A/chairs $A/lamps $A/tableware $A/decor $A/water $A/hdr $A/textures
K="https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models"
T="https://raw.githubusercontent.com/mrdoob/three.js/r170/examples/textures"
dl(){ echo " $2"; curl -sL "$1" -o "$2"; }
dl $K/SheenChair/glTF-Binary/SheenChair.glb $A/chairs/sheen_chair.glb
dl $K/ChairDamaskPurplegold/glTF-Binary/ChairDamaskPurplegold.glb $A/chairs/damask_chair.glb
dl $K/Lantern/glTF-Binary/Lantern.glb $A/lamps/lantern.glb
dl $K/WaterBottle/glTF-Binary/WaterBottle.glb $A/tableware/water_bottle.glb
dl $K/IridescentDishWithOlives/glTF-Binary/IridescentDishWithOlives.glb $A/tableware/dish_olives.glb
dl $K/GlassVaseFlowers/glTF-Binary/GlassVaseFlowers.glb $A/decor/vase_flowers.glb
dl $T/waternormals.jpg $A/water/waternormals.jpg
dl $T/equirectangular/venice_sunset_1k.hdr $A/hdr/venice_sunset_1k.hdr
dl $T/equirectangular/royal_esplanade_1k.hdr $A/hdr/royal_esplanade_1k.hdr
for n in hardwood2_diffuse hardwood2_bump hardwood2_roughness brick_diffuse brick_bump brick_roughness; do dl $T/$n.jpg $A/textures/$n.jpg; done
python3 tools/texture_gen.py 2>/dev/null || echo " (texture_gen needs numpy; shipped textures kept)"
echo "done"
