#!/usr/bin/env python3
"""SUFRA Immersive Reservations - start here.

    python3 run.py            start the server on http://127.0.0.1:8010
    python3 run.py --rebuild  regenerate venue data and all artwork
    python3 run.py --reset    wipe the demo database and reseed
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

PORT = int(os.environ.get("PORT", "8013"))


def rebuild():
    from tools import venue_gen, map_gen, pano_gen, menu_gen
    venue_gen.build()
    map_gen.build()
    pano_gen.build()
    menu_gen.build()


def main():
    args = sys.argv[1:]

    if "--reset" in args:
        p = os.path.join(HERE, "sufra_v7.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(p + suffix)
            except OSError:
                pass
        print("[reset] database removed")

    if "--rebuild" in args:
        print("[rebuild] regenerating venue and artwork ...")
        rebuild()

    if not os.path.exists(os.path.join(HERE, "assets", "map", "ground.png")):
        print("[setup] artwork missing, generating it now ...")
        rebuild()

    try:
        import uvicorn
    except ImportError:
        print("Missing dependencies. Run:\n"
              "    python3 -m pip install fastapi uvicorn pillow websockets")
        sys.exit(1)

    try:
        import websockets  # noqa: F401
    except ImportError:
        print("\n  Note: the 'websockets' package is not installed, so live")
        print("  updates fall back to polling every 8 seconds. Everything")
        print("  works. To turn live updates on:")
        print("      python3 -m pip install websockets\n")

    print("\n  SUFRA Immersive Reservations  (build 12 - SUFRA 360 - port 8013)")
    print("  open  http://127.0.0.1:%d\n" % PORT)
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
