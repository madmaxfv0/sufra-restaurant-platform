# Guests and waiters go here

Rigged characters (GLB) and animation clips. The scene seats guests at every
occupied table (as many as the live feed reports), each starting its clip at a
random point and speed, and walks waiters along the venue's walk paths.

manifest.json:

{
  "characters": [
    { "file": "guest_a.glb", "height": 1.72,
      "animations": { "sit_idle": "sitting_idle.glb", "sit_talk": "sitting_talking.glb",
                      "sit_drink": "sitting_drinking.glb", "walk": "walking.glb" } },
    { "file": "guest_b.glb", "height": 1.65, "animations": { ... } }
  ]
}

Clips whose name contains "sit" are used at tables; a clip containing "walk"
is used for waiters. Put clip GLBs in static/3d/animations/humans/.

Mixamo (https://www.mixamo.com) requires an Adobe login, so this is manual:

  Characters (pick 8):  e.g. Remy, Michelle, Malcolm, Regina, Jasper, Sophie, Louise, Brian
  Animations:           Sitting Idle · Sitting Talking · Sitting Drinking · Standing Idle · Walking
  Export:               FBX Binary, "With Skin" for the character, "Without Skin" for animations

FBX -> GLB: open Blender, File > Import > FBX, File > Export > glTF 2.0 (GLB),
or run   blender -b --python tools/fbx_to_glb.py -- input.fbx output.glb
