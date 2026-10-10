# Real trees go here

Drop CC0 tree models (GLB/glTF) into this folder and describe them in
`manifest.json`. The scene loads them, instances them at every tree position
in the venue with size variation, and applies hierarchical wind to any
material whose name contains leaf / leaves / foliage / needle / canopy / frond
(or that uses alpha). Trunks stay still, branch tips and leaves move.

manifest.json:

{
  "trees": [
    { "file": "tree_a.glb", "height": 8.0 },
    { "file": "tree_b.glb", "height": 6.5 },
    { "file": "shrub_a.glb", "height": 1.4 }
  ]
}

Where to get them (blocked from the build machine, so this step is manual):

  https://polyhaven.com/models?c=nature   ->  any tree; download glTF, 1K or 2K
  https://polyhaven.com/a/<slug>          ->  "Download" -> glTF

Recommended: two deciduous species of different canopy shape, one shrub.
Run  python3 tools/optimise_models.py  afterwards to Draco-compress them.
