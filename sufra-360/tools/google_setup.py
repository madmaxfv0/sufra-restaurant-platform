"""
Google integration setup.

    python3 tools/google_setup.py --key AIza... --place "Baku Boulevard, Baku"
    python3 tools/google_setup.py --key AIza... --lat 51.5022 --lng -0.1624
    python3 tools/google_setup.py --map-table t06 --pano CAoSLEFG... --heading 120
    python3 tools/google_setup.py --show

What this can and cannot do
---------------------------
CAN:  embed Google's own Street View panorama (including "See inside" interior
      imagery where the business has it) beside the generated view, and show
      real exterior / satellite / 45-degree context for arrival.
CANNOT: download, re-render, retouch or repaint that imagery. Google's
      Street View and Maps imagery is licensed for display through Google's
      own embed and JS viewers only. "Take a real restaurant's VR tour and
      edit it" is not something the terms allow, and it is not something this
      tool will pretend to do. To own the pixels you have to capture them -
      see CAPTURE.md.

There is no "Google Earth API" for building this. The relevant products are:
  * Maps Embed API      - streetview / place / view modes, iframe, key-gated
  * Street View Static  - flat images, key-gated
  * Map Tiles API       - photorealistic 3D tiles, exterior only
  * Places API          - place_id, hours, photos
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG = os.path.join(ROOT, "venue", "google.json")

DEFAULT = {
    "api_key": "",
    "place_query": "",
    "place_id": "",
    "location": {"lat": None, "lng": None},
    "exterior_pano_id": "",
    "interior_pano_id": "",
    "table_panos": {},
    "notes": "Imagery stays Google's. Embedded, never modified or cached.",
}


def load():
    if os.path.exists(CFG):
        cfg = json.load(open(CFG))
        for k, v in DEFAULT.items():
            cfg.setdefault(k, v)
        return cfg
    return dict(DEFAULT)


def save(cfg):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(cfg, open(CFG, "w"), indent=1)
    print("wrote %s" % CFG)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key")
    ap.add_argument("--place")
    ap.add_argument("--place-id")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lng", type=float)
    ap.add_argument("--exterior-pano")
    ap.add_argument("--interior-pano")
    ap.add_argument("--map-table")
    ap.add_argument("--pano")
    ap.add_argument("--heading", type=float, default=0)
    ap.add_argument("--pitch", type=float, default=0)
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()

    cfg = dict(DEFAULT) if a.clear else load()

    if a.key is not None:
        cfg["api_key"] = a.key.strip()
    if a.place:
        cfg["place_query"] = a.place
    if a.place_id:
        cfg["place_id"] = a.place_id
    if a.lat is not None:
        cfg["location"]["lat"] = a.lat
    if a.lng is not None:
        cfg["location"]["lng"] = a.lng
    if a.exterior_pano:
        cfg["exterior_pano_id"] = a.exterior_pano
    if a.interior_pano:
        cfg["interior_pano_id"] = a.interior_pano
    if a.map_table and a.pano:
        cfg["table_panos"][a.map_table] = {
            "pano_id": a.pano, "heading": a.heading, "pitch": a.pitch}
        print("table %s -> pano %s" % (a.map_table, a.pano[:18] + "..."))

    save(cfg)

    if a.show or not any(vars(a).values()):
        print(json.dumps(cfg, indent=1))
    print("\nenabled: %s" % ("yes" if cfg["api_key"] else
                             "no  (no API key, the app uses generated views)"))


if __name__ == "__main__":
    main()
