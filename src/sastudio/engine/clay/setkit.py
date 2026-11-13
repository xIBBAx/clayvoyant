"""Set-building kit: clay forms, furniture, props and light, all made by code. Runs inside Blender.

Nothing here loads a model, a photo or a texture file, so every set can be rebuilt by anyone from the source alone.
Scale: a character stands about 3.4 units tall (one unit is roughly half a metre). The camera looks along +Y, the
floor is z = 0, actors face -Y.
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector as V

_m = {}
FONT = None      # path of a .ttf for lettering on signs and screens; set by film.py
# Every loose thing a set puts somewhere (a mug, a laptop, papers, a plant): the film rests each on the surface under it
# and keeps them out of each other (film.settle_dressing), whatever coordinates a set gave them.
PROPS = []


def _prop(g, kind):
    PROPS.append(dict(group=g, kind=kind))
    return g


def SETS_PROPS():
    """The loose things built so far that still exist (a held prop made later is not dressing)."""
    out = []
    for d in PROPS:
        try:
            d['group'].name
        except ReferenceError:
            continue
        out.append(d)
    return out


# Every place to sit a set builds. The film measures each one from its own geometry (film.measure_seats): how high the
# sitting surface really is, where its front edge, its base and its backrest are. A builder only says what it is.
SEATS = []


def _seat(g, kind, half_width, soft=0.0, cushions=()):
    """Declare the group g a seat: a sitter faces its local -y from its origin; half_width is how far to each side
    someone may sit; soft is how far its cushions give under a sitter (0 for wood); cushions can be pressed in."""
    SEATS.append(dict(group=g, kind=kind, half_width=half_width, soft=soft, cushions=list(cushions)))
    return g


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + .055) / 1.055) ** 2.4 if x > .04045 else x / 12.92 for x in c) + (1,)


def mix(a, b, t):
    a, b = a.lstrip('#'), b.lstrip('#')
    return '#%02x%02x%02x' % tuple(round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t) for i in (0, 2, 4))


# ------------------------------------------------------------------ materials
def clay(hex_, rough=.58, gloss=False, print_=.5):
    """Modelling clay: thumb-print whorls broken by smudges, fine grain from handling, colour that is never flat."""
    k = ('c', hex_, rough, gloss, print_)
    if k in _m:
        return _m[k]
    m = bpy.data.materials.new('clay_' + hex_)
    m.use_nodes = True
    n = m.node_tree
    b = n.nodes['Principled BSDF']
    tc = n.nodes.new('ShaderNodeTexCoord')
    mp = n.nodes.new('ShaderNodeMapping')
    mp.name = 'boil'
    n.links.new(tc.outputs['Object'], mp.inputs[0])
    w = n.nodes.new('ShaderNodeTexWave')
    w.wave_type = 'RINGS'
    w.inputs['Scale'].default_value = 4.0
    w.inputs['Distortion'].default_value = 8
    w.inputs['Detail'].default_value = 3
    w.inputs['Detail Scale'].default_value = 2.2
    sm = n.nodes.new('ShaderNodeTexNoise')
    sm.inputs['Scale'].default_value = 2.6
    sm.inputs['Detail'].default_value = 5
    for t in (w, sm):
        n.links.new(mp.outputs[0], t.inputs['Vector'])
    mx = n.nodes.new('ShaderNodeMath')
    mx.operation = 'MULTIPLY'
    n.links.new(w.outputs[0], mx.inputs[0])
    n.links.new(sm.outputs[0], mx.inputs[1])
    ad = n.nodes.new('ShaderNodeMath')
    ad.operation = 'MULTIPLY_ADD'
    n.links.new(mx.outputs[0], ad.inputs[0])
    ad.inputs[1].default_value = .14 * print_
    n.links.new(sm.outputs[0], ad.inputs[2])
    bp = n.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = .42
    bp.inputs['Distance'].default_value = .05
    n.links.new(ad.outputs[0], bp.inputs['Height'])
    n.links.new(bp.outputs[0], b.inputs['Normal'])
    rp = n.nodes.new('ShaderNodeValToRGB')
    rp.color_ramp.elements[0].position = .3
    rp.color_ramp.elements[1].position = .7
    c = srgb(hex_)
    rp.color_ramp.elements[0].color = tuple(x * .84 for x in c[:3]) + (1,)
    rp.color_ramp.elements[1].color = tuple(min(1, x * 1.08) for x in c[:3]) + (1,)
    n.links.new(sm.outputs[0], rp.inputs[0])
    n.links.new(rp.outputs[0], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = rough
    if gloss and 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = .6
        b.inputs['Coat Roughness'].default_value = .15
    _m[k] = m
    return m


def paint(hex_, rough=.45, metal=0.0):
    """A plain painted or metal surface: for steel, brass, enamel."""
    k = ('p', hex_, rough, metal)
    if k not in _m:
        m = bpy.data.materials.new('paint' + hex_)
        m.use_nodes = True
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Base Color'].default_value = srgb(hex_)
        b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal
        _m[k] = m
    return _m[k]


def glass(tint=(.82, .92, .92), rough=.04):
    k = ('g', tint, rough)
    if k not in _m:
        m = bpy.data.materials.new('glass')
        m.use_nodes = True
        n = m.node_tree
        b = n.nodes['Principled BSDF']
        b.inputs['Base Color'].default_value = (*tint, 1)
        b.inputs['Roughness'].default_value = rough
        b.inputs['Alpha'].default_value = .05
        b.inputs['Specular IOR Level'].default_value = .5
        _m[k] = m
    return _m[k]


def glowmat(col=(1, .8, .5), st=6):
    k = ('e', tuple(col), st)
    if k not in _m:
        m = bpy.data.materials.new('glow')
        m.use_nodes = True
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Emission Color'].default_value = (*col, 1)
        b.inputs['Emission Strength'].default_value = st
        b.inputs['Base Color'].default_value = (*col, 1)
        _m[k] = m
    return _m[k]


STEEL = lambda: paint('#1b1d21', .38, .85)
BRASS = lambda: paint('#c9a256', .28, 1.0)


# ------------------------------------------------------------------ forms
def _link(o, parent=None):
    bpy.context.scene.collection.objects.link(o)
    if parent:
        o.parent = parent
    return o


def _finish(o, mat, parent, lumps=.03, sub=2):
    o.data.materials.append(mat)
    if parent:
        o.parent = parent
    for p in o.data.polygons:
        p.use_smooth = True
    if sub:
        s = o.modifiers.new('sub', 'SUBSURF')
        s.levels = s.render_levels = sub
    if lumps:
        t = bpy.data.textures.new('lump', 'CLOUDS')
        t.noise_scale = .55
        t.noise_depth = 2
        d = o.modifiers.new('lump', 'DISPLACE')
        d.texture = t
        d.strength = lumps
        d.texture_coords = 'OBJECT'
        d.mid_level = .5
    return o


def group(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    e.rotation_euler = rot
    return _link(e, parent)


def blob(name, loc, scale, hex_, parent=None, rot=(0, 0, 0), lumps=.03, rough=.58, gloss=False, print_=.5, mat=None):
    """A ball of clay pressed to a shape."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=1)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    return _finish(o, mat or clay(hex_, rough, gloss, print_), parent, lumps, sub=1)


def boxy(name, loc, scale, hex_, parent=None, rot=(0, 0, 0), bevel=.08, lumps=.015, rough=.6, print_=.5, mat=None):
    """A slab of clay with softened edges. scale is the half size."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    for v in bm.verts:
        v.co = (v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    if bevel:
        b = o.modifiers.new('b', 'BEVEL')
        b.width = min(bevel, min(scale) * .9)
        b.segments = 3
        b.limit_method = 'NONE'
    return _finish(o, mat or clay(hex_, rough, False, print_), parent, lumps, sub=0)


def pillow(name, loc, scale, hex_, parent=None, r=.1, lumps=.02, res=.06):
    """A cushion: a rounded slab of clay with enough surface to be pressed in where someone sits (film.press_cushions).
    scale is the half size; r the roundness of its edges."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    cuts = max(4, int(round(2 * max(scale[:2]) / res)))
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    hx, hy, hz = scale
    r = min(r, hz * .95, hx * .5, hy * .5)
    inner = (hx - r, hy - r, hz - r)
    from mathutils import noise
    for v in bm.verts:
        p = (v.co.x * hx, v.co.y * hy, v.co.z * hz)
        c = [max(-i, min(i, q)) for q, i in zip(p, inner)]
        d = [q - k for q, k in zip(p, c)]
        n = math.sqrt(sum(x * x for x in d)) or 1.0
        # the lumps of handled clay are part of the shape itself, so a pressed cushion is pressed exactly where it is drawn
        bump = lumps * .5 * noise.noise(V((p[0] * 1.8 + loc[0], p[1] * 1.8 + loc[1], p[2] * 1.8)))
        v.co = [k + x / n * (r + bump) for k, x in zip(c, d)]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o['rest'] = [c for v in me.vertices for c in v.co]      # its shape before anyone sits on it
    o['half'] = list(scale)
    return _finish(o, clay(hex_, .6, False, .5), parent, 0, sub=0)


def slab(name, loc, scale, mat, parent=None, rot=(0, 0, 0), bevel=.012):
    """A hard-edged box (steel, glass, screens): no lumps, no thumb prints."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    for v in bm.verts:
        v.co = (v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    me.materials.append(mat)
    if bevel:
        b = o.modifiers.new('b', 'BEVEL')
        b.width = min(bevel, min(scale) * .9)
        b.segments = 2
        b.limit_method = 'NONE'
    if parent:
        o.parent = parent
    return o


def cyl(name, loc, r, h, mat, parent=None, rot=(0, 0, 0), seg=28, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    me.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def tube(name, pts, r, hex_, parent=None, taper=None, rough=.58, closed=False, mat=None):
    """A rolled coil of clay through points."""
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = r
    c.bevel_resolution = 4
    c.resolution_u = 10
    c.use_fill_caps = True
    s = c.splines.new('NURBS')
    s.points.add(len(pts) - 1)
    s.use_endpoint_u = not closed
    s.use_cyclic_u = closed
    s.order_u = min(3, len(pts))
    for i, p in enumerate(pts):
        s.points[i].co = (*p, 1)
        s.points[i].radius = taper[i] if taper else 1
    o = bpy.data.objects.new(name, c)
    c.materials.append(mat or clay(hex_, rough))
    return _link(o, parent)


def lathe(name, prof, hex_, parent=None, loc=(0, 0, 0), sy=1.0, lumps=.02, print_=.6, seg=24, rough=.58, mat=None):
    """One continuous turned form from a profile [(z, radius), ...]: pots, shades, mugs, trunks."""
    bm = bmesh.new()
    rings = []
    for z, r in prof:
        rings.append([bm.verts.new((r * math.cos(a * 2 * math.pi / seg), r * sy * math.sin(a * 2 * math.pi / seg), z)) for a in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            bm.faces.new((a[i], a[(i + 1) % seg], b[(i + 1) % seg], b[i]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    return _finish(o, mat or clay(hex_, rough, False, print_), parent, lumps, sub=1)


def label(name, text, size, hex_, parent=None, loc=(0, 0, 0), rot=(math.pi / 2, 0, 0), ext=.02, align='CENTER', mat=None):
    """Raised clay lettering."""
    c = bpy.data.curves.new(name, 'FONT')
    c.body = text
    c.size = size
    c.extrude = ext
    c.bevel_depth = ext * .3
    c.align_x = align
    c.align_y = 'CENTER'
    if FONT:
        try:
            c.font = bpy.data.fonts.load(FONT, check_existing=True)
        except Exception:
            pass
    o = bpy.data.objects.new(name, c)
    o.location, o.rotation_euler = loc, rot
    c.materials.append(mat or clay(hex_, print_=.3))
    return _link(o, parent)


def glow(name, loc, sc, col=(1, .8, .5), st=6, parent=None):
    return blob(name, loc, sc, '#ffffff', parent, lumps=0, mat=glowmat(col, st))


def plane(name, x0, x1, y0, y1, z, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.update()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    return _link(o)


# ------------------------------------------------------------------ light
def lamp(loc, e, sz, col, rot=(0, 0, 0), kind='AREA', shadow=None):
    d = bpy.data.lights.new('lamp', kind)
    d.energy, d.color = e, col
    if kind == 'AREA':
        d.size = sz
    elif kind == 'SPOT':
        d.spot_size, d.spot_blend, d.shadow_soft_size = sz, .6, .5
    else:
        d.shadow_soft_size = sz
    # only keys and spots cast shadows: practical lamps and fills add colour and glow, and frames render far faster
    d.use_shadow = (kind == 'SPOT' or e >= 1500) if shadow is None else shadow
    o = bpy.data.objects.new('lamp', d)
    o.location, o.rotation_euler = loc, rot
    return _link(o)


def aim(o, at):
    o.rotation_euler = (V(at) - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o


def sun(az, el, col=(1, .92, .78), e=4.0, soft=.012):
    """az 0: from behind the camera. +90: camera right. 180: from behind the set. el: above the horizon."""
    d = bpy.data.lights.new('sun', 'SUN')
    d.energy, d.color, d.angle, d.use_shadow = e, col, soft, True
    o = _link(bpy.data.objects.new('sun', d))
    a, b = math.radians(az), math.radians(el)
    src = V((math.sin(a) * math.cos(b), -math.cos(a) * math.cos(b), math.sin(b)))
    o.rotation_euler = (-src).to_track_quat('-Z', 'Y').to_euler()
    return o, src


def gobo(src, at_, dist=16, w=26, h=16, cols=5, rows=3, bar=.34, blinds=False):
    """A window we never see: its frame, standing in the sun, throws real pane shadows across the room."""
    g = group('gobo', V(at_) + src * dist)
    g.rotation_euler = (-src).to_track_quat('-Z', 'Y').to_euler()
    m = paint('#000000', .9)

    def bar_(x, y, sx, sy):
        o = slab('gob', (x, y, 0), (sx, sy, .05), m, g, bevel=0)
        o.visible_camera = False
    if blinds:
        for i in range(int(h / .62)):
            bar_(0, -h / 2 + i * .62, w * .6, .17)
        for s in (-1, 1):
            bar_(s * w * .34, 0, w * .12, h)
    else:
        for i in range(cols + 1):
            bar_(-w / 2 + i * w / cols, 0, bar, h / 2 + 2)
        for j in range(rows + 1):
            bar_(0, -h / 2 + j * h / rows, w / 2 + 2, bar)
        bar_(-w / 2 - 22, 0, 22, h + 30)     # the wall the window sits in
        bar_(w / 2 + 22, 0, 22, h + 30)
        bar_(0, h / 2 + 22, w + 40, 22)
        bar_(0, -h / 2 - 22, w + 40, 22)
    return g


def kelvin(k):
    """Colour of a lamp at k kelvin (Tanner Helland's fit), linear RGB scaled to a bright 1."""
    t = k / 100
    r = 255 if t <= 66 else 329.698727446 * (t - 60) ** -.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -.0755148492
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = [max(0, min(255, x)) / 255 for x in (r, g, b)]
    c = [x ** 2.2 for x in c]
    m = max(c)
    return tuple(x / m for x in c)


def sky(strength=1.0, top='#6fa3d8', horizon='#dfe9f2', ground='#b9a98f'):
    """A painted sky dome: horizon haze rising to blue. No photograph, so it belongs to whoever renders it."""
    w = bpy.data.worlds.new('sky')
    bpy.context.scene.world = w
    w.use_nodes = True
    n = w.node_tree
    bg = n.nodes['Background']
    tc = n.nodes.new('ShaderNodeTexCoord')
    sep = n.nodes.new('ShaderNodeSeparateXYZ')
    n.links.new(tc.outputs['Generated'], sep.inputs[0])
    rp = n.nodes.new('ShaderNodeValToRGB')
    e = rp.color_ramp.elements
    e[0].position, e[0].color = .0, srgb(ground)
    e[1].position, e[1].color = 1.0, srgb(top)
    a = e.new(.49)
    a.color = srgb(mix(ground, horizon, .7))
    b = e.new(.52)
    b.color = srgb(horizon)
    c = e.new(.68)
    c.color = srgb(mix(horizon, top, .7))
    mr = n.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -1
    mr.inputs['From Max'].default_value = 1
    n.links.new(sep.outputs['Z'], mr.inputs['Value'])
    n.links.new(mr.outputs[0], rp.inputs[0])
    n.links.new(rp.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    return w


# ------------------------------------------------------------------ furniture and props
def planks(x0, x1, y0, y1, n, hexes, z=0, seed=1):
    """A floor of real boards, each a little different."""
    r = random.Random(seed)
    dy = (y1 - y0) / n
    for i in range(n):
        boxy(f'plank{i}', ((x0 + x1) / 2, y0 + dy * (i + .5), z - .08), ((x1 - x0) / 2, dy * .485, .08 + r.random() * .012),
             hexes[i % len(hexes)], bevel=.018, lumps=.006, print_=1)


def tiles(x0, x1, y0, y1, size, hexes, z=0, seed=1, gap=.03):
    r = random.Random(seed)
    nx, ny = max(1, round((x1 - x0) / size)), max(1, round((y1 - y0) / size))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    for i in range(nx):
        for j in range(ny):
            boxy('tile', (x0 + sx * (i + .5), y0 + sy * (j + .5), z - .05), (sx / 2 - gap, sy / 2 - gap, .05 + r.random() * .006),
                 hexes[(i + j) % len(hexes)] if r.random() > .12 else r.choice(hexes), bevel=.02, lumps=.004, print_=.8)


def wall(name, x0, x1, y, z1, hex_, z0=0, thick=.12, holes=()):
    """A wall along x at depth y, with rectangular openings holes=[(xa, xb, za, zb), ...] for windows and doors."""
    xs = sorted({x0, x1, *[h[0] for h in holes], *[h[1] for h in holes]})
    for a, b in zip(xs, xs[1:]):
        zs = [(z0, z1)]
        for (ha, hb, za, zb) in holes:
            if ha <= a and b <= hb:
                zs = [(lo, hi) for lo, hi in ((z0, za), (zb, z1)) if hi - lo > .01]
        for lo, hi in zs:
            boxy(name, ((a + b) / 2, y + thick, (lo + hi) / 2), ((b - a) / 2, thick, (hi - lo) / 2), hex_, bevel=.01, lumps=.012, print_=.8)


def ceiling(x0, x1, y0, y1, z, hex_='#f4f0e8'):
    """A ceiling the camera sees and the light does not: the sun and the sky still reach the room, as on a film set
    with its lid off, and a low angle never looks out over the top of the walls."""
    m = clay(hex_, .8, False, .3).copy()
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Emission Color'].default_value = srgb(hex_)
    b.inputs['Emission Strength'].default_value = .32
    o = plane('ceiling', x0, x1, y0, y1, z, m)
    o.visible_shadow = o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
    return o


def side_wall(name, x, y0, y1, z1, hex_, thick=.12, holes=()):
    """A wall along y at x, with openings holes=[(ya, yb, za, zb), ...]: a way in from the side of a room."""
    ys = sorted({y0, y1, *[h[0] for h in holes], *[h[1] for h in holes]})
    for a, b in zip(ys, ys[1:]):
        zs = [(0.0, z1)]
        for (ha, hb, za, zb) in holes:
            if ha <= a and b <= hb:
                zs = [(lo, hi) for lo, hi in ((0.0, za), (zb, z1)) if hi - lo > .01]
        for lo, hi in zs:
            boxy(name, (x, (a + b) / 2, (lo + hi) / 2), (thick, (b - a) / 2, (hi - lo) / 2), hex_, bevel=.01, lumps=.012, print_=.8)


def skirting(x0, x1, y, hex_='#efe6d6', h=.16):
    boxy('skirt', ((x0 + x1) / 2, y - .03, h), ((x1 - x0) / 2, .035, h), hex_, bevel=.02, lumps=.004)


def window(x, z, y, w=1.6, h=1.3, frame='#f1ebdf', panes=(2, 2), sill=True, curtains=None, parent=None):
    """A window frame for an opening in a wall (the opening itself is a hole in wall()): centre x, z; half size w, h."""
    g = group('window', (x, y, z), parent)
    for X, Z, sx, sz in [(0, -h, w + .09, .08), (0, h, w + .09, .08), (-w, 0, .08, h), (w, 0, .08, h)]:
        boxy('wf', (X, 0, Z), (sx, .09, sz), frame, g, bevel=.025, lumps=.004)
    for i in range(1, panes[0]):
        boxy('wm', (-w + 2 * w * i / panes[0], 0, 0), (.035, .05, h), frame, g, bevel=.012, lumps=.002)
    for j in range(1, panes[1]):
        boxy('wm', (0, 0, -h + 2 * h * j / panes[1]), (w, .05, .035), frame, g, bevel=.012, lumps=.002)
    slab('pane', (0, .04, 0), (w, .008, h), glass(), g, bevel=0).visible_shadow = False
    if sill:
        boxy('sill', (0, -.14, -h - .07), (w + .2, .2, .05), frame, g, bevel=.02, lumps=.004)
    if curtains:
        for sg in (-1, 1):
            for k in range(4):
                tube('curtain', [(sg * (w + .12 + k * .13), -.16 - (k % 2) * .05, h + .25), (sg * (w + .15 + k * .12), -.18, 0),
                                 (sg * (w + .17 + k * .14), -.16 - (k % 2) * .06, -h - .3)], .09, curtains, g)
        tube('rail', [(-w - .8, -.17, h + .3), (0, -.17, h + .3), (w + .8, -.17, h + .3)], .03, '#3a2a22', g)
    return g


def door(x, y, w=1.05, h=4.3, hex_='#7c5236', frame='#efe6d6', hinge=-1, parent=None):
    """A door in a wall at depth y. Returns (group, leaf): turn leaf.rotation_euler.z to open it; hinge -1 left, +1 right."""
    g = group('door', (x, y, 0), parent)
    for X, Z, sx, sz in [(-w - .08, h / 2, .08, h / 2), (w + .08, h / 2, .08, h / 2), (0, h + .08, w + .16, .08)]:
        boxy('df', (X, -.02, Z), (sx, .12, sz), frame, g, bevel=.02, lumps=.004)
    leaf = group('leaf', (hinge * w, .02, 0), g)
    boxy('dl', (-hinge * w, 0, h / 2), (w - .02, .05, h / 2 - .02), hex_, leaf, bevel=.02, lumps=.008, print_=.9)
    for Z in (h * .28, h * .72):
        boxy('dp', (-hinge * w, -.05, Z), (w * .68, .015, h * .17), mix(hex_, '#000000', .12), leaf, bevel=.02, lumps=.004)
    blob('knob', (-hinge * (2 * w - .16), -.1, h * .47), (.07, .07, .07), '#000000', leaf, lumps=0, mat=BRASS())
    return g, leaf


def desk(x, y, w=1.9, d=.82, h=1.45, top='#a56c45', leg='#6e452d', rz=0, drawers=True, user=1):
    """A work desk at sitting height: drawers on the right and a modesty panel on the far side from its user, who sits
    on its +y side (user=1, facing the camera) or its -y side (user=-1, back to the camera): the knees go under it."""
    g = group('desk', (x, y, 0), rot=(0, 0, rz))
    boxy('top', (0, 0, h), (w, d, .075), top, g, bevel=.03, lumps=.01, print_=1)
    for X, Y in ((-w + .16, -d + .14), (w - .16, -d + .14), (-w + .16, d - .14), (w - .16, d - .14)):
        boxy('leg', (X, Y, (h - .07) / 2), (.085, .085, (h - .07) / 2), leg, g, bevel=.03, lumps=.005)
    boxy('modesty', (0, -user * (d - .1), h * .62), (w - .3, .03, h * .25), mix(top, '#000000', .18), g, bevel=.015, lumps=.004)
    if drawers:
        boxy('ped', (w - .62, .05, h - .5), (.42, d - .16, .4), mix(top, '#000000', .1), g, bevel=.025, lumps=.006)
        for k in range(2):
            blob('pull', (w - .62, user * (d - .08), h - .32 - k * .36), (.1, .035, .035), '#000000', g, lumps=0, mat=BRASS())
    return _prop(g, 'furniture')


def table_round(x, y, r=1.0, h=1.45, top='#e9dcc3', leg='#2b2d31'):
    g = group('table', (x, y, 0))
    lathe('ttop', [(h - .07, r * .96), (h - .03, r), (h + .03, r), (h + .06, r * .97)], top, g, lumps=.006)
    cyl('tpost', (0, 0, h / 2), .075, h - .1, paint(leg, .4, .7), g)
    lathe('tfoot', [(0, r * .62), (.06, r * .6), (.1, .12)], leg, g, lumps=0, mat=paint(leg, .4, .7))
    return _prop(g, 'furniture')


def chair(x, y, rz=0, seat=.82, hex_='#d9583f', leg='#3a2a22', back=True):
    """A plain chair. The sitter faces local -y; rz turns it (rz=pi faces +y, away from the camera)."""
    g = group('chair', (x, y, 0), rot=(0, 0, rz))
    # the seat is shallower than a thigh is long, front edge ahead of where the sitter's weight is: the knees clear it
    # and the shins hang in front of the legs instead of through them
    boxy('seat', (0, .12, seat - .07), (.52, .38, .075), hex_, g, bevel=.05, lumps=.01)
    for X, Y in ((-.42, -.18), (.42, -.18), (-.42, .4), (.42, .4)):
        boxy('cl', (X, Y, (seat - .14) / 2), (.05, .05, (seat - .14) / 2), leg, g, bevel=.02, lumps=.004)
    if back:
        for X in (-.42, .42):
            boxy('cb', (X, .44, seat + .55), (.05, .05, .62), leg, g, bevel=.02, lumps=.004)
        boxy('cbk', (0, .46, seat + .8), (.5, .06, .3), hex_, g, bevel=.05, lumps=.01)
    return _prop(_seat(g, 'chair', .3), 'furniture')


def task_chair(x, y, rz=0, seat=.82, hex_='#2f6f73'):
    """An office chair on a five-star base."""
    g = group('taskchair', (x, y, 0), rot=(0, 0, rz))
    boxy('seat', (0, .12, seat - .08), (.56, .4, .085), hex_, g, bevel=.07, lumps=.012)     # knees clear its edge
    boxy('back', (0, .5, seat + .78), (.5, .07, .52), hex_, g, bevel=.07, lumps=.012)
    slab('spine', (0, .56, seat + .28), (.06, .04, .34), STEEL(), g)
    cyl('post', (0, 0, (seat - .16) / 2 + .1), .06, seat - .3, STEEL(), g)
    for i in range(5):
        a = i * 2 * math.pi / 5 + .3
        slab('spoke', (math.sin(a) * .3, math.cos(a) * .3, .12), (.04, .32, .03), STEEL(), g, rot=(0, 0, -a))
        cyl('castor', (math.sin(a) * .6, math.cos(a) * .6, .06), .06, .08, paint('#222428', .5), g, rot=(math.pi / 2, 0, 0))
    return _prop(_seat(g, 'chair', .32), 'furniture')


def stool(x, y, seat=.82, hex_='#c9a256'):
    g = group('stool', (x, y, 0))
    lathe('st', [(seat - .1, .36), (seat - .02, .42), (seat, .4)], hex_, g, lumps=.006)
    for i in range(3):
        a = i * 2 * math.pi / 3
        tube('sl', [(math.sin(a) * .22, math.cos(a) * .22, seat - .1), (math.sin(a) * .36, math.cos(a) * .36, 0)], .04, '#3a2a22', g)
    return _prop(_seat(g, 'stool', .2), 'furniture')


def sofa(x, y, w=2.2, rz=0, hex_='#4f7c8a', seat=.82):
    """A sofa. `seat` is the top of its seat cushions, where a sitter's weight rests, as it is for every other seat;
    the cushions give a little under a sitter."""
    g = group('sofa', (x, y, 0), rot=(0, 0, rz))
    ch = .14                       # half the thickness of a seat cushion
    base = seat - 2 * ch           # the cushions rest on the base
    boxy('base', (0, 0, base / 2), (w, .78, base / 2), mix(hex_, '#000000', .15), g, bevel=.1, lumps=.02)
    n = max(1, round(w / 1.05))
    cush = []
    top = 1.96                     # the top of the backrest, as before
    for i in range(n):
        cx = -w + (2 * w) * (i + .5) / n
        cush.append(pillow('cush', (cx, -.08, seat - ch), (w / n - .04, .66, ch), hex_, g, r=.11, lumps=.022))
        hb = (top - (seat - .03)) / 2
        boxy('backc', (cx, .62, seat - .03 + hb), (w / n - .05, .2, hb), hex_, g, bevel=.14, lumps=.03, rot=(-.12, 0, 0))
    arm = 1.28                     # armrests at the height they always had
    for sg in (-1, 1):
        boxy('arm', (sg * (w + .16), -.02, arm / 2), (.2, .8, arm / 2), mix(hex_, '#000000', .08), g, bevel=.14, lumps=.025)
    return _prop(_seat(g, 'sofa', w - .25, soft=.055, cushions=cush), 'furniture')


def shelf(x, z, y, w=1.6, seed=2, board='#8a5a3a', parent=None):
    """A wall shelf with a run of books."""
    g = group('shelf', (x, y, z), parent)
    boxy('board', (0, 0, 0), (w, .24, .04), board, g, bevel=.015, lumps=.004)
    r = random.Random(seed)
    X = -w + .1
    while X < w - .25:
        wd = .05 + r.random() * .05
        H = .26 + r.random() * .16
        boxy('book', (X, 0, .04 + H), (wd, .17, H), r.choice(['#3f8f8c', '#c1553f', '#dfa42f', '#2f5d80', '#7b3045', '#e8ddc2', '#5f7f4a']),
             g, rot=(0, r.choice([0, 0, 0, .05, -.05]), 0), bevel=.012, lumps=.004)
        X += wd * 2 + .012
        if r.random() < .14:
            X += .26
    return g


def bookcase(x, y, w=1.3, h=3.6, rows=4, hex_='#7c5236', seed=4, rz=0):
    g = group('bookcase', (x, y, 0), rot=(0, 0, rz))
    boxy('bcb', (0, .2, h / 2), (w, .04, h / 2), mix(hex_, '#000000', .2), g, bevel=.01, lumps=.004)
    for sg in (-1, 1):
        boxy('bcs', (sg * w, 0, h / 2), (.05, .26, h / 2), hex_, g, bevel=.015, lumps=.004)
    for k in range(rows + 1):
        z = .08 + (h - .12) * k / rows
        if k < rows:
            shelf(0, z, 0, w - .06, seed + k, hex_, g)
        else:
            boxy('bct', (0, 0, z), (w + .04, .28, .045), hex_, g, bevel=.015, lumps=.004)
    return _prop(g, 'furniture')


def plant(x, y, sc=1.0, pot='#b5553a', leaf='#3d6b45', seed=1):
    g = group('plant', (x, y, 0))
    g.scale = (sc, sc, sc)
    r = random.Random(seed)
    lathe('pot', [(0, .3), (.62, .42), (.7, .37)], pot, g, lumps=.01)
    blob('soil', (0, 0, .64), (.34, .34, .05), '#3a2a22', g, lumps=.01)
    for i in range(8):
        a_ = i * 2.399 + r.random()
        h = 1.2 + r.random() * 1.0
        rd = .25 + r.random() * .55
        tube('leaf', [(0, 0, .62), (math.sin(a_) * rd * .4, math.cos(a_) * rd * .4, .62 + h * .55), (math.sin(a_) * rd, math.cos(a_) * rd, .62 + h)],
             .1, mix(leaf, '#9fc76a', r.random() * .35), g, taper=[.6, 1.25, .12])
    return _prop(g, 'plant')


def tree(x, y, h=6.0, sc=1.0, trunk='#6b4a35', leaf='#4f8a4c', seed=1):
    g = group('tree', (x, y, 0))
    g.scale = (sc, sc, sc)
    r = random.Random(seed)
    lathe('trunk', [(0, .34), (h * .2, .24), (h * .55, .18), (h * .62, .08)], trunk, g, lumps=.03)
    for i in range(7):
        a_ = i * 2.399
        rr = .5 + r.random() * .8
        blob('crown', (math.sin(a_) * rr, math.cos(a_) * rr, h * (.62 + r.random() * .3)), (1.0 + r.random() * .5,) * 2 + (.85 + r.random() * .4,),
             mix(leaf, '#a9c95f', r.random() * .3), g, lumps=.12)
    return g


def pendant(x, y, z, shade='#3f6f6a', e=70, drop=2.2, col=(1, .8, .52)):
    """A hanging lamp: cord, a turned shade, a bulb that really lights the set."""
    g = group('pendant', (x, y, z))
    tube('cord', [(0, 0, 0), (0, 0, drop / 2), (0, 0, drop)], .014, '#2b1d16', g)
    lathe('shade', [(-.4, .42), (-.18, .33), (0, .15), (.07, .05)], shade, g, lumps=.008)
    glow('bulb', (0, 0, -.28), (.12, .12, .12), col, 12, g)
    if e:
        lamp((x, y, z - .32), e, 1.0, col, kind='POINT')
    return g


def floor_lamp(x, y, h=3.3, shade='#e9d9b6', e=60, col=(1, .78, .5)):
    g = group('floorlamp', (x, y, 0))
    lathe('base', [(0, .32), (.05, .3), (.09, .05)], '#000000', g, lumps=0, mat=STEEL())
    cyl('pole', (0, 0, h / 2), .03, h, STEEL(), g)
    lathe('shade', [(h - .5, .46), (h + .05, .3), (h + .08, .28)], shade, g, lumps=.006)
    glow('bulb', (0, 0, h - .3), (.11, .11, .14), col, 9, g)
    if e:
        lamp((x, y, h - .3), e, .8, col, kind='POINT')
    return g


def ceiling_panel(x, y, z, w=1.4, d=.5, e=120, col=(1, .96, .9)):
    """A lit ceiling panel: the light an office actually has."""
    slab('panel', (x, y, z), (w, d, .03), glowmat(col, 3.0), bevel=.01)
    if e:
        lamp((x, y, z - .08), e, 1.6, col, (0, 0, 0), 'AREA', shadow=False)


def laptop(x, y, z, parent=None, rot=0, sc=.36, screen='#bcd3d6', open_=1.0):
    lap = group('laptop', (x, y, z), parent, rot=(0, 0, rot))
    lap.scale = (sc, sc, sc)
    boxy('base', (0, 0, .04), (1.32, .86, .045), '#b8b4ab', lap, bevel=.025, lumps=.002)
    for row in range(4):
        for k in range(10):
            boxy('key', (-1.0 + k * .222, -.42 + row * .2, .092), (.082, .072, .018), '#55535c', lap, bevel=.01, lumps=0)
    boxy('pad', (0, -.68, .088), (.34, .15, .004), '#a8a49b', lap, bevel=.002, lumps=0)
    scr = group('lid', (0, .84, .05), lap, rot=(-.16 - (1 - open_) * 1.4, 0, 0))
    boxy('lidb', (0, 0, .92), (1.38, .035, .92), '#48474e', scr, bevel=.025, lumps=.003)
    slab('display', (0, -.04, .92), (1.28, .004, .85), glowmat(srgb(screen)[:3], .9), scr, bevel=0)
    return _prop(lap, 'laptop')


def monitor(x, y, z, parent=None, rot=0, w=.62, h=.38, screen='#bcd3d6'):
    g = group('monitor', (x, y, z), parent, rot=(0, 0, rot))
    slab('mb', (0, 0, h + .22), (w, .03, h), paint('#202226', .4), g, bevel=.02)
    scr = slab('display', (0, -.032, h + .22), (w - .04, .004, h - .04), glowmat(srgb(screen)[:3], .9), g, bevel=0)
    cyl('ms', (0, .03, .12), .035, .24, STEEL(), g)
    lathe('mf', [(0, .24), (.025, .22), (.04, .05)], '#000000', g, lumps=0, mat=STEEL())
    return _prop(g, 'monitor'), scr


def phone(x, y, z, parent=None, rot=0, hex_='#1f2329', screen='#8fd0c8'):
    g = group('phone', (x, y, z), parent, rot=(0, 0, rot))
    boxy('pb', (0, 0, .015), (.075, .15, .015), hex_, g, bevel=.012, lumps=0)
    slab('display', (0, 0, .032), (.064, .135, .002), glowmat(srgb(screen)[:3], .7), g, bevel=0)
    return _prop(g, 'phone') if parent is None or not parent.name.endswith(('_palmL', '_palmR')) else g


def mug(x, y, z, parent=None, hex_='#c1553f', steam=False):
    g = group('mug', (x, y, z), parent)
    lathe('mb', [(0, .085), (.012, .1), (.2, .105), (.21, .095), (.2, .085), (.03, .08)], hex_, g, lumps=.003)
    tube('mh', [(.1, 0, .16), (.17, 0, .15), (.18, 0, .08), (.1, 0, .05)], .018, hex_, g)
    blob('coffee', (0, 0, .175), (.085, .085, .01), '#3b2416', g, lumps=0, gloss=True)
    return _prop(g, 'mug') if parent is None or not parent.name.endswith(('_palmL', '_palmR')) else g


def papers(x, y, z, parent=None, n=5, seed=5):
    """A loose stack of papers: one thing, each sheet resting on the one below."""
    r = random.Random(seed)
    g = group('papers', (x, y, z), parent)
    for i in range(n):
        boxy('paper', (r.uniform(-.12, .12), r.uniform(-.08, .08), .004 + i * .0085), (.2, .28, .004),
             r.choice(['#f7f2e4', '#efe6cf', '#f4e7c8']), g, rot=(0, 0, r.uniform(-.5, .5)), bevel=.003, lumps=.002)
    return _prop(g, 'papers')


def books(x, y, z, parent=None, n=3, seed=3):
    """A pile of books lying flat: one thing, each book resting on the one below."""
    r = random.Random(seed)
    g = group('books', (x, y, z), parent)
    for i in range(n):
        boxy('bookflat', (r.uniform(-.03, .03), 0, .04 + i * .085), (.26 - i * .02, .19, .04),
             r.choice(['#3f8f8c', '#c1553f', '#dfa42f', '#2f5d80', '#7b3045']), g, rot=(0, 0, r.uniform(-.25, .25)), bevel=.012, lumps=.003)
    return _prop(g, 'books')


def pencil_pot(x, y, z, parent=None):
    g = group('pencils', (x, y, z), parent)
    lathe('pot', [(0, .08), (.2, .09), (.21, .08)], '#3f8f8c', g, lumps=.004)
    for a, c in ((.2, '#eab531'), (-.25, '#c73a46'), (.05, '#2f5d80')):
        tube('pencil', [(0, 0, .05), (math.sin(a) * .07, 0, .25), (math.sin(a) * .12, 0, .42)], .012, c, g)
    return _prop(g, 'pencils')


def frame(x, z, y, w=.6, h=.8, art=('#e9b44c', '#3f8f8c', '#c1553f'), border='#3a2a22', seed=1, parent=None):
    """A framed picture, painted by code: bold shapes on a ground, different for every seed."""
    g = group('frame', (x, y, z), parent)
    r = random.Random(seed)
    boxy('fr', (0, 0, 0), (w + .06, .03, h + .06), border, g, bevel=.012, lumps=.002)
    boxy('mount', (0, -.025, 0), (w, .012, h), '#f3ecdd', g, bevel=.004, lumps=.001)
    for i in range(4 + r.randrange(3)):
        cw, ch = w * (.2 + r.random() * .4), h * (.12 + r.random() * .35)
        cx, cz = r.uniform(-w * .7 + cw * .5, w * .7 - cw * .5), r.uniform(-h * .7 + ch * .5, h * .7 - ch * .5)
        if r.random() < .5:
            boxy('art', (cx, -.036 - i * .002, cz), (cw / 2, .004, ch / 2), r.choice(art), g, bevel=.004, lumps=.001, rot=(0, r.uniform(-.3, .3), 0))
        else:
            blob('art', (cx, -.036 - i * .002, cz), (min(cw, ch) / 2, .006, min(cw, ch) / 2), r.choice(art), g, lumps=0)
    return g


def poster(x, z, y, lines, w=.62, h=.86, paper='#f4e7c8', ink='#2b1d16', accent='#c1553f', parent=None):
    """A printed poster: a band of colour and a few words, big enough to read across the room."""
    g = group('poster', (x, y, z), parent)
    boxy('pf', (0, 0, 0), (w + .03, .02, h + .03), '#3a2a22', g, bevel=.01, lumps=.002)
    boxy('pp', (0, -.02, 0), (w, .008, h), paper, g, bevel=.004, lumps=.001)
    boxy('band', (0, -.027, h * .62), (w, .004, h * .26), accent, g, bevel=.002, lumps=0)
    n = len(lines)
    for i, t in enumerate(lines):
        size = min(.2, 1.7 * w / max(4, len(t)))
        label('pt', t, size, paper if i == 0 else ink, g, (0, -.034, h * .62 if i == 0 else h * .18 - (i - 1) * size * 1.25), ext=.004)
    return g


def sign(x, z, y, text, size=.42, hex_='#2b2d31', plate=None, parent=None, ext=.03):
    """Raised lettering on a wall, with an optional plate behind it."""
    g = group('sign', (x, y, z), parent)
    if plate:
        boxy('plate', (0, .02, 0), (len(text) * size * .33 + .25, .03, size * .9), plate, g, bevel=.03, lumps=.004)
    label('st', text, size, hex_, g, (0, -.03, 0), ext=ext)
    return g


def clock(x, z, y, r=.36, hour=10, minute=10, parent=None):
    g = group('clock', (x, y, z), parent)
    lathe('face', [(0, r), (.03, r * 1.04), (.05, r)], '#f3ecdd', g, lumps=0).rotation_euler = (math.pi / 2, 0, 0)
    for i in range(12):
        a = i * math.pi / 6
        boxy('tick', (math.sin(a) * r * .82, -.06, math.cos(a) * r * .82), (.012, .005, .04), '#2b1d16', g, rot=(0, a, 0), bevel=.002, lumps=0)
    for ang, ln, wd in ((2 * math.pi * (hour % 12 + minute / 60) / 12, r * .48, .022), (2 * math.pi * minute / 60, r * .72, .015)):
        boxy('hand', (math.sin(ang) * ln / 2, -.075, math.cos(ang) * ln / 2), (wd, .006, ln / 2), '#2b1d16', g, rot=(0, ang, 0), bevel=.004, lumps=0)
    return g


def rug(x, y, w=2.6, d=1.6, hex_='#b5553a', border='#e9d9b6'):
    boxy('rugb', (x, y, .012), (w, d, .012), border, bevel=.01, lumps=.006)
    boxy('rug', (x, y, .02), (w - .14, d - .14, .012), hex_, bevel=.01, lumps=.006)


def cabinet(x, y, w=.9, h=1.5, d=.42, hex_='#e3d9c6', rz=0, drawers=3):
    g = group('cabinet', (x, y, 0), rot=(0, 0, rz))
    boxy('cb', (0, 0, h / 2), (w, d, h / 2), hex_, g, bevel=.03, lumps=.006)
    for k in range(drawers):
        z = h * (k + .5) / drawers
        boxy('cd', (0, -d - .005, z), (w - .07, .02, h / drawers / 2 - .04), mix(hex_, '#ffffff', .25), g, bevel=.015, lumps=.003)
        blob('ck', (0, -d - .04, z), (.12, .03, .03), '#000000', g, lumps=0, mat=BRASS())
    return _prop(g, 'furniture')


def printer(x, y, z, parent=None):
    g = group('printer', (x, y, z), parent)
    boxy('pr', (0, 0, .22), (.5, .42, .22), '#dcd7cc', g, bevel=.05, lumps=.004)
    boxy('prt', (0, -.1, .46), (.42, .26, .02), '#55535c', g, bevel=.01, lumps=0)
    boxy('tray', (0, -.5, .1), (.36, .16, .012), '#c9c4b8', g, bevel=.008, lumps=0)
    boxy('sheet', (0, -.5, .12), (.3, .14, .006), '#f7f2e4', g, bevel=.003, lumps=0)
    glow('led', (.36, -.425, .3), (.02, .01, .02), (.3, 1, .4), 4, g)
    return _prop(g, 'printer')


def counter(x, y, w=2.4, h=1.85, d=.5, hex_='#7c5236', top='#e9dcc3'):
    g = group('counter', (x, y, 0))
    boxy('cbody', (0, 0, h / 2), (w, d, h / 2), hex_, g, bevel=.04, lumps=.01, print_=.9)
    boxy('ctop', (0, -.04, h + .04), (w + .08, d + .1, .05), top, g, bevel=.03, lumps=.006)
    for i in range(max(2, round(w / .5))):
        boxy('cpanel', (-w + .3 + i * (2 * w - .6) / max(1, round(w / .5) - 1), -d - .005, h * .5), (.2, .012, h * .38), mix(hex_, '#000000', .12), g, bevel=.02, lumps=.004)
    return _prop(g, 'furniture')


def whiteboard(x, z, y, w=1.9, h=1.05, parent=None, board='#f6f4ee', marks=True, seed=1):
    g = group('board', (x, y, z), parent)
    boxy('wbf', (0, 0, 0), (w + .05, .03, h + .05), '#c9c4b8', g, bevel=.012, lumps=.002)
    boxy('wb', (0, -.032, 0), (w, .012, h), board, g, bevel=.004, lumps=0, rough=.25)
    boxy('tray', (0, -.08, -h - .03), (w * .6, .06, .02), '#c9c4b8', g, bevel=.008, lumps=0)
    if marks:
        r = random.Random(seed)
        for i in range(4):
            z0 = h * .55 - i * h * .34
            tube('mark', [(-w * .8, -.035, z0), (-w * .8 + r.uniform(.4, 1.2) * w, -.035, z0 + r.uniform(-.03, .03))], .014,
                 r.choice(['#2f5d80', '#c1553f', '#2b1d16', '#3f8f6a']), g)
    return g


def badge_reader(x, z, y, parent=None):
    g = group('reader', (x, y, z), parent)
    boxy('rb', (0, 0, 0), (.13, .035, .19), '#2b2d31', g, bevel=.03, lumps=0)
    glow('rl', (0, -.04, .11), (.03, .008, .012), (.25, 1, .45), 5, g)
    return g


def car(x, y, rz=0, hex_='#c9422f', sc=1.0):
    """A clay car: body, cabin, glass, wheels, lights."""
    g = group('car', (x, y, 0), rot=(0, 0, rz))
    g.scale = (sc, sc, sc)
    boxy('body', (0, 0, .78), (2.9, 1.2, .46), hex_, g, bevel=.3, lumps=.02)
    boxy('cabin', (-.25, 0, 1.52), (1.55, 1.05, .42), hex_, g, bevel=.3, lumps=.02)
    slab('glassS', (-.25, 0, 1.55), (1.42, 1.07, .3), glass((.55, .68, .72), .03), g, bevel=.1)
    for X in (-1.75, 1.75):
        for sg in (-1, 1):
            cyl('wheel', (X, sg * 1.13, .5), .5, .3, paint('#1c1c1e', .7), g, rot=(math.pi / 2, 0, 0))
            cyl('hub', (X, sg * 1.29, .5), .24, .04, paint('#c9c9c9', .3, .8), g, rot=(math.pi / 2, 0, 0))
    for sg in (-1, 1):
        glow('headlight', (2.9, sg * .78, .86), (.05, .2, .12), (1, .95, .8), 3, g)
        glow('tail', (-2.9, sg * .82, .9), (.05, .18, .08), (1, .12, .08), 2, g)
    return g


def street_lamp(x, y, h=6.2, e=180, col=(1, .78, .5)):
    g = group('streetlamp', (x, y, 0))
    lathe('slb', [(0, .22), (.5, .16), (.6, .09)], '#000000', g, lumps=0, mat=paint('#1f2a2c', .5, .6))
    cyl('slp', (0, 0, h / 2), .07, h, paint('#1f2a2c', .5, .6), g)
    tube('sla', [(0, 0, h), (0, -.5, h + .35), (0, -1.0, h + .2)], .05, '#1f2a2c', g, mat=paint('#1f2a2c', .5, .6))
    glow('sll', (0, -1.0, h + .05), (.2, .26, .12), col, 10, g)
    if e:
        lamp((x, y - 1.0, h - .1), e, .6, col, kind='POINT')
    return g


def bench(x, y, rz=0, hex_='#7c5236'):
    g = group('bench', (x, y, 0), rot=(0, 0, rz))
    for i in range(4):
        boxy('slat', (0, -.3 + i * .2, .8), (1.5, .085, .035), hex_, g, bevel=.02, lumps=.006)
    for i in range(3):
        boxy('bslat', (0, .42, 1.05 + i * .22), (1.5, .035, .085), hex_, g, bevel=.02, lumps=.006, rot=(-.12, 0, 0))
    for sg in (-1, 1):
        slab('bleg', (sg * 1.3, 0, .39), (.05, .4, .39), paint('#1f2a2c', .5, .6), g)
        slab('bback', (sg * 1.3, .43, 1.1), (.05, .05, .5), paint('#1f2a2c', .5, .6), g, rot=(-.12, 0, 0))
    return _prop(_seat(g, 'bench', 1.25), 'furniture')


def building(x, y, w=4.0, h=9.0, d=3.0, hex_='#d9b38c', floors=3, door_x=None, awning=None, seed=1, lit=.0, name=None):
    """A street frontage facing -y: storeys of windows, a cornice, an optional shop door and awning."""
    r = random.Random(seed)
    g = group('building', (x, y, 0))
    boxy('bw', (0, d, h / 2), (w, d, h / 2), hex_, g, bevel=.04, lumps=.02, print_=.9)
    boxy('cornice', (0, -.08, h + .1), (w + .14, .2, .14), mix(hex_, '#ffffff', .35), g, bevel=.05, lumps=.01)
    fh = h / floors
    cols = max(2, round(w / 1.1))
    for fl in range(floors):
        for i in range(cols):
            cx = -w + (2 * w) * (i + .5) / cols
            cz = fh * (fl + .55)
            if fl == 0 and door_x is not None and abs(cx - door_x) < 2 * w / cols * .6:
                continue
            on = r.random() < lit
            pane = glowmat((1, .82, .5), 1.6) if on else paint(mix('#2c3e4f', '#8fb3c9', r.random() * .5), .12)
            slab('bwin', (cx, -.03, cz), (w / cols * .56, .03, fh * .27), pane, g, bevel=.01)
            boxy('bsill', (cx, -.09, cz - fh * .3), (w / cols * .64, .08, .04), mix(hex_, '#ffffff', .35), g, bevel=.02, lumps=.004)
    if door_x is not None:
        boxy('sdoor', (door_x, -.03, fh * .43), (.62, .05, fh * .43), mix(hex_, '#000000', .45), g, bevel=.03, lumps=.006)
        slab('sdoorg', (door_x, -.07, fh * .52), (.44, .02, fh * .26), paint('#8fb3c9', .12), g, bevel=.01)
    if awning:
        for i in range(8):
            boxy('awn', (-w * .8 + i * w * 1.6 / 7, -.7, fh * .93), (w * .115, .75, .03), awning if i % 2 == 0 else '#f3ecdd', g, rot=(-.35, 0, 0), bevel=.01, lumps=.006)
    if name:
        label('bname', name, .5, '#f3ecdd', g, (0, -.2, fh * 1.08), ext=.03)
    return g


def skyline(y=60, x0=-70, x1=70, seed=3, base='#7f96b0', lit=.25, zmin=8, zmax=34):
    """Distant towers behind a window or a street: three depths of haze, a few lit windows, real parallax."""
    r = random.Random(seed)
    for depth in range(3):
        x = x0
        col = mix(base, '#dfe9f2', depth * .28)
        while x < x1:
            w = r.uniform(3, 8)
            h = r.uniform(zmin, zmax) * (1 - depth * .12)
            slab('tower', (x + w / 2, y + depth * 22, h / 2), (w / 2, 3, h / 2), paint(col, .7), bevel=0)
            if depth == 0 and lit:
                for _ in range(int(h * w * lit * .2)):
                    slab('twin', (x + r.uniform(.4, w - .4), y - 3.05, r.uniform(1, h - .6)), (.22, .02, .3), glowmat((1, .85, .6), 1.2), bevel=0)
            x += w + r.uniform(.3, 3)


def cloud(x, y, z, sc=1.0, seed=1):
    r = random.Random(seed)
    g = group('cloud', (x, y, z))
    for i in range(5):
        blob('cl', ((i - 2) * 1.1 * sc, r.uniform(-.3, .3), r.uniform(-.2, .35) * sc), (1.3 * sc * r.uniform(.7, 1.1), .7 * sc, .8 * sc * r.uniform(.7, 1.1)),
             '#ffffff', g, lumps=.1, rough=.9, mat=clay('#fbf7ef', .9, False, .2))
    return g


# ------------------------------------------------------------------ dressing that moves (direction.dressing)
def _vapour():
    """Soft vapour for Cycles: white, fully rough, its opacity falling off towards each puff's silhouette (no hard
    rim, no glass bubble) and scaled by the object's own alpha, which the animator sets as a puff rises and thins."""
    m = bpy.data.materials.get('vapour')
    if m:
        return m
    m = bpy.data.materials.new('vapour')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (1, 1, 1, 1)
    b.inputs['Roughness'].default_value = 1.0
    lw = nt.nodes.new('ShaderNodeLayerWeight')
    lw.inputs['Blend'].default_value = .5
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation, inv.inputs[0].default_value = 'SUBTRACT', 1.0
    nt.links.new(lw.outputs['Facing'], inv.inputs[1])
    pw = nt.nodes.new('ShaderNodeMath')
    pw.operation, pw.inputs[1].default_value = 'POWER', 2.2
    nt.links.new(inv.outputs[0], pw.inputs[0])
    oi = nt.nodes.new('ShaderNodeObjectInfo')
    mu = nt.nodes.new('ShaderNodeMath')
    mu.operation = 'MULTIPLY'
    nt.links.new(pw.outputs[0], mu.inputs[0])
    nt.links.new(oi.outputs['Alpha'], mu.inputs[1])
    mk = nt.nodes.new('ShaderNodeMath')
    mk.operation, mk.inputs[1].default_value = 'MULTIPLY', .16
    nt.links.new(mu.outputs[0], mk.inputs[0])
    nt.links.new(mk.outputs[0], b.inputs['Alpha'])
    return m


def steam(loc, n=14, seed=8):
    """Vapour off a hot drink: puffs that leave the surface small, swell, drift and thin out as they rise, each on
    its own clock. Returns the per-frame animator."""
    r = random.Random(seed)
    mat = _vapour()
    puffs = []
    for i in range(n):
        o = blob('steam', (0, 0, -50), (.1, .1, .1), '#ffffff', None, lumps=.01, mat=mat)
        o.visible_shadow = False
        puffs.append((o, (i + r.uniform(0, .6)) / n, r.uniform(-.6, .6), r.uniform(.8, 1.2)))
    x, y, z = loc

    def anim(f):
        for o, ph, dx, sp in puffs:
            t = (f / 60.0 * sp + ph) % 1.0
            o.location = (x + dx * .14 * t + .035 * math.sin(f / 9 + ph * 7), y + .04 * math.sin(f / 13 + ph * 5), z + .05 + .8 * t)
            sc = .025 + .11 * t
            o.scale = (sc, sc, sc * 1.4)
            o.color = (1, 1, 1, math.sin(math.pi * t) ** 1.5 * (1 - .5 * t))
    return anim


def birds(back, outdoor=False, n=4, seed=2):
    """A few birds crossing the sky outside: seen through the windows of a room, or over a street. Wings beat, each
    bird on its own line, height and speed. Returns the per-frame animator."""
    r = random.Random(seed)
    y, z = (back + 26, 11.0) if outdoor else (back + 14, 6.2)
    x0, x1 = -34, 34
    flock = []
    for i in range(n):
        g = group('bird', (0, y, z))
        wl = tube('wing', [(-.55, 0, .14), (-.22, 0, 0), (0, 0, -.04)], .045, '#2b2b30', g)
        wr = tube('wing', [(.55, 0, .14), (.22, 0, 0), (0, 0, -.04)], .045, '#2b2b30', g)
        flock.append((g, wl, wr, r.uniform(0, 1), r.uniform(.6, 1.1), r.uniform(-1.2, 1.4)))

    def anim(f):
        for g, wl, wr, ph, sp, dz in flock:
            t = (f * .0016 * sp + ph) % 1.0
            g.location = (x0 + (x1 - x0) * t, y + 2.5 * math.sin(t * 6), z + dz + .4 * math.sin(f / 30 + ph * 6))
            flap = .5 * math.sin(f / 2.2 + ph * 20)
            wl.rotation_euler = (0, flap, 0)
            wr.rotation_euler = (0, -flap, 0)
    return anim
