"""Download CC0 source assets from Poly Haven into assets_src/.

Poly Haven ships models as glTF plus loose textures, at photogrammetry density:
a single tree is 40-200 MB of geometry, far too heavy to serve. This only
fetches the raw source. blender/prep_assets.py is what decimates it and writes
the GLBs that the app actually loads, so assets_src/ stays out of git.

    python3 tools/fetch_polyhaven.py            # everything in WANTED
    python3 tools/fetch_polyhaven.py island_tree_01 shrub_03

Requests go through curl: the python.org interpreter on this machine has no CA
bundle, so urllib cannot complete the TLS handshake to the CDN.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets_src" / "polyhaven"
API = "https://api.polyhaven.com"

# Poly Haven ids -> what they are for in the venue. Everything here is CC0.
WANTED = {
    # --- interior fit-out (all CC0). The dining room was primitive boxes; the
    # reference brief asks for real upholstered chairs, real tables, a bar that
    # reads as a bar, and table decor rather than cylinders.
    "dining_chair_02":          "dining chairs, the main indoor seating",
    "GreenChair_01":            "upholstered chair, window/east rooms",
    "WoodenChair_01":           "wooden chair, garden court",
    "ArmChair_01":              "armchair, the lounge",
    "Sofa_01":                  "banquette/wall sofa, room edges",
    "dining_table":             "rectangular dining tables",
    "WoodenTable_02":           "square/small dining tables",
    "coffee_table_round_01":    "round tables, lounge",
    "bar_chair_round_01":       "bar stools at the counter",
    "metal_stool_02":           "second stool variant",
    "Shelf_01":                 "back-bar and service shelving",
    "modern_wooden_cabinet":    "sideboards along the room edges",
    "wine_bottle_01":           "bar bottles",
    "ceramic_vase_02":          "table flower vases",
    "brass_vase_01":            "decor vases, sideboards",
    "ceramic_pot":              "indoor plant pots",
    "food_pomegranate_01":      "table food",
    "food_apple_01":            "table food",
    "desk_lamp_arm_01":         "table/service lamps",
    "industrial_wall_lamp":     "wall sconces",
    "modern_ceiling_lamp_01":   "pendant lights over the bar",

    "island_tree_01":             "promenade / garden tree, coastal broadleaf",
    "island_tree_02":             "promenade / garden tree, second species",
    "tree_small_02":              "garden tree, smaller crown",
    "shrub_01":                   "planting beds along the plot edge",
    "shrub_03":                   "low ground planting",
    "street_lamp_01":             "promenade lamp posts (22 in venue/floor.json)",
    "outdoor_table_chair_set_01": "terrace table and chair set",
    "modular_street_seating":     "promenade benches",
    "planter_box_01":             "terrace and entrance planters",
    "planter_pot_clay":           "terrace and entrance planters",
    "potted_plant_01":            "interior decor",
    "potted_plant_02":            "interior decor",
}


def curl_json(url):
    out = subprocess.run(["curl", "-sfL", url], capture_output=True, check=True).stdout
    return json.loads(out)


def fetch(asset_id):
    dest = SRC / asset_id
    files = curl_json(f"{API}/files/{asset_id}")
    gltf = files.get("gltf")
    if not gltf:
        print(f"!! {asset_id}: no glTF format offered", file=sys.stderr)
        return False
    res = "1k" if "1k" in gltf else sorted(gltf)[0]
    entry = gltf[res]["gltf"]

    dest.mkdir(parents=True, exist_ok=True)
    jobs = [(entry["url"], dest / pathlib.Path(entry["url"]).name)]
    for rel, meta in entry.get("include", {}).items():
        jobs.append((meta["url"], dest / rel))

    total = sum(m.get("size", 0) for m in entry.get("include", {}).values()) + entry.get("size", 0)
    print(f"{asset_id} [{res}] {total / 1e6:.0f} MB -> {dest.relative_to(ROOT)}")
    for url, path in jobs:
        if path.exists() and path.stat().st_size > 0:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sfL", url, "-o", str(path)], check=True)
    return True


def main():
    ids = sys.argv[1:] or list(WANTED)
    ok = 0
    for i in ids:
        try:
            ok += bool(fetch(i))
        except subprocess.CalledProcessError as e:
            print(f"!! {i}: download failed ({e})", file=sys.stderr)
    print(f"\n{ok}/{len(ids)} assets in {SRC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
