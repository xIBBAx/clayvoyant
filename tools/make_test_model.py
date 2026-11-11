"""Make a small rigged test figure (GLB) for the model importer's tests (run inside Blender).

    blender -b --factory-startup -P tools/make_test_model.py -- tests/data/rigged_figure.glb

The figure is deliberately like a typical downloaded character: Y-up glTF, arms out in a T-pose,
bones named the way Mixamo names them ("mixamorig:LeftArm"...), a skinned mesh, and face shape keys
named the ARKit way (jawOpen, eyeBlinkLeft, eyeBlinkRight). Everything is built here from
primitives, so the file is original and MIT like the rest of the repository.
"""

import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
H = 1.8  # a life-size model (metres), as most downloads are: the importer must rescale it


def part(op, name, **kw):
    getattr(bpy.ops.mesh, op)(**kw)
    o = bpy.context.object
    o.name = name
    return o


parts = [
    part("primitive_cylinder_add", "body", radius=0.18, depth=0.62, location=(0, 0, 1.12)),
    part("primitive_cylinder_add", "hips", radius=0.17, depth=0.18, location=(0, 0, 0.78)),
    part("primitive_cylinder_add", "leg_l", radius=0.07, depth=0.78, location=(0.09, 0, 0.39)),
    part("primitive_cylinder_add", "leg_r", radius=0.07, depth=0.78, location=(-0.09, 0, 0.39)),
    part("primitive_cylinder_add", "arm_l", radius=0.05, depth=0.62, location=(0.50, 0, 1.38), rotation=(0, 1.5708, 0)),
    part("primitive_cylinder_add", "arm_r", radius=0.05, depth=0.62, location=(-0.50, 0, 1.38), rotation=(0, 1.5708, 0)),
    part("primitive_cylinder_add", "neck", radius=0.05, depth=0.12, location=(0, 0, 1.50)),
]
for o in parts:
    o.modifiers.new("subd", "SUBSURF").levels = 1
head = part("primitive_uv_sphere_add", "head", radius=0.13, location=(0, 0, 1.66), segments=24, ring_count=16)
mat = bpy.data.materials.new("figure")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.42, 0.33, 1)
for o in parts + [head]:
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True

# face shape keys, ARKit names
head.shape_key_add(name="Basis")
jaw = head.shape_key_add(name="jawOpen")
for i, v in enumerate(head.data.vertices):
    if v.co.z < -0.03 and v.co.y < 0:
        jaw.data[i].co.z -= 0.04
for side, sx in (("Left", 1), ("Right", -1)):
    k = head.shape_key_add(name=f"eyeBlink{side}")
    for i, v in enumerate(head.data.vertices):
        if v.co.y < -0.08 and 0.0 < v.co.z < 0.06 and v.co.x * sx > 0.02:
            k.data[i].co.z -= 0.012

for o in parts:
    bpy.context.view_layer.objects.active = o
    for m in o.modifiers:
        bpy.ops.object.modifier_apply(modifier=m.name)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
body = bpy.context.object

# a Mixamo-style skeleton in T-pose
bpy.ops.object.armature_add(location=(0, 0, 0))
arm = bpy.context.object
arm.name = "Armature"
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
eb.remove(eb[0])
bones = {
    "Hips": ((0, 0, 0.80), (0, 0, 0.95), None),
    "Spine": ((0, 0, 0.95), (0, 0, 1.15), "Hips"),
    "Spine1": ((0, 0, 1.15), (0, 0, 1.35), "Spine"),
    "Neck": ((0, 0, 1.45), (0, 0, 1.55), "Spine1"),
    "Head": ((0, 0, 1.55), (0, 0, 1.80), "Neck"),
    "LeftArm": ((0.20, 0, 1.38), (0.50, 0, 1.38), "Spine1"),
    "LeftForeArm": ((0.50, 0, 1.38), (0.80, 0, 1.38), "LeftArm"),
    "RightArm": ((-0.20, 0, 1.38), (-0.50, 0, 1.38), "Spine1"),
    "RightForeArm": ((-0.50, 0, 1.38), (-0.80, 0, 1.38), "RightArm"),
    "LeftUpLeg": ((0.09, 0, 0.80), (0.09, 0, 0.40), "Hips"),
    "RightUpLeg": ((-0.09, 0, 0.80), (-0.09, 0, 0.40), "Hips"),
}
for name, (h, t, parent) in bones.items():
    b = eb.new("mixamorig:" + name)
    b.head, b.tail = h, t
    if parent:
        b.parent = eb["mixamorig:" + parent]
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
arm.data.bones.active = arm.data.bones["mixamorig:Head"]
bpy.ops.object.mode_set(mode="OBJECT")
head.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.parent_set(type="BONE", keep_transform=True)  # the head follows the Head bone, in place
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_yup=True, export_skins=True,
                          export_morph=True, export_apply=False)
print("TESTMODEL written", out)
