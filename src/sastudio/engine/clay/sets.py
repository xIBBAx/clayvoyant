"""Environments: every place a scene can happen, built by code from the kit in setkit.py. Runs inside Blender.

A set is a function taking a context C and returning a Stage: where people can stand and sit (marks), where an
undirected cast goes (spots), things that can be looked at or shown in an insert (things), a door that can open, and
whether the place is outdoors. C carries the organisation's palette and short name, so a set wears the brand of
whoever is making the film, and a seed, so two films do not get the same books on the same shelf.

Layout shared by all sets: the camera looks along +y; the acting area is around the origin; the back wall or
backdrop is 6 to 9 units behind it; people face -y.
"""
import math
import random

import setkit as K

WOODS = ['#b98a5e', '#a97c52', '#c2946a', '#b0835a']


def _c(C, key, default):
    return (C.get('palette') or {}).get(key) or default


def mark(x, y, face=0.0, seat=None, **more):
    return dict(pos=(x, y), face=face, seat=seat, **more)


def stage(marks, spots, things=None, door=None, outdoor=False, windows=False, back=6.0):
    return dict(marks=marks, spots=spots, things=things or {}, door=door, outdoor=outdoor, windows=windows, back=back)


def _room(C, wallc, floor='wood', back=6.0, half=9.5, height=7.6, holes=(), side_holes=False, skirt=True):
    """Floor, back wall with openings, two side walls. Returns nothing: the room is the scene."""
    r = C.get('seed', 1)
    if floor == 'wood':
        K.planks(-half - 1, half + 1, -16, back, 26, WOODS, seed=r)
    elif floor == 'tile':
        K.tiles(-half - 1, half + 1, -16, back, 1.5, ['#e6dccb', '#d9cdb8'], seed=r)
    elif floor == 'carpet':
        K.boxy('carpet', (0, (back - 16) / 2, -.06), (half + 1, (back + 16) / 2, .06), C.get('carpet', '#5f7480'), bevel=0, lumps=.01, print_=1.2)
    elif floor == 'stone':
        K.tiles(-half - 1, half + 1, -16, back, 2.2, ['#b9b3a8', '#aea79b', '#c2bcb1'], seed=r)
    K.wall('back', -half, half, back, height, wallc, holes=holes)
    for sg in (-1, 1):
        K.side_wall('side', sg * half, -16, back, height, K.mix(wallc, '#000000', .06))
    K.ceiling(-half, half, -16, back + .2, height)
    if skirt:
        xs = sorted({-half, half, *[h[0] for h in holes if h[2] <= .01], *[h[1] for h in holes if h[2] <= .01]})
        doors = [(h[0], h[1]) for h in holes if h[2] <= .01]
        for a, b in zip(xs, xs[1:]):
            if (a, b) not in doors:
                K.skirting(a, b, back)


def _outside(C, back, kind='city'):
    """What a window looks out on: a city, or a garden."""
    if kind == 'city':
        K.skyline(y=back + 46, seed=C.get('seed', 1), zmin=2.5, zmax=9.5, lit=.3 if C.get('time') in ('evening', 'night') else 0)
        K.boxy('plaza', (0, back + 30, -.6), (80, 30, .2), '#9aa79a', bevel=0, lumps=.02)
    else:
        for i, x in enumerate((-8, -3.5, 2, 7.5)):
            K.tree(x, back + 6 + (i % 2) * 3, h=6.5, sc=1.25, seed=i + C.get('seed', 1))
        K.boxy('lawn', (0, back + 20, -.3), (60, 20, .2), '#6f9a55', bevel=0, lumps=.02)
    for i, (x, z) in enumerate(((-14, 20), (6, 24), (22, 18))):
        K.cloud(x, back + 70, z, 3.0, seed=i)


def _work_desk(x, y, C, seed=1, screen='#bcd3d6', chair_col='#2f6f73'):
    """A desk somebody works at: laptop, mug, papers, a chair behind it facing the camera."""
    d = K.desk(x, y)
    lap = K.laptop(-.25, .05, 1.53, d, rot=math.pi, screen=screen)
    K.mug(.75, -.2, 1.53, d, hex_=_c(C, 'accent', '#c1553f'))
    K.papers(-1.15, -.1, 1.53, d, seed=seed)
    K.pencil_pot(1.25, .25, 1.53, d)
    K.task_chair(x, y + 1.25, rz=0, hex_=chair_col)
    return d, lap


# ---------------------------------------------------------------------------------------------------- sets
def office(C):
    """An open office in daylight: two desks, a wall of windows over the city, a brand wall, plants, a printer."""
    pri, acc, bg = _c(C, 'primary', '#1E4E5F'), _c(C, 'accent', '#E07A3F'), _c(C, 'background', '#F4EFE6')
    back = 6.0
    holes = [(-7.4, -3.2, 1.9, 5.6), (-2.1, 2.1, 1.9, 5.6), (5.3, 7.6, 0, 4.4)]
    _room(C, K.mix(bg, '#ffffff', .2), 'wood', back, holes=holes)
    _outside(C, back, 'city')
    K.window(-5.3, 3.75, back, 2.1, 1.85, panes=(3, 2))
    K.window(0, 3.75, back, 2.1, 1.85, panes=(3, 2))
    _, leaf = K.door(6.45, back, 1.1, 4.3, hex_=K.mix(pri, '#000000', .1))
    # the brand wall: slats in the organisation's colour, its name in raised letters
    for i in range(9):
        K.boxy('slat', (9.36, -5.2 + i * .62, 3.6), (.05, .2, 3.4), K.mix(pri, '#000000', .05 * (i % 3)), bevel=.03, lumps=.006)
    K.sign(-9.32, 4.4, -1.5, (C.get('org') or 'STUDIO')[:14], .62, bg).rotation_euler = (0, 0, math.pi / 2)
    K.boxy('brandpanel', (-9.4, -1.5, 4.4), (.04, 3.4, .95), pri, bevel=.02, lumps=.006)
    d1, lap1 = _work_desk(-4.3, 2.3, C, 1)
    d2, lap2 = _work_desk(4.0, 2.6, C, 2, chair_col=acc)
    K.plant(-8.3, 4.6, 1.25, seed=2)
    K.plant(8.4, -2.2, 1.0, pot='#e9dcc3', seed=5)
    K.cabinet(2.9, 5.45, 1.0, 1.7, hex_='#e3d9c6')
    pr = K.printer(2.9, 5.4, 1.7)
    K.books(3.5, 5.4, 1.7, seed=3)
    K.bookcase(-8.9, 1.2, 1.2, 4.2, rz=math.pi / 2, seed=C.get('seed', 1))
    K.poster(9.3, 3.7, 3.4, ['THINK', 'before', 'you click'], accent=acc).rotation_euler = (0, 0, -math.pi / 2)
    K.rug(0, .4, 3.4, 2.0, hex_=K.mix(pri, '#ffffff', .25), border=bg)
    for x in (-4.5, 0, 4.5):
        K.ceiling_panel(x, .5, 7.5, e=160)
    K.pendant(-4.3, 2.3, 6.9, shade=acc, e=55, drop=1.9)
    K.pendant(4.0, 2.6, 6.9, shade=pri, e=55, drop=1.9)
    marks = dict(desk=mark(-4.3, 3.55, 0, .82, table=1.525), desk_2=mark(4.0, 3.85, 0, .82, table=1.525),
                 standing_left=mark(-1.35, .5), standing_right=mark(1.35, .5), window=mark(-.2, 4.6, .3), door=mark(6.45, 4.7))
    return stage(marks, [(-1.4, .5), (1.4, .5), (-3.5, 1.3), (3.5, 1.3), (0, 1.9)],
                 dict(laptop=lap1, laptop_2=lap2, printer=pr, phone=(-3.5, 2.2, 1.55), mug=(-3.55, 2.1, 1.6), badge=(0, .4, 2.3),
                      plant=(-8.3, 4.6, 2.2), poster=(9.3, 3.4, 3.7)), leaf, windows=True, back=back)


def reception(C):
    """A front desk: counter with the organisation's name, visitor seating, a badge reader by the door."""
    pri, acc, bg = _c(C, 'primary', '#1E4E5F'), _c(C, 'accent', '#E07A3F'), _c(C, 'background', '#F4EFE6')
    back = 6.2
    holes = [(5.0, 7.4, 0, 4.4), (-8.2, -5.0, 1.9, 5.4)]
    _room(C, K.mix(bg, '#ffffff', .15), 'tile', back, holes=holes)
    _outside(C, back, 'city')
    K.window(-6.6, 3.65, back, 1.6, 1.75, panes=(2, 2))
    _, leaf = K.door(6.2, back, 1.15, 4.3, hex_=K.mix(pri, '#000000', .1))
    K.badge_reader(4.6, 2.5, back - .05)
    K.counter(-1.2, 3.4, 3.0, 1.95, .55, hex_=K.mix(pri, '#000000', .08), top=bg)
    K.boxy('feature', (-1.2, back - .1, 4.3), (3.6, .06, 1.6), pri, bevel=.03, lumps=.008)
    K.sign(-1.2, 4.5, back - .2, (C.get('org') or 'WELCOME')[:14], .8, bg)
    K.sign(-1.2, 3.55, back - .2, 'reception', .3, K.mix(bg, pri, .35))
    mon, _ = K.monitor(-2.4, 3.5, 2.0, rot=math.pi)
    K.phone(-.3, 3.2, 2.02)
    K.books(.9, 3.35, 2.0, n=1, seed=8)      # the visitor book
    K.sofa(-6.6, 1.2, 1.5, rz=math.pi / 2, hex_=acc)
    K.table_round(-5.0, -.6, .7, .9, top='#e9dcc3')
    K.plant(8.4, 4.4, 1.3, seed=3)
    K.plant(-8.6, 4.6, 1.1, pot='#e9dcc3', seed=7)
    K.poster(2.6, 3.6, back - .06, ['VISITORS', 'sign in', 'wear a badge'], accent=acc)
    for x in (-4.5, 0, 4.5):
        K.ceiling_panel(x, .8, 7.5, e=170)
    K.pendant(-1.2, 3.0, 6.9, shade=acc, e=60, drop=1.6)
    marks = dict(counter=mark(-1.2, 4.55, 0), visitor=mark(-1.2, 1.5, math.pi), standing_left=mark(-1.35, .5),
                 standing_right=mark(1.35, .5), door=mark(6.2, 4.8))
    return stage(marks, [(-1.3, .5), (1.3, .5), (-3.0, 1.2), (3.2, 1.2)],
                 dict(badge=(4.6, back - .1, 2.5), badge_reader=(4.6, back - .1, 2.5), phone=(-.3, 3.2, 2.05), visitor_book=(.9, 3.35, 2.1),
                      plant=(8.4, 4.4, 2.2), poster=(2.6, back - .1, 3.6), monitor=mon), leaf, windows=True, back=back)


def meeting_room(C):
    """A meeting room: a long table, chairs, a wall screen, a whiteboard."""
    pri, acc, bg = _c(C, 'primary', '#1E4E5F'), _c(C, 'accent', '#E07A3F'), _c(C, 'background', '#F4EFE6')
    back = 6.0
    holes = [(6.0, 8.3, 0, 4.4)]
    _room(C, K.mix(pri, '#ffffff', .78), 'carpet', back, holes=holes)
    _, leaf = K.door(7.15, back, 1.1, 4.3, hex_='#7c5236')
    K.boxy('tabletop', (0, 2.4, 1.45), (3.4, 1.15, .08), '#a56c45', bevel=.05, lumps=.01, print_=1)
    for x in (-2.6, 2.6):
        K.boxy('tableleg', (x, 2.4, .68), (.12, .8, .68), '#3a2a22', bevel=.04, lumps=.006)
    K.task_chair(0, 4.0, 0, hex_=pri)
    K.task_chair(-4.3, 2.4, math.pi / 2, hex_=acc)
    K.task_chair(4.3, 2.4, -math.pi / 2, hex_=acc)
    scr_g = K.group('screen', (-2.6, back - .12, 4.1))
    K.slab('scrb', (0, 0, 0), (2.1, .05, 1.2), K.paint('#17191c', .35), scr_g, bevel=.03)
    scr = K.slab('display', (0, -.055, 0), (2.0, .004, 1.1), K.glowmat(K.srgb(K.mix(pri, '#ffffff', .55))[:3], 1.2), scr_g, bevel=0)
    K.whiteboard(3.2, 3.9, back - .08, 1.8, 1.05, seed=C.get('seed', 1))
    lap = K.laptop(-.9, 2.2, 1.54, rot=math.pi * .9)
    K.mug(1.4, 2.0, 1.54, hex_=acc)
    K.phone(.5, 2.6, 1.54, rot=.4)
    K.papers(2.1, 2.7, 1.54, seed=4)
    K.plant(-8.5, 4.7, 1.2, seed=4)
    K.poster(-9.3, 3.6, 1.0, ['LOCK', 'your screen', 'every time'], accent=acc).rotation_euler = (0, 0, math.pi / 2)
    for x in (-3.5, 3.5):
        K.ceiling_panel(x, 1.6, 7.5, e=170)
    K.pendant(0, 2.4, 6.9, shade=pri, e=70, drop=2.6)
    marks = dict(head_of_table=mark(0, 4.0, 0, .82, table=1.53), left_seat=mark(-4.3, 2.4, 1.1, .82, table=1.53),
                 right_seat=mark(4.3, 2.4, -1.1, .82, table=1.53),
                 screen=mark(-2.6, 4.9, .25), door=mark(7.15, 4.7))
    return stage(marks, [(-1.5, .3), (1.5, .3), (-3.4, .9), (3.4, .9)],
                 dict(laptop=lap, phone=(.5, 2.6, 1.6), mug=(1.4, 2.0, 1.65), screen=scr, poster=(-9.3, 1.0, 3.6)), leaf, back=back)



def _clock(C):
    """The hands of a wall clock: the scene's time (the job's `clock`, "HH:MM"), ten past ten when it gives none."""
    try:
        hh, mm = (int(x) for x in str(C.get('clock') or '10:10').split(':'))
    except ValueError:
        hh, mm = 10, 10
    return dict(hour=hh, minute=mm)

def home_desk(C):
    """Working from home: a desk by a garden window, a sofa, a lamp, books, a rug."""
    acc = _c(C, 'accent', '#E07A3F')
    back = 6.0
    holes = [(-6.2, -1.6, 1.8, 5.5)]
    _room(C, '#e9d9c0', 'wood', back, holes=holes)
    _outside(C, back, 'garden')
    K.window(-3.9, 3.65, back, 2.3, 1.85, panes=(2, 2), curtains='#b34d3f')
    d = K.desk(-3.9, 3.9, 1.7, .72, top='#b98a5e', drawers=False)
    lap = K.laptop(0, .0, 1.53, d, rot=0)
    K.mug(.95, -.1, 1.53, d, hex_=acc)
    K.books(-1.1, .1, 1.53, d, seed=6)
    K.chair(-3.9, 2.75, math.pi, hex_='#3f6f6a')
    K.sofa(3.9, 3.9, 2.0, hex_='#4f7c8a')
    K.floor_lamp(6.9, 4.6, e=85)
    K.bookcase(8.1, 5.6, 1.1, 4.4, seed=C.get('seed', 1) + 3)
    K.rug(1.4, .8, 3.6, 2.1, hex_='#b5553a', border='#e9d9b6')
    K.table_round(3.9, 1.7, .62, .78, top='#b98a5e', leg='#3a2a22')
    K.mug(3.7, 1.6, .85, hex_='#3f8f8c')
    K.plant(-8.3, 4.5, 1.3, pot='#e9dcc3', seed=8)
    K.plant(.3, 5.2, .8, seed=9)
    for i, (x, z) in enumerate(((1.0, 4.6), (2.3, 4.2), (1.2, 3.1))):
        K.frame(x, z, back - .06, .45 + .1 * (i % 2), .55, seed=i + C.get('seed', 1))
    K.clock(6.0, 5.6, back - .06, **_clock(C))
    router = K.group('router', (8.1, 5.3, 4.5))
    K.boxy('rb', (0, 0, 0), (.32, .2, .05), '#f3f0ea', router, bevel=.03, lumps=0)
    for i in range(3):
        K.glow('rled', (-.18 + i * .09, -.2, 0), (.012, .006, .012), (.3, 1, .45), 5, router)
    K.pendant(1.5, 1.5, 6.9, shade='#e9d9b6', e=90, drop=1.5)
    marks = dict(desk=mark(-3.9, 2.75, math.pi, .82, table=1.525), sofa=mark(3.4, 3.75, 0, .82), window=mark(-1.0, 4.3, -.4))
    return stage(marks, [(-1.2, .7), (1.5, .7), (-2.9, 1.4), (3.2, 1.3)],
                 dict(laptop=lap, phone=(3.2, 3.7, 1.0), mug=(3.7, 1.6, .95), plant=(-8.3, 4.5, 2.2), router=router), None, windows=True, back=back)


def cafe(C):
    """A cafe: round tables, a counter with a coffee machine, pendant lamps, a street window."""
    acc = _c(C, 'accent', '#E07A3F')
    back = 6.4
    holes = [(-8.0, -2.4, 1.6, 5.4), (6.2, 8.5, 0, 4.4)]
    _room(C, '#efe2c8', 'tile', back, holes=holes)
    _outside(C, back, 'city')
    K.window(-5.2, 3.5, back, 2.8, 1.9, panes=(3, 2), frame='#3f6f6a')
    _, leaf = K.door(7.35, back, 1.1, 4.3, hex_='#3f6f6a')
    K.counter(3.0, 4.6, 2.4, 1.9, .55, hex_='#3f6f6a', top='#e9dcc3')
    mach = K.group('machine', (3.9, 4.7, 1.99))
    K.boxy('mb', (0, 0, .4), (.5, .36, .4), '#c9c4b8', mach, bevel=.06, lumps=.004)
    K.boxy('mh', (0, -.2, .62), (.36, .2, .1), '#2b2d31', mach, bevel=.03, lumps=0)
    for sg in (-1, 1):
        K.cyl('spout', (sg * .16, -.3, .42), .03, .18, K.STEEL(), mach)
    for i in range(3):
        K.mug(2.0 + i * .34, 4.5, 1.99, hex_=['#f3ecdd', '#3f8f8c', acc][i])
    K.boxy('menu', (3.0, back - .08, 4.6), (1.9, .04, .9), '#2b2d31', bevel=.03, lumps=.006)
    for i, t in enumerate(('coffee  tea', 'cake  toast', 'free wifi ?')):
        K.label('menut', t, .26, '#f3ecdd', None, (3.0, back - .14, 5.05 - i * .46), ext=.006)
    wifi = K.poster(-.9, 3.7, back - .06, ['FREE WIFI', 'ask at', 'the counter'], w=.6, h=.8, accent=acc)
    for x, y in ((-3.4, 1.9), (2.7, 1.5)):
        K.table_round(x, y, .85, 1.45)
        K.chair(x - 1.35, y + .2, math.pi / 2, hex_='#c1553f')
        K.chair(x + 1.35, y + .2, -math.pi / 2, hex_='#dfa42f')
    lap = K.laptop(-3.5, 1.9, 1.52, rot=-math.pi / 2, sc=.3)
    K.mug(-3.2, 2.3, 1.52, hex_='#f3ecdd')
    K.mug(2.5, 1.7, 1.52, hex_=acc)
    K.phone(3.0, 1.3, 1.52, rot=.5)
    K.plant(-8.6, .6, 1.2, seed=11)
    for x, y in ((-3.4, 1.9), (2.7, 1.5), (3.0, 4.2)):
        K.pendant(x, y, 6.9, shade=['#c1553f', '#dfa42f', '#3f6f6a'][int(abs(x)) % 3], e=75, drop=2.5)
    marks = dict(table_left=mark(-4.75, 2.1, 1.1, .82, table=1.48), table_right=mark(4.05, 1.7, -1.1, .82, table=1.48), counter=mark(3.0, 5.65, 0),
                 door=mark(7.35, 5.0), table_left_2=mark(-2.05, 2.1, -1.1, .82, table=1.48), table_right_2=mark(1.35, 1.7, 1.1, .82, table=1.48),
                 standing_left=mark(-1.0, .2), standing_right=mark(.9, .2))
    return stage(marks, [(-.9, .1), (.9, .1), (-2.2, -.6), (4.6, .2)],
                 dict(laptop=lap, phone=(3.0, 1.3, 1.56), mug=(2.5, 1.7, 1.62), wifi_sign=wifi), leaf, windows=True, back=back)


def corridor(C):
    """A corridor: doors along one wall, a runner, wall lights, a badge reader at the far door."""
    pri, acc, bg = _c(C, 'primary', '#1E4E5F'), _c(C, 'accent', '#E07A3F'), _c(C, 'background', '#F4EFE6')
    back = 7.0
    holes = [(-1.2, 1.2, 0, 4.4)]
    _room(C, K.mix(bg, '#ffffff', .1), 'stone', back, half=6.2, holes=holes)
    _, leaf = K.door(0, back, 1.12, 4.3, hex_=K.mix(pri, '#000000', .1), hinge=1)
    K.badge_reader(1.75, 2.5, back - .05)
    K.boxy('runner', (0, -4, .015), (1.7, 11, .015), K.mix(pri, '#ffffff', .2), bevel=.01, lumps=.006)
    K.boxy('wainL', (-6.06, -4.5, 1.1), (.05, 11.5, 1.1), K.mix(pri, '#ffffff', .55), bevel=.02, lumps=.006)
    K.boxy('wainR', (6.06, -4.5, 1.1), (.05, 11.5, 1.1), K.mix(pri, '#ffffff', .55), bevel=.02, lumps=.006)
    for i, y in enumerate((3.2, -1.6, -6.4)):
        for sg in (-1, 1):
            K.glow('sconce', (sg * 5.95, y, 4.6), (.08, .2, .28), (1, .82, .55), 7)
            K.lamp((sg * 5.6, y, 4.6), 45, .5, (1, .8, .52), kind='POINT')
        K.frame(-6.0, 3.3, y - 2.2, .55, .7, seed=i + C.get('seed', 1)).rotation_euler = (0, 0, math.pi / 2)
    p = K.poster(6.0, 3.4, 1.0, ['BADGE', 'on show', 'always'], accent=acc)
    p.rotation_euler = (0, 0, -math.pi / 2)
    K.plant(-5.0, 6.0, 1.1, seed=13)
    K.plant(5.0, 6.0, 1.1, pot='#e9dcc3', seed=14)
    for y in (-4.0, 1.5):
        K.ceiling_panel(0, y, 7.5, w=.9, d=.5, e=120)
    marks = dict(left=mark(-1.6, .9), centre=mark(0, 1.6), right=mark(1.6, .9), door=mark(0, 5.6))
    return stage(marks, [(-1.25, .8), (1.25, .8), (0, 2.2), (-2.9, 1.6)],
                 dict(badge=(1.75, back - .1, 2.5), badge_reader=(1.75, back - .1, 2.5), poster=p, phone=(0, .5, 2.2)), leaf, back=back)


def street(C):
    """A city street by day: shop fronts, a pavement, a road with a parked car, a lamp post, a bench, trees."""
    acc = _c(C, 'accent', '#E07A3F')
    back = 7.5
    r = random.Random(C.get('seed', 1))
    K.tiles(-30, 30, -2.5, back, 1.6, ['#c9c2b6', '#beb7ab', '#d2ccc0'], seed=3)        # pavement
    K.boxy('kerb', (0, -2.7, -.02), (30, .22, .12), '#a8a196', bevel=.05, lumps=.01)
    K.boxy('road', (0, -11, -.2), (30, 8.2, .1), '#55585c', bevel=0, lumps=.012, print_=1.2)
    for i in range(-6, 7):
        K.boxy('lane', (i * 4.6, -9.5, -.09), (1.1, .09, .006), '#e9e3d2', bevel=0, lumps=.002)
    cols = ['#d9b38c', '#c98f6b', '#e3d3b0', '#a9b7a2', '#c9a8a0', '#d6c08f']
    x = -27.0
    i = 0
    while x < 27:
        w = r.uniform(3.4, 5.2)
        K.building(x + w, back, w, r.uniform(8.5, 13), 3.0, cols[i % len(cols)], floors=r.choice((3, 3, 4)),
                   door_x=r.uniform(-w * .4, w * .4), awning=[acc, '#3f6f6a', '#c1553f', None][i % 4], seed=i,
                   lit=.5 if C.get('time') in ('evening', 'night') else 0)
        x += 2 * w + .12
        i += 1
    K.skyline(y=back + 34, seed=C.get('seed', 1) + 5, zmin=16, zmax=40, lit=.3 if C.get('time') in ('evening', 'night') else 0)
    for i, (cx, cz) in enumerate(((-18, 30), (4, 34), (24, 28))):
        K.cloud(cx, back + 60, cz, 3.2, seed=i)
    K.street_lamp(-6.4, -1.6, e=160 if C.get('time') in ('evening', 'night') else 0)
    K.street_lamp(8.6, -1.6, e=160 if C.get('time') in ('evening', 'night') else 0)
    K.bench(4.2, 5.4)
    K.tree(-9.5, 4.9, 6.0, 1.0, seed=2)
    K.tree(11.5, 4.9, 6.4, 1.05, seed=3)
    for tx in (-9.5, 11.5):
        K.boxy('pit', (tx, 4.9, .03), (.9, .9, .03), '#5c4a3a', bevel=.03, lumps=.01)
    K.car(-9.5, -5.3, 0, hex_=acc)
    K.car(13.0, -5.3, 0, hex_='#3f6f8a', sc=.96)
    stop = K.group('busstop', (-3.4, 5.6, 0))
    K.cyl('bsp', (0, 0, 2.6), .06, 5.2, K.paint('#1f2a2c', .5, .6), stop)
    K.boxy('bss', (0, -.05, 4.7), (.5, .04, .5), _c(C, 'primary', '#1E4E5F'), stop, bevel=.06, lumps=.004)
    K.label('bst', 'BUS', .32, '#f3ecdd', stop, (0, -.11, 4.7), ext=.01)
    marks = dict(pavement_left=mark(-1.35, .9), pavement_right=mark(1.35, .9), bench=mark(4.2, 5.25, 0, .8), bus_stop=mark(-2.2, 4.6, .2),
                 shop_door=mark(.6, 6.3, 0), far_left=mark(-13, 1.5), far_right=mark(13, 1.5))
    return stage(marks, [(-1.3, .9), (1.3, .9), (-3.0, 1.7), (3.2, 1.7)],
                 dict(phone=(0, .8, 2.2), car=(-9.5, -5.3, 1.2), bus_stop=stop), None, outdoor=True, back=back)


def classroom(C):
    """A classroom: a blackboard, a teacher's desk, rows of pupils' desks, a clock, a map, tall windows."""
    acc = _c(C, 'accent', '#E07A3F')
    back = 6.2
    holes = [(6.3, 8.6, 0, 4.4)]
    _room(C, '#e8e0c9', 'wood', back, holes=holes)
    _, leaf = K.door(7.45, back, 1.1, 4.3, hex_='#3f6f6a')
    board = K.whiteboard(-1.6, 3.9, back - .08, 3.3, 1.35, board='#2f4a3d', marks=False)
    K.label('bt', 'Passwords:', .34, '#f3ecdd', board, (-1.6, -.05, .75), ext=.004)
    K.label('bt2', 'long  +  unique  +  secret', .27, '#f6e58a', board, (-.3, -.05, .1), ext=.004)
    K.tube('underline', [(-2.9, -.05, .48), (-1.6, -.055, .44), (-.4, -.05, .5)], .018, '#f3ecdd', board)
    K.clock(3.4, 5.7, back - .06, **_clock(C))
    mp = K.frame(4.4, 3.6, back - .06, .95, .7, art=('#7fb0c8', '#9fc76a', '#e9d9a0'), seed=C.get('seed', 1) + 20)
    K.desk(-4.6, 3.6, 1.5, .7, top='#b98a5e')
    K.books(-5.3, 3.5, 1.53, seed=5)
    K.mug(-3.8, 3.4, 1.53, hex_=acc)
    lap = K.laptop(-4.6, 3.65, 1.53, rot=math.pi)
    K.chair(-4.6, 4.75, 0, hex_='#3f6f6a')
    for row, y in enumerate((-2.2, -5.2)):
        for col, x in enumerate((-4.8, -1.6, 1.6, 4.8)):
            K.desk(x, y, 1.05, .55, 1.3, top='#c2946a', leg='#4a5a66', drawers=False)
            K.chair(x, y - 1.05, math.pi, .74, hex_=['#c1553f', '#dfa42f', '#3f8f8c', '#2f5d80'][(row + col) % 4], leg='#4a5a66')
            if (row + col) % 2 == 0:
                K.books(x - .3, y, 1.38, n=2, seed=row * 4 + col)
    for sg, x in ((-1, -9.38), (1, 9.38)):
        for i, y in enumerate((-6.5, -1.5, 3.2)):
            K.boxy('winband', (x, y, 4.0), (.03, 1.5, 1.6), '#cfe3ee', bevel=.01, lumps=0, rough=.2)
            K.boxy('winbar', (x - sg * .04, y, 4.0), (.04, .05, 1.6), '#f1ebdf', bevel=.01, lumps=.002)
            K.boxy('winbar', (x - sg * .04, y, 4.0), (.04, 1.5, .05), '#f1ebdf', bevel=.01, lumps=.002)
    K.plant(8.6, 4.8, 1.1, seed=21)
    for x in (-4.5, 0, 4.5):
        K.ceiling_panel(x, -.5, 7.5, e=170)
    marks = dict(teacher=mark(-1.2, 4.2, 0), board=mark(1.0, 4.9, -.3), teacher_desk=mark(-4.6, 4.75, 0, .82, table=1.525),
                 front_desk_left=mark(-1.6, -3.25, math.pi, .74, table=1.375), front_desk_right=mark(1.6, -3.25, math.pi, .74, table=1.375), door=mark(7.45, 4.8),
                 standing_left=mark(-1.35, 1.2), standing_right=mark(1.6, 1.2))
    return stage(marks, [(-1.3, 1.6), (1.5, 1.6), (-3.0, 2.2), (3.4, 2.2)],
                 dict(board=board, laptop=lap, map=mp, phone=(0, 1.2, 2.2)), leaf, back=back)


def studio(C):
    """A plain sweep of paper, for portraits and tests."""
    bg = _c(C, 'background', '#d9cbb5')
    K.slab('floor', (0, 0, -.1), (40, 40, .1), K.paint(K.mix(bg, '#6b5138', .55), .8), bevel=0)
    K.slab('backdrop', (0, 7, 10), (40, .1, 10), K.paint(bg, .85), bevel=0)
    return stage(dict(centre=mark(0, 0)), [(0, 0), (-1.6, .3), (1.6, .3), (-3.2, .8), (3.2, .8)], back=7)


SETS = dict(office=office, reception=reception, meeting_room=meeting_room, home_desk=home_desk, cafe=cafe, corridor=corridor,
            street=street, classroom=classroom, studio=studio)


def build(name, C):
    return SETS.get(name, office)(C)
