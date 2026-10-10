"""blender -b --python tools/fbx_to_glb.py -- input.fbx output.glb"""
import bpy, sys
argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src)
bpy.ops.export_scene.gltf(filepath=dst, export_format='GLB', export_animations=True, export_apply=True)
print("wrote", dst)
