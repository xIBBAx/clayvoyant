"""Face rig: one continuous head mesh, deformed per vertex. No replacement plates, no seams.
Pure numpy so the sculpt tools and Blender share exactly the same mouth line. Head space: -y is the face, z up."""
import numpy as np

CTRL = ['jaw', 'wide', 'pucker', 'smileL', 'smileR', 'frownL', 'frownR', 'press', 'upLip', 'lowLip', 'fv',
        'browL', 'browR', 'squintL', 'squintR', 'sneerL', 'sneerR', 'jawSide', 'tongueUp', 'openL', 'openR']
IDX = {k: i for i, k in enumerate(CTRL)}
THETA = .23
HINGE = (0.0, -.02, .42)

def sm(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def zline(x, p):
    """The line where the lips meet."""
    u = x / p['W']
    return p['mz'] + p['mcurve'] * u * u - .0022 * np.exp(-(x / .03) ** 2)

def slit_h(x, p):
    """Half height of the carved parting. Closed by the 'press' control."""
    u = np.clip(np.abs(x) / p['W'], 0, 1)
    return p['mh'] * np.sqrt(np.clip(1 - u ** 4, 0, 1))

def opening(x, p):
    """How much each point along the mouth can open: full at the centre, nothing at the corners."""
    u = np.clip(np.abs(x) / p['W'], 0, 1)
    return np.clip(1 - u ** 2.2, 0, 1) ** .75

def fields(v, p):
    """-> {control: (indices, displacement)}. Every field is continuous except across the carved mouth."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    W = p['W']
    zL = zline(x, p)
    dz = z - zL
    above = dz >= 0
    s = opening(x, p)
    front = sm(.10, -.10, y)
    facing = sm(-.12, -.28, y)
    # JAW: rotates the lower face about a hinge near the ears
    # wide, soft falloff to the side: the old narrow band sheared the jaw line into a crease every time the mouth opened
    c = sm(p['mz'] + .09, p['mz'] - .06, z) * sm(.43, .13, np.abs(x)) * front
    wl = c + (1 - c) * s * np.exp(-(np.minimum(dz, 0) / .11) ** 2) * front
    wu = c * (1 - s * np.exp(-(np.maximum(dz, 0) / .05) ** 2))
    w = np.where(above, wu, wl)
    hy, hz = HINGE[1], HINGE[2]
    dy_, dz_ = y - hy, z - hz
    ct, st = np.cos(THETA), np.sin(THETA)
    D = {}
    D['jaw'] = np.c_[0 * x, w * (dy_ * ct - dz_ * st - dy_), w * (dy_ * st + dz_ * ct - dz_)]
    # corners
    ax = np.abs(x)
    uu = np.minimum(ax / W, 1) ** 1.2
    fall = np.exp(-(np.maximum(ax - W, 0) / .15) ** 2)
    cw = uu * fall * np.exp(-(dz / .11) ** 2) * facing
    sg = np.sign(x)
    D['wide'] = np.c_[sg * .042 * cw, .012 * cw, 0 * x]
    pk = np.exp(-(x / .13) ** 2 - ((z - p['mz']) / .085) ** 2) * facing
    D['pucker'] = np.c_[-sg * .042 * cw, -.036 * pk, 0 * x]
    # smiles, per side: the corner climbs and the cheek rides up under the eye
    es, ez = p['es'], p['ez']
    for nm, side in (('L', -1), ('R', 1)):
        m = (side * x > 0) * 1.0
        ck = np.exp(-((ax - .25) / .115) ** 2 - ((z - (p['mz'] + .165)) / .10) ** 2) * facing * m
        # the corner climbs in a curve: a straight line from the middle of the lip to the corner is what made a grin a V
        cs = np.minimum(ax / W, 1) ** 2.3 * fall * np.exp(-(dz / .11) ** 2) * facing
        D['smile' + nm] = np.c_[sg * .024 * cw * m, .012 * cw * m - .020 * ck, .046 * cs * m + .030 * ck]
        D['frown' + nm] = np.c_[sg * .004 * cw * m, 0 * x, -.042 * cw * m]
        br = np.exp(-((ax - es) / .14) ** 2 - ((z - (ez + .20)) / .10) ** 2) * facing * m
        D['brow' + nm] = np.c_[0 * x, -.005 * br, .032 * br]
        sq = np.exp(-((ax - es) / .13) ** 2 - ((z - (ez - .135)) / .055) ** 2) * facing * m
        D['squint' + nm] = np.c_[0 * x, -.008 * sq, .030 * sq]
        sn = np.exp(-((ax - .055) / .05) ** 2 - ((z - (p['mz'] + .12)) / .075) ** 2) * facing * m
        D['sneer' + nm] = np.c_[0 * x, 0 * x, .020 * sn]
        # the eye itself: the skin of the lids opens wide or narrows. The eyeballs sit behind carved skin, so without this a shocked
        # face and a bored face have the same eyes, and that is what reads as a game character
        r_ = p.get('eye', .1)
        u_ = (ax - es) / (r_ * 1.14 + .03)
        v_ = (z - ez) / (r_ * p.get('almond', .78) + .03)
        rho = np.sqrt(u_ * u_ + v_ * v_)
        rim = np.exp(-(np.maximum(rho - .9, 0) / 1.1) ** 2) * sm(.2, .7, rho)
        D['open' + nm] = np.c_[0 * x, 0 * x, .032 * np.tanh(1.8 * v_) * rim * facing * m]
    # lips
    ul = np.where(above, 1.0, 0.0) * s * np.exp(-(dz / .06) ** 2) * facing
    ll = np.where(above, 0.0, 1.0) * s * np.exp(-(dz / .06) ** 2) * facing
    hh = slit_h(x, p)
    pu = np.where(above, 1.0, 0.0) * np.exp(-(dz / .035) ** 2)
    pl = np.where(above, 0.0, 1.0) * np.exp(-(dz / .035) ** 2)
    D['press'] = np.c_[0 * x, .006 * (pu + pl) * s, (-pu + pl) * hh]
    D['upLip'] = np.c_[0 * x, 0 * x, .030 * ul]
    D['lowLip'] = np.c_[0 * x, 0 * x, -.030 * ll]
    D['fv'] = np.c_[0 * x, .020 * ll, .012 * ll]
    D['jawSide'] = np.c_[.028 * w, 0 * x, 0 * x]
    out = {}
    for k, d in D.items():
        idx = np.where(np.abs(d).max(1) > 2e-5)[0]
        out[k] = (idx, d[idx].astype(np.float32))
    return out
