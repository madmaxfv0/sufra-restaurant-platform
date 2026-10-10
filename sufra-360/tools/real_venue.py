"""
Point the app at a real, existing venue with a real 3D capture.

    python3 tools/real_venue.py --show
    python3 tools/real_venue.py --add-viewpoint bar --label "At the bar" \
        --pos -1.20,0.45,2.10 --rot -3.08,-0.35,-3.14
    python3 tools/real_venue.py --map-table t13 --viewpoint bar
    python3 tools/real_venue.py --venue "Some Cafe" --url https://app.kukan.ai/view/slug \
        --address "..." --kind "Restaurant"

How to get pos and rot: open the embedded tour, walk to the spot you want with
the arrow keys, then copy the pos= and rot= values out of the provider's own
share link. Those are their coordinates, so they are exact.

What this does NOT do: download, cache, re-render or modify anyone's capture.
The tour is embedded live from the provider's viewer, which is what their
embed URL is for. To own the pixels of your own room, see CAPTURE.md.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(os.path.dirname(HERE), "venue", "real_venue.json")


def load():
    return json.load(open(CFG))


def save(c):
    json.dump(c, open(CFG, "w"), indent=1)
    print("wrote %s" % CFG)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--venue")
    ap.add_argument("--url")
    ap.add_argument("--address")
    ap.add_argument("--kind")
    ap.add_argument("--add-viewpoint")
    ap.add_argument("--label")
    ap.add_argument("--pos")
    ap.add_argument("--rot")
    ap.add_argument("--map-table")
    ap.add_argument("--viewpoint")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--enable", action="store_true")
    a = ap.parse_args()

    c = load()
    if a.venue:
        c["name"] = a.venue
    if a.url:
        c["embed_base"] = a.url.split("?")[0]
    if a.address:
        c["address"] = a.address
    if a.kind:
        c["kind"] = a.kind
    if a.disable:
        c["enabled"] = False
    if a.enable:
        c["enabled"] = True

    if a.add_viewpoint:
        if not (a.pos and a.rot):
            ap.error("--add-viewpoint needs --pos and --rot")
        c["viewpoints"] = [v for v in c["viewpoints"] if v["id"] != a.add_viewpoint]
        c["viewpoints"].append({
            "id": a.add_viewpoint, "label": a.label or a.add_viewpoint,
            "pos": a.pos, "rot": a.rot, "verified": True,
            "note": "Copied from the provider's own share link."})
        print("viewpoint '%s' added" % a.add_viewpoint)

    if a.map_table:
        if not a.viewpoint:
            ap.error("--map-table needs --viewpoint")
        c.setdefault("table_viewpoints", {})[a.map_table] = a.viewpoint
        print("table %s opens at viewpoint '%s'" % (a.map_table, a.viewpoint))

    save(c)
    if a.show:
        print(json.dumps(c, indent=1))
    print("\nvenue: %s (%s)\nenabled: %s\nviewpoints: %s"
          % (c.get("name"), c.get("address"), c.get("enabled"),
             ", ".join(v["id"] for v in c.get("viewpoints", []))))


if __name__ == "__main__":
    main()
