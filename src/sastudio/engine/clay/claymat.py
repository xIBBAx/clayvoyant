"""Clay material kit: loads sculpted assets (npz), vertex-painted clay material, cloth and skin that behave differently."""
import bpy, math, sys, numpy as np
from mathutils import Vector as V, Matrix, Euler

def winp(p):
    return p

import os
# Optional fabric detail textures (any PBR set with Diffuse.jpg + Rough.jpg per folder). Unset = plain clay.
PHT = os.environ.get('SASTUDIO_FABRIC_DIR', '')
FAB = dict(jersey=('cotton_jersey', 2.2, .5), denim=('denim_fabric', 1.9, .8), wool=('poly_wool_herringbone', 1.5, .55), velvet=('velour_velvet', 1.2, .35), knit=('wool_boucle', 1.4, 1.0))

_mats = {}
_imgs = {}
def _img(path, data=False):
    if path in _imgs:
        return _imgs[path]
    im = bpy.data.images.load(winp(path), check_existing=True)
    if data:
        im.colorspace_settings.name = 'Non-Color'
    _imgs[path] = im
    return im

def clayv(name='clayv', rough=.52, sss=.12, print_=1.0, sheen=.12, fabric=None, coord='Object', cgrain=.05):
    k = (name, rough, sss, print_, fabric, coord)
    if k in _mats:
        return _mats[k]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree
    b = n.nodes['Principled BSDF']
    a = n.nodes.new('ShaderNodeVertexColor')
    a.layer_name = 'Col'
    tc = n.nodes.new('ShaderNodeTexCoord')
    mp = n.nodes.new('ShaderNodeMapping')
    mp.name = 'boil'
    n.links.new(tc.outputs['UV' if coord == 'UV' else 'Object'], mp.inputs[0])
    # thumb whorls broken up by smudges; fine grain from handling
    w = n.nodes.new('ShaderNodeTexWave')
    w.wave_type = 'RINGS'
    w.inputs['Scale'].default_value = 7.0
    w.inputs['Distortion'].default_value = 9
    w.inputs['Detail'].default_value = 2
    w.inputs['Detail Scale'].default_value = 2.5
    sm = n.nodes.new('ShaderNodeTexNoise')
    sm.inputs['Scale'].default_value = 5.5
    sm.inputs['Detail'].default_value = 6
    fine = n.nodes.new('ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 140
    fine.inputs['Detail'].default_value = 3
    for t in (w, sm, fine):
        n.links.new(mp.outputs[0], t.inputs['Vector'])
    rp0 = n.nodes.new('ShaderNodeValToRGB')
    rp0.color_ramp.elements[0].position = .48
    rp0.color_ramp.elements[1].position = .62
    n.links.new(sm.outputs[0], rp0.inputs[0])
    mw = n.nodes.new('ShaderNodeMath')
    mw.operation = 'MULTIPLY'
    n.links.new(w.outputs[0], mw.inputs[0])
    n.links.new(rp0.outputs[0], mw.inputs[1])
    fm = n.nodes.new('ShaderNodeMath')
    fm.operation = 'MULTIPLY'
    n.links.new(fine.outputs[0], fm.inputs[0])
    fm.inputs[1].default_value = cgrain
    add2 = n.nodes.new('ShaderNodeMath')
    add2.operation = 'MULTIPLY_ADD'
    n.links.new(sm.outputs[0], add2.inputs[0])
    add2.inputs[1].default_value = .6
    n.links.new(fm.outputs[0], add2.inputs[2])
    add = n.nodes.new('ShaderNodeMath')
    add.operation = 'MULTIPLY_ADD'
    n.links.new(mw.outputs[0], add.inputs[0])
    add.inputs[1].default_value = .06 * print_
    n.links.new(add2.outputs[0], add.inputs[2])
    bp = n.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = .5
    bp.inputs['Distance'].default_value = .03
    n.links.new(add.outputs[0], bp.inputs['Height'])
    n.links.new(bp.outputs[0], b.inputs['Normal'])
    # colour: paint times gentle hue mottling, never flat
    mott = n.nodes.new('ShaderNodeValToRGB')
    mott.color_ramp.elements[0].position = .32
    mott.color_ramp.elements[0].color = (.9, .885, .87, 1)
    mott.color_ramp.elements[1].position = .72
    mott.color_ramp.elements[1].color = (1.04, 1.035, 1.03, 1)
    n.links.new(sm.outputs[0], mott.inputs[0])
    mix = n.nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.name = 'paint'
    mix.inputs[0].default_value = 1
    n.links.new(a.outputs['Color'], mix.inputs[1])
    n.links.new(mott.outputs[0], mix.inputs[2])
    out = mix.outputs[0]
    if fabric and PHT and fabric in FAB and os.path.exists(os.path.join(PHT, FAB[fabric][0], 'Rough.jpg')):
        tex, sc, st = FAB[fabric]
        tex = os.path.join(PHT, tex) + '/'
        PHT_ = ''
        fm_ = n.nodes.new('ShaderNodeMapping')
        fm_.inputs['Scale'].default_value = (sc, sc, sc)
        n.links.new(tc.outputs['UV' if coord == 'UV' else 'Object'], fm_.inputs[0])
        hi = n.nodes.new('ShaderNodeTexImage')
        hi.image = _img(tex + 'Rough.jpg', True)
        ci = n.nodes.new('ShaderNodeTexImage')
        ci.image = _img(tex + 'Diffuse.jpg')
        for t_ in (hi, ci):
            if coord != 'UV':
                t_.projection = 'BOX'
                t_.projection_blend = .35
            n.links.new(fm_.outputs[0], t_.inputs['Vector'])
        inv = n.nodes.new('ShaderNodeMath')
        inv.operation = 'SUBTRACT'
        inv.inputs[0].default_value = 1
        n.links.new(a.outputs['Alpha'], inv.inputs[1])
        hm = n.nodes.new('ShaderNodeMath')
        hm.operation = 'MULTIPLY'
        n.links.new(hi.outputs[0], hm.inputs[0])
        n.links.new(inv.outputs[0], hm.inputs[1])
        bf = n.nodes.new('ShaderNodeBump')
        bf.inputs['Strength'].default_value = st
        bf.inputs['Distance'].default_value = .012
        n.links.new(hm.outputs[0], bf.inputs['Height'])
        n.links.new(bf.outputs[0], bp.inputs['Normal'])
        # the weave shows in the colour too, a little
        bw = n.nodes.new('ShaderNodeRGBToBW')
        n.links.new(ci.outputs[0], bw.inputs[0])
        rm_ = n.nodes.new('ShaderNodeMapRange')
        rm_.inputs['From Min'].default_value = .1
        rm_.inputs['From Max'].default_value = .7
        rm_.inputs['To Min'].default_value = .84
        rm_.inputs['To Max'].default_value = 1.08
        n.links.new(bw.outputs[0], rm_.inputs['Value'])
        mx2 = n.nodes.new('ShaderNodeMixRGB')
        mx2.blend_type = 'MULTIPLY'
        mx2.inputs[0].default_value = 1
        n.links.new(out, mx2.inputs[1])
        n.links.new(rm_.outputs[0], mx2.inputs[2])
        out = mx2.outputs[0]
    n.links.new(out, b.inputs['Base Color'])
    # alpha channel of the paint = polished metal mask (metallic accents)
    n.links.new(a.outputs['Alpha'], b.inputs['Metallic'])
    rm = n.nodes.new('ShaderNodeMapRange')
    rm.name = 'metalrough'
    rm.inputs['To Min'].default_value = rough
    rm.inputs['To Max'].default_value = .16
    n.links.new(a.outputs['Alpha'], rm.inputs['Value'])
    n.links.new(rm.outputs[0], b.inputs['Roughness'])
    if name == 'skin':
        # the inside of a mouth is dark and wet, not a grey surface catching the sky: where the paint is near black, nothing shines
        lum = n.nodes.new('ShaderNodeRGBToBW')
        n.links.new(a.outputs['Color'], lum.inputs[0])
        sp = n.nodes.new('ShaderNodeMapRange')
        sp.inputs['From Min'].default_value = .02
        sp.inputs['From Max'].default_value = .09
        sp.inputs['To Min'].default_value = 0
        sp.inputs['To Max'].default_value = .5
        n.links.new(lum.outputs[0], sp.inputs['Value'])
        n.links.new(sp.outputs[0], b.inputs['Specular IOR Level'])
    if sss > 0 and 'Subsurface Weight' in b.inputs:
        b.inputs['Subsurface Weight'].default_value = sss
        b.inputs['Subsurface Scale'].default_value = .06
    if 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = sheen
        b.inputs['Coat Roughness'].default_value = .4
    _mats[k] = m
    return m

_mesh = {}
def load(path, mat=None):
    if path in _mesh:
        return _mesh[path]
    d = np.load(path)
    v, f, c = d['v'], d['f'], d['c']
    me = bpy.data.meshes.new(path.rsplit('/', 1)[-1][:-4])
    me.vertices.add(len(v))
    me.vertices.foreach_set('co', v.ravel())
    me.loops.add(len(f) * 3)
    me.loops.foreach_set('vertex_index', f.ravel())
    me.polygons.add(len(f))
    me.polygons.foreach_set('loop_start', np.arange(len(f)) * 3)
    me.update(calc_edges=True)
    me.shade_smooth()
    ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set('color', c.ravel())
    me.materials.append(mat or clayv())
    _mesh[path] = me
    return me

def obj(name, me, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    if scale:
        o.scale = scale
    if parent:
        o.parent = parent
    return o

def gloss_eye():
    """Wet eye: vertex-painted, polished, no thumbprints, strong clear coat so it always catches a light."""
    if 'eye' in _mats:
        return _mats['eye']
    m = bpy.data.materials.new('eye')
    m.use_nodes = True
    n = m.node_tree
    b = n.nodes['Principled BSDF']
    a = n.nodes.new('ShaderNodeVertexColor')
    a.layer_name = 'Col'
    n.links.new(a.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = .22
    b.inputs['Coat Weight'].default_value = 1.0
    b.inputs['Coat Roughness'].default_value = .04
    _mats['eye'] = m
    return m

def clay_rgb(hex_, rough=.62, sss=.03, sheen=.0, fabric=None, coord='Object'):
    """Same clay, solid colour: for sleeves and trouser legs, which are swept meshes rather than painted ones."""
    k = ('rgb', hex_, rough, fabric, coord)
    if k in _mats:
        return _mats[k]
    h = hex_.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [((x + .055) / 1.055) ** 2.4 if x > .04045 else x / 12.92 for x in c]
    m = clayv('rgb_' + hex_, rough, sss, 1.0, sheen, fabric, coord).copy()
    m.name = 'rgb_' + hex_
    n = m.node_tree
    rgb = n.nodes.new('ShaderNodeRGB')
    rgb.outputs[0].default_value = (*c, 1)
    b = n.nodes['Principled BSDF']
    for l in list(n.links):
        if l.from_node.type == 'VERTEX_COLOR':
            n.links.remove(l)
    n.links.new(rgb.outputs[0], n.nodes['paint'].inputs[1])
    b.inputs['Metallic'].default_value = 0
    n.nodes['metalrough'].inputs['Value'].default_value = 0
    _mats[k] = m
    return m
