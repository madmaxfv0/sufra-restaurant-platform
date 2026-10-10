"""Draco-compress and 1K-resize every model under static/3d/models (needs Node + @gltf-transform/cli:
   npm install -g @gltf-transform/cli   then   python3 tools/optimise_models.py)"""
import os, subprocess, sys
root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "3d", "models")
for dp, _, fs in os.walk(root):
    for f in fs:
        if f.endswith((".glb", ".gltf")):
            p = os.path.join(dp, f); tmp = p + ".tmp.glb"
            if subprocess.call(["gltf-transform", "resize", p, tmp, "--width", "1024", "--height", "1024"]) == 0 and \
               subprocess.call(["gltf-transform", "draco", tmp, p]) == 0:
                print("optimised", p)
            if os.path.exists(tmp): os.remove(tmp)
