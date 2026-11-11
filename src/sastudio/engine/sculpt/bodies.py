"""Clothing, hands, shoes, hair and accessories. Torso origin: hip pivot, z up, face -y. Neck pivot at z=L+.16."""
import os, sys
import numpy as np
from sdfkit import *
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clay'))  # shared with the Blender side
import handrig as hr

CL = Field(23, sigma=8)

def base_torso(P, c):
    sw, cw, ww, hw, dp, L = c['sw'], c['cw'], c['ww'], c['hw'], c['dp'], c['L']
    pelvis = ell(P, (0, .0, .03), (hw, hw * dp, .22))
    waist = ell(P, (0, .0, .40), (ww, ww * dp, .25))
    chest = ell(P, (0, -.012, c.get('chz', .74)), (cw, cw * dp, c.get('chr', .34)))
    sh = cone(P, (-sw + .11, .012, L - .05), (sw - .11, .012, L - .05), .105)
    d = U(pelvis, waist, k=.11)
    d = smin(d, chest, .12)
    d = smin(d, sh, .10)
    bu = c.get('bust', 0)
    if bu:
        # a woman's chest under her jacket: soft, modest, part of the silhouette rather than a feature
        for s_ in (-1, 1):
            d = smin(d, ell(P, (s_ * .1, -(cw * dp) * .62, c.get('chz', .74) - .05), (.105, .085 * bu, .09)), .07)
    return d

def hem(d, P, z0=0.0, t=.014):
    """The garment ends at z0 and stands a little proud of what is under it: the join is a shadow line, not a paint edge."""
    return smin(d, smax(d - t, z0 - P[2], .008), .004)

def neck(P, c):
    L = c['L']
    # up into the skull behind the throat: since the heads came down to real size, a neck that rose straight poked through the back of the mouth
    return cone(P, (0, .03, L - .02), (0, .125, L + .36), c.get('nk', .125), c.get('nk', .125) * .70)

def folds(P, amp=.006, z0=.38, zw=.22, seed=0):
    m = np.exp(-((P[2] - z0) / zw) ** 2)
    return amp * m * (np.sin(P[2] * 34 + P[0] * 9 + seed) + .6 * np.sin(P[2] * 52 - P[0] * 14 + seed * 2))

def V_zone(P, apex, slope):
    return np.maximum(np.abs(P[0]) - (P[2] - apex) * slope, apex - P[2])

def collar(P, L, col_y=-.20, spread=.13, r=.028):
    return U(path(P, [(-spread, col_y + .05, L + .09), (-.03, col_y - .09, L - .03)], r, r * .7),
             path(P, [(spread, col_y + .05, L + .09), (.03, col_y - .09, L - .03)], r, r * .7), k=.006)

# ---------- torsos ----------
def knit_vest(c):
    L, sw = c['L'], c['sw']
    def vzone(P):
        return np.maximum(np.maximum(-V_zone(P, .66, .36), -ell(P, (sw, 0, L - .12), (.17, .34, .25))), -ell(P, (-sw, 0, L - .12), (.17, .34, .25)))
    vest = lambda P: np.maximum(vzone(P), P[2] - (L + .02))
    def sdf(P):
        b = hem(base_torso(P, c) + folds(P), P, .0, .012)
        v = smax(b - .016 + .0035 * np.sin(P[0] * 95) * smooth01(.16, .06, P[2]) + .0015 * np.sin(P[2] * 120), vest(P), .006)
        d = smin(b, v, .003)
        d = smin(d, neck(P, c), .03)
        d = smin(d, collar(P, L), .004)
        lan = U(path(P, [(-.135, -.14, L + .08), (-.125, -.285, L - .16), (-.04, -.325, .74), (0, -.33, .62)], .012),
                path(P, [(.135, -.14, L + .08), (.125, -.285, L - .16), (.04, -.325, .74), (0, -.33, .62)], .012), k=.006)
        d = smin(d, lan, .003)
        d = smin(d, rbox(P, (.0, -.345, .51), (.085, .007, .105), .006, rot=(0, .1, 0)), .002)
        return d + .003 * CL(P)
    paint = [
        (lambda P: P[2] + .006, c['pant'], .004, 0),
        (lambda P: smax(vest(P), .0 - P[2], .001), c['vest'], .003, 0),
        (lambda P: path(P, [(-.135, -.14, L + .08), (-.125, -.285, L - .16), (-.04, -.325, .74), (0, -.33, .62)], .02), c['lan'], .002, 0),
        (lambda P: path(P, [(.135, -.14, L + .08), (.125, -.285, L - .16), (.04, -.325, .74), (0, -.33, .62)], .02), c['lan'], .002, 0),
        (lambda P: rbox(P, (.0, -.345, .51), (.09, .02, .11), .006, rot=(0, .1, 0)), '#f6efe0', .002, 0),
        (lambda P: rbox(P, (.009, -.345, .59), (.09, .03, .02), .002, rot=(0, .1, 0)), '#2f8fa8', .002, 0),
        (lambda P: rbox(P, (-.012, -.345, .49), (.04, .03, .05), .002, rot=(0, .1, 0)), '#c48a5c', .002, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .0)), .002), c['skin'], .003, 0),
    ]
    return sdf, paint, c['shirt']

def blazer_sdf(P, c, apex, slope, lap=.075):
    L, cw, dp = c['L'], c['cw'], c['dp']
    b = base_torso(P, c)
    y0 = -(cw * dp) - .005
    d = hem(b + folds(P, .005), P, -.03, .016)
    shirt = b + .014
    jacket = smax(d, -np.maximum(V_zone(P, apex, slope), -P[1] - 0 - .0 + (P[1] * 0)), .004) if False else smax(d, -smax(V_zone(P, apex, slope), P[1] + .05, .001), .004)
    d = smin(shirt, jacket, .002)
    for s in (-1, 1):
        d = smin(d, rbox(P, (s * .155, y0 - .002, (apex + L) / 2 - .02), (lap, .011, (L - apex) / 2 + .03), .012, rot=(.08, s * .05, s * (.34 if slope > .3 else .28))), .004)
    # centre closure below the button
    d = d + .005 * np.exp(-(P[0] / .007) ** 2) * (P[2] < apex) * (P[1] < 0)
    return d

def blazer(c):
    L = c['L']
    ap = .54
    def sdf(P):
        d = blazer_sdf(P, c, ap, .34)
        d = smin(d, neck(P, c), .03)
        for s in (-1, 1):
            d = smin(d, rbox(P, (s * .205, -.265, .20), (.085, .012, .028), .01, rot=(0, 0, s * .1)), .004)
        d = smin(d, ell(P, (0, -.272, ap - .05), (.028, .012, .028)), .003)
        if c.get('necklace', 1):
            d = smin(d, path(P, [(-.13, -.12, L + .06), (-.08, -.255, L - .12), (0, -.285, L - .20), (.08, -.255, L - .12), (.13, -.12, L + .06)], .006), .002)
            d = smin(d, ell(P, (0, -.295, L - .225), (.018, .008, .024)), .002)
        return d + .0028 * CL(P)
    paint = [
        (lambda P: P[2] + .036, c['pant'], .003, 0),
        (lambda P: smax(V_zone(P, ap, .34) - .004, P[1] + .05, .001), c['top'], .003, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L - .02)), .002), c['skin'], .003, 0),
        (lambda P: V_zone(P, L - .10, .9), c['skin'], .004, 0),
        (lambda P: ell(P, (0, -.272, ap - .05), (.034, .02, .034)), '#7c2a25', .002, 0),
    ]
    if c.get('necklace', 1):
        paint += [(lambda P: path(P, [(-.13, -.12, L + .06), (-.08, -.255, L - .12), (0, -.285, L - .20), (.08, -.255, L - .12), (.13, -.12, L + .06)], .011), '#e7c15c', .002, 1.0),
                  (lambda P: ell(P, (0, -.295, L - .225), (.022, .014, .028)), '#e7c15c', .002, 1.0)]
    return sdf, paint, c['jacket']

def suit_jacket(c):
    L = c['L']
    ap = .60
    def sdf(P):
        d = blazer_sdf(P, c, ap, .30, lap=.07)
        d = smin(d, neck(P, c), .03)
        for s in (-1, 1):
            # sharp padded shoulders: quiet authority
            d = smin(d, rbox(P, (s * (c['sw'] - .09), .012, L - .005), (.11, .10, .03), .025, rot=(0, s * .1, 0)), .04)
        d = smin(d, ell(P, (0, -.27, ap - .05), (.024, .012, .024)), .003)
        if c.get('pin', 1):
            d = smin(d, ell(P, (.165, -.31, .92), (.03, .012, .03)), .003)
        # blouse collar
        d = smin(d, collar(P, L, -.18, .11, .024), .004)
        return d + .0025 * CL(P)
    paint = [
        (lambda P: P[2] + .036, c['pant'], .003, 0),
        (lambda P: smax(V_zone(P, ap, .30) - .004, P[1] + .05, .001), c['top'], .003, 0),
        (lambda P: collar(P, L, -.18, .11, .03), c['top'], .002, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .03)), .002), c['skin'], .003, 0),
        (lambda P: ell(P, (0, -.27, ap - .05), (.03, .02, .03)), '#e7c15c', .002, 1.0),
    ]
    if c.get('pin', 1):
        paint.append((lambda P: ell(P, (.165, -.31, .92), (.036, .02, .036)), '#e7c15c', .002, 1.0))
    return sdf, paint, c['jacket']

def _buttons(P, L, y0, n=5, top=None, bottom=.12, r=.017):
    """A row of buttons down the front, as one field."""
    top = L - .16 if top is None else top
    d = None
    for i in range(n):
        z = top - (top - bottom) * i / max(1, n - 1)
        q = ell(P, (0, y0 - .012 - .02 * np.exp(-((z - .62) / .3) ** 2), z), (r, r * .6, r))
        d = q if d is None else np.minimum(d, q)
    return d

def _front_y(c):
    return -(c['cw'] * c['dp'])

def shirt(c):
    """A collared shirt, buttoned to the neck or open one button: the plainest thing a person wears to work."""
    L = c['L']
    y0 = _front_y(c)
    def sdf(P):
        b = base_torso(P, c) + folds(P, .007)
        d = hem(b, P, .0, .02)
        d = d + .004 * np.exp(-((P[0] - .0) / .022) ** 2) * (P[1] < 0) * (P[2] < L - .12) * -1    # the placket stands a little proud
        d = smin(d, neck(P, c), .03)
        d = smin(d, collar(P, L, -.185, .125, .03), .005)
        d = smin(d, _buttons(P, L, y0), .003)
        d = smin(d, rbox(P, (.2, y0 - .012, L - .36), (.075, .008, .085), .008), .003)            # a chest pocket
        return d + .003 * CL(P)
    paint = [
        (lambda P: P[2] + .006, c['pant'], .004, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .0)), .002), c['skin'], .003, 0),
        (lambda P: V_zone(P, L - .11, .8), c['skin'], .004, 0),
        (lambda P: _buttons(P, L, y0, r=.021), c.get('button', '#f3ecdd'), .002, 0),
    ]
    return sdf, paint, c['top']

def sweater(c):
    """A crew-neck jumper: ribbed at the neck and the hem, soft everywhere else."""
    L = c['L']
    ring = [(-.2, .02, L + .04), (-.15, -.14, L + .0), (0, -.215, L - .05), (.15, -.14, L + .0), (.2, .02, L + .04), (0, .16, L + .07), (-.2, .02, L + .04)]
    def sdf(P):
        b = base_torso(P, c) + folds(P, .009, z0=.3)
        d = b - .03
        # the rib of the hem, and the knit itself
        d = d - .012 * smooth01(.16, .08, P[2]) * (.6 + .4 * np.sin(P[0] * 80)) * (P[2] > .02)
        d = d + .0018 * np.sin(P[0] * 105) * np.sin(P[2] * 105)
        d = smin(d, neck(P, c), .03)
        d = smin(d, path(P, ring, .04), .012)
        if c.get('shirt_collar', 1):
            d = smin(d, collar(P, L, -.19, .115, .024), .004)
        return d + .0035 * CL(P)
    paint = [
        (lambda P: P[2] - .02, c['pant'], .004, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .02)), .002), c['skin'], .003, 0),
    ]
    if c.get('shirt_collar', 1):
        paint.append((lambda P: collar(P, L, -.19, .115, .03), c.get('shirt', '#f1ece4'), .002, 0))
    return sdf, paint, c['top']

def hoodie(c):
    """A hooded sweatshirt: the hood rolled behind the neck, drawstrings, one wide pocket."""
    L = c['L']
    y0 = _front_y(c)
    def sdf(P):
        b = base_torso(P, c) + folds(P, .008)
        d = b - .028
        d = d - .01 * smooth01(.15, .07, P[2]) * (P[2] > .02)                                    # the ribbed hem
        d = smin(d, rbox(P, (0, y0 - .03, .30), (.24, .02, .11), .03), .012)                     # the pocket
        d = smin(d, neck(P, c), .03)
        d = smin(d, ell(P, (0, .20, L + .07), (.27, .19, .17)), .05)                             # the hood, lying back
        d = smin(d, path(P, [(-.25, .06, L + .03), (-.2, -.13, L + .03), (0, -.215, L - .02), (.2, -.13, L + .03), (.25, .06, L + .03)], .062), .03)
        for s in (-1, 1):
            d = smin(d, path(P, [(s * .07, -.26, L - .03), (s * .08, -.30, L - .17), (s * .075, -.315, L - .29)], .011), .003)
            d = smin(d, ell(P, (s * .075, -.32, L - .31), (.016, .016, .026)), .003)
        return d + .003 * CL(P)
    paint = [
        (lambda P: P[2] - .02, c['pant'], .003, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .02)), .002), c['skin'], .003, 0),
    ]
    for s in (-1, 1):
        paint.append((lambda P, s=s: path(P, [(s * .07, -.26, L - .03), (s * .08, -.30, L - .17), (s * .075, -.315, L - .29)], .016), c.get('cord', '#e8e2d2'), .002, 0))
        paint.append((lambda P, s=s: ell(P, (s * .075, -.32, L - .31), (.02, .02, .03)), c.get('cord', '#e8e2d2'), .002, 0))
    return sdf, paint, c['top']

def kurta(c):
    """A short kurta: a band collar, a buttoned placket to the chest, straight to the hip with a slit at each side."""
    L = c['L']
    y0 = _front_y(c)
    def sdf(P):
        b = base_torso(P, c) + folds(P, .006, z0=.25, zw=.3)
        d = b - .02
        # it hangs straight from the chest rather than following the waist, and ends below the hip
        d = smin(d, ell(P, (0, 0, .12), (c['hw'] + .045, (c['hw'] + .04) * c['dp'], .40)), .08)
        d = smax(d, -(P[2] + .27), .012)
        for s in (-1, 1):
            d = smax(d, -rbox(P, (s * (c['hw'] + .05), 0, -.2), (.03, .05, .12), .01), .01)       # the side slits
        d = smin(d, neck(P, c), .03)
        d = smin(d, path(P, [(-.16, .03, L + .07), (-.12, -.13, L + .05), (-.03, -.2, L + .02)], .026), .006)   # the band collar, open at the front
        d = smin(d, path(P, [(.16, .03, L + .07), (.12, -.13, L + .05), (.03, -.2, L + .02)], .026), .006)
        d = smin(d, rbox(P, (0, y0 - .015, L - .3), (.03, .008, .26), .006), .004)               # the placket
        d = smin(d, _buttons(P, L, y0 - .012, n=4, top=L - .1, bottom=L - .5, r=.014), .003)
        return d + .003 * CL(P)
    paint = [
        (lambda P: P[2] + .285, c['pant'], .004, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .02)), .002), c['skin'], .003, 0),
        (lambda P: V_zone(P, L - .06, .55), c['skin'], .004, 0),
        (lambda P: rbox(P, (0, y0 - .015, L - .3), (.036, .03, .27), .006), c.get('trim', c['top']), .003, 0),
        (lambda P: _buttons(P, L, y0 - .012, n=4, top=L - .1, bottom=L - .5, r=.018), c.get('button', '#e7c15c'), .002, 1.0),
    ]
    return sdf, paint, c['top']

def zip_jacket(c):
    """A casual jacket worn open over a shirt: ribbed collar and hem, a zip down each edge."""
    L = c['L']
    ap = .1
    def sdf(P):
        b = base_torso(P, c)
        d = hem(b + folds(P, .006), P, .02, .012)
        shirt_ = b + .014
        open_ = smax(np.abs(P[0]) - .075 - (P[2] - ap) * .09, P[1] + .05, .001)                  # the gap the jacket hangs open by
        jacket = smax(d - .03, -open_, .006)
        d = smin(shirt_, jacket, .003)
        d = d - .011 * smooth01(.15, .07, P[2]) * (P[2] > .02) * (np.abs(P[0]) > .1)             # the ribbed hem
        for s in (-1, 1):
            # the zip: a fine ridge down each open edge
            d = smin(d, path(P, [(s * (.085 + (L - .2 - ap) * .09), _front_y(c) - .03, L - .2), (s * .08, _front_y(c) - .035, ap + .04)], .011), .004)
            d = smin(d, rbox(P, (s * .23, _front_y(c) - .028, .3), (.012, .012, .09), .006, rot=(0, s * .25, 0)), .004)   # slanted pockets
        d = smin(d, neck(P, c), .03)
        d = smin(d, path(P, [(-.21, .05, L + .05), (-.17, -.12, L + .03), (-.09, -.2, L - .04)], .05), .02)   # the collar, standing
        d = smin(d, path(P, [(.21, .05, L + .05), (.17, -.12, L + .03), (.09, -.2, L - .04)], .05), .02)
        d = smin(d, ell(P, (0, .16, L + .06), (.2, .09, .07)), .03)
        return d + .003 * CL(P)
    paint = [
        (lambda P: P[2] - .02, c['pant'], .003, 0),
        (lambda P: smax(np.abs(P[0]) - .07 - (P[2] - ap) * .09, P[1] + .05, .001), c['top'], .003, 0),
        (lambda P: smax(neck(P, c) - .012, -(P[2] - (L + .0)), .002), c['skin'], .003, 0),
        (lambda P: V_zone(P, L - .09, .8) + 1e3 * (P[1] > -.05), c['skin'], .004, 0),
    ]
    return sdf, paint, c['jacket']

HAND = hr.HAND
def make_hand(c, pose, side, out):
    s = c.get('hs', 1.0)
    H = HAND[pose]
    zs = np.array([-.066, -.024, .018, .058])
    lens = np.array([.82, .96, 1.0, .9])
    side_ = side  # +1 thumb +z, -1 mirrored
    def sdf(P0):
        P = (P0[0] / s, P0[1] / s, P0[2] / s * side_)
        d = ell(P, (.055, .0, -.002), (.092, .036, .092))
        d = smin(d, cone(P, (-.09, 0, 0), (.0, 0, 0), .052, .058), .03)
        for i, (z, ln) in enumerate(zip(zs, lens)):
            a = H['c'][i]
            x, y, zz = .125, 0., z
            ang = 0.
            zdir = (z / .066) * H['spread'] * .6
            pts = [(.10, 0, z * .92)]
            for seg, (cu, L_) in enumerate(zip(a, (.062, .05, .04))):
                ang += cu
                x += np.cos(ang) * L_ * ln
                y += np.sin(ang) * L_ * ln
                zz += zdir * L_
                pts.append((x, y, zz))
            d = smin(d, path(P, pts, .0215, .0175, k=.006), .012)
        t0, t1 = H['th']
        tb = (.03, -.02, .058)
        tm = (tb[0] + .05 * np.cos(t1 * .6), tb[1] - .025 - .02 * np.sin(t1), tb[2] + .055 * np.sin(t0))
        tt = (tm[0] + .045 * np.cos(t1), tm[1] - .012 - .02 * np.sin(t1), tm[2] + .05 * np.sin(t0))
        d = smin(d, path(P, [tb, tm, tt], .027, .02, k=.006), .018)
        return (d + .0015 * CL(P, 5)) * s
    sl = c.get('sleeve', c['skin'])
    cuff = c.get('cuff', sl)
    paint = [(lambda P: P[0] + .045 * s, cuff, .002, c.get('cuffm', 0))]
    def full(P):
        d = sdf(P)
        return smin(d, smax(cone(P, (-.075 * s, 0, 0), (-.20 * s, 0, 0), .070 * s, .072 * s), -(P[0] + .05 * s), .006), .004)
    return mesh(full, (-.24 * s, -.2 * s, -.2 * s), (.36 * s, .2 * s, .2 * s), 80, paint=paint, base=c['skin'], path_=out, smooth=.45)

def make_hand_rig(c, side, out):
    """The hand as the puppet poses it: one sculpted skin per side, fingers fanned so each is its own form, with skin weights for the
    bones in handrig.py. Same palm, same finger proportions and same clay as make_hand; the shapes it can take are now continuous."""
    s = c.get('hs', 1.0)
    ch = hr.chains(hr.fvec(hr.BASE))
    def sdf(P0):
        P = (P0[0] / s, P0[1] / s, P0[2] / s * side)
        d = ell(P, (.055, .0, -.002), (.092, .036, .092))
        d = smin(d, cone(P, (-.09, 0, 0), (.0, 0, 0), .052, .058), .03)
        for J in ch[:4]:
            d = smin(d, path(P, [tuple(q) for q in J], .0215, .0175, k=.006), .012)
        d = smin(d, path(P, [tuple(q) for q in ch[4]], .027, .02, k=.006), .018)
        return (d + .0015 * CL(P, 5)) * s
    sl = c.get('sleeve', c['skin'])
    cuff = c.get('cuff', sl)
    paint = [(lambda P: P[0] + .045 * s, cuff, .002, c.get('cuffm', 0))]
    def full(P):
        d = sdf(P)
        return smin(d, smax(cone(P, (-.075 * s, 0, 0), (-.20 * s, 0, 0), .070 * s, .072 * s), -(P[0] + .05 * s), .006), .004)
    o = mesh(full, (-.24 * s, -.14 * s, -.24 * s), (.38 * s, .14 * s, .24 * s), 112, paint=paint, base=c['skin'], smooth=.45)
    bi, bw = hr.skin(o['v'], s, side)
    np.savez_compressed(out, bi=bi, bw=bw, **o)

# ---------- shoes: origin at ankle centre on the ground ----------
def make_shoe(c, out):
    st = c.get('shoe_style', 'sneaker')
    col, sole = c['shoe'], c.get('sole', '#efe3cb')
    if st == 'heel':
        def sdf(P):
            d = U(ell(P, (0, -.14, .085), (.085, .20, .075)), ell(P, (0, .03, .10), (.08, .085, .10)), k=.05)
            d = smax(d, -(P[2] - .05 - smooth01(.05, -.2, P[1]) * -.03), .012)
            d = smin(d, rbox(P, (0, -.15, .022), (.08, .18, .022), .018), .01)
            d = smin(d, cone(P, (0, .09, .13), (0, .10, .0), .03, .018), .006)
            return d
        return mesh(sdf, (-.14, -.42, -.01), (.14, .2, .24), 72, paint=[(lambda P: P[2] - .03, sole, .003, 0)], base=col, path_=out)
    def sdf(P):
        d = U(ell(P, (0, -.13, .10), (.135, .25, .10)), ell(P, (0, .04, .12), (.12, .115, .13)), k=.06)
        d = smin(d, cone(P, (0, .02, .18), (0, .02, .30), .105, .095), .04)
        sole_ = smax(U(ell(P, (0, -.13, .06), (.142, .262, .10)), ell(P, (0, .04, .06), (.126, .125, .10)), k=.05), P[2] - .056, .006)
        d = smin(d, sole_, .004)
        d = smax(d, -P[2] - .0, .004)
        if st in ('sneaker', 'hitop', 'brogue'):
            for i in range(4):
                d = smin(d, cone(P, (-.052, -.235 + i * .055, .185 - i * -.012), (.052, -.235 + i * .055, .185 - i * -.012), .011), .003)
        if st == 'hitop':
            d = smin(d, torus(P, (0, .02, .29), .10, .022, rot=(np.pi / 2, 0, 0)), .006)
        return d + .002 * CL(P, 3)
    p = [(lambda P: P[2] - .062, sole, .003, 0)]
    if st == 'sneaker' or st == 'hitop':
        p.append((lambda P: ell(P, (0, -.31, .09), (.11, .075, .09)), sole, .004, 0))
        p.append((lambda P: smax(np.abs(P[0]) - .062, np.abs(P[1] + .15) - .10, .002) + 1e3 * (P[2] < .13), '#fbf5e6', .002, 0))
    return mesh(sdf, (-.18, -.42, -.01), (.18, .22, .38), 80, paint=p, base=col, path_=out)
