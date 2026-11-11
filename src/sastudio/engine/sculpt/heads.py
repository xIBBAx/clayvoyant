"""Head, face, eye and brow sculpts. Head origin: base of neck pivot, face toward -y, top of skull near z=1.05.
A head is one continuous piece, with the mouth carved into it; faceops.py moves it."""
import os, sys
import numpy as np
from sdfkit import *
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clay'))  # shared with the Blender side
from faceops import zline, slit_h

LUMP = Field(11, sigma=7)
MOTTLE = Field(23, sigma=5)
FINE = Field(41, sigma=2)

def mixhex(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def eye_y(r):
    """Eyeball centre depth. The ball sits just proud of the eye band's plane so the lid margins rest on it, as they do on a person.
    Set .012 behind that plane, you could see down the wall of the socket beside the eye from three quarters."""
    return -.375 + r + .012 - .024

def skull_sdf(P, p):
    """Everything but the mouth, drawn on real facial proportions: eyes at half the head's height, the base of the nose
    halfway from eye to chin, the mouth a third of the way down from there. One smooth mandible tapers from the cheek to the
    chin. An egg of a face kept full width down to the mouth, with separate jaw-corner blobs hung on it, reads as two
    bones about to poke through, and its nose stopped so high that the upper lip was twice the length of a real one."""
    fw, jw, cw, ns = p.get('fw', 1), p.get('jaw', 1), p.get('chin', 1), p.get('nose', 1)
    es, ez, mz = p['es'], p['ez'], p['mz']
    lo = p.get('long', 0)
    r = p.get('eye', .1)
    ey = p.get('eyey', eye_y(r))
    skull = ell(P, (0, .05, .66), (.44 * fw, .47, .41))
    # the mid-face ends above the mouth: below that the mandible alone sets the outline
    face = ell(P, (0, -.075, .475), (.378 * fw, .325, .325))
    d = smin(skull, face, .12)
    jaw = ell(P, (0, -.105, .245 - lo), (.298 * jw, .285, .225 + lo * .4))
    d = smin(d, jaw, .13)
    jc = p.get('jawc', 0)
    if jc:
        # a firmer jaw for the men: the same single form made a little squarer, always inside the outline, never a corner
        for s in (-1, 1):
            d = smin(d, ell(P, (s * (.135 + .05 * jc) * jw, -.125, .165 - lo), (.13, .175, .105)), .13)
    chin = ell(P, (0, -.285, .092 - lo * 1.3), (.098 * cw, .092, .066 * p.get('chinh', 1)))
    d = smin(d, chin, .095)
    # the nape: the skull runs on into the neck and down inside the collar, one form, so no seam shows when someone is seen from behind
    d = smin(d, cone(P, (0, .125, .32), (0, .135, -.12), .115, .135), .05)
    # the eye band: a broad, gently curved plane across both eyes, so the skin stands just proud of the eyeballs
    d = smin(d, ell(P, (0, -.21, ez + .015), (.355 * fw, .195, .15)), .10)
    ck = p.get('cheek', 1)
    for s in (-1, 1):
        # cheeks high under the eyes: youth lives here
        d = smin(d, ell(P, (s * .205 * fw, -.215, .385 - lo * .3), (.125 * ck, .145, .10)), .10)
    # the muzzle: the lips sit on the curve of the teeth, a little proud of the chin and no more
    d = smin(d, ell(P, (0, -.245, mz + .018), (.158, .165, .112)), .085)
    rb = p.get('ridge', .3)
    if rb > 0:
        # brow shelf: one soft plane over both eyes, stronger for the men, fading out before the temples
        d = smin(d, ell(P, (0, -.30 - .02 * rb, ez + .15), (.30 * fw, .095, .05)), .05 + .05 * rb)
    # the nose: rises out of the face at the eyes, gains its bridge on the way down, rounded tip, soft wings
    nl, nb, nw = p.get('nl', 1), p.get('nb', 1), p.get('nw', 1)
    ny = -.480 - .02 * (nl - 1) * 2
    nz = .338 - .03 * (nl - 1)
    d = smin(d, cone(P, (0, -.365, ez + .035), (0, ny + .03, nz + .03), .027 * nb, .035 * ns), .058)
    d = smin(d, ell(P, (0, ny, nz), (.046 * ns * nw, .042 * ns, .04 * ns)), .035)
    for s in (-1, 1):
        d = smin(d, ell(P, (s * .05 * ns * nw, ny + .034, nz - .016), (.03 * ns * nw, .028, .024)), .022)
        d = sub(d, ell(P, (s * .025 * ns * nw, ny - .01, nz - .036), (.012, .014, .008)), .009)
    # the lid opening: an almond, not a porthole. The skin covers the top and bottom of the eyeball, as it does on a person,
    # so nobody stares; the lid shells tuck in behind it and only their margins show
    ah = p.get('almond', .78)
    # the opening looks where the face looks at that spot, outward by the curve of the head, and it is narrower than the ball
    toe = p.get('socket', .26)
    for s in (-1, 1):
        d = smax(d, -ell(P, (s * (es + .02 * np.sin(toe)), ey - .02 * np.cos(toe), ez + .002), (r * .94, r + .035, r * ah * .85), rot=(0, 0, s * toe)), .02)
    # ears with an inner dent
    ee = p.get('ear', 1)
    for s in (-1, 1):
        d = smin(d, ell(P, (s * .432 * fw, .03, .455), (.04 * ee, .066 * ee, .092 * ee), rot=(0, s * .12, s * -.25)), .025)
        d = sub(d, ell(P, (s * (.432 * fw + .03 * ee), .0, .455), (.018 * ee, .038 * ee, .058 * ee)), .012)
    return d

def sm_(e0, e1, x):
    q = np.clip((x - e0) / (e1 - e0), 0, 1)
    return q * q * (3 - 2 * q)

def _lips(P, p):
    """Vermilion thickness above and below the line, as signed height over the skin."""
    W = p['W']
    x, z = P[0], P[2]
    zL = zline(x, p)
    dz = z - zL
    u = np.clip(x / W, -1, 1)
    taper = np.clip(1 - u * u, 0, 1) ** .62
    bow = 1 + .22 * np.exp(-((np.abs(x) - .30 * W) / (.22 * W)) ** 2) - .26 * np.exp(-(x / (.085 * W)) ** 2)
    tu = np.maximum(p.get('lipU', .036) * taper * bow, 1e-4)
    tl = np.maximum(p.get('lipL', .045) * taper * (1 + .08 * np.exp(-(x / (.5 * W)) ** 2)), 1e-4)
    t = np.where(dz > 0, dz / tu, -dz / tl)
    amt = np.where(dz > 0, p.get('lipBU', .018), p.get('lipBL', .026))
    # lips belong to the front of the face: without the y limit the same ridge ran round to the back of the neck
    bump = np.clip(1 - t * t, 0, 1) ** .7 * amt * (np.abs(x) < W) * (P[1] < -.15)
    return bump, t, zL, dz

def pocket_sdf(P, p):
    return ell(P, (0, -.225, p['mz'] - .03), (p['W'] * 1.2, .115, .115))

def slit_sdf(P, p):
    x, y, z = P
    zL = zline(x, p)
    hh = slit_h(x, p)
    return np.maximum(np.maximum(np.abs(z - zL) - hh, np.abs(x) - p['W']), y + .29)

def beard_zone(P, p):
    """Negative where a full beard grows: the chin, the jaw and up the cheek to the ear, clear of the lips."""
    x, y, z = P
    lo, mz, W, ez = p.get('long', 0), p['mz'], p['W'], p['ez']
    ax = np.abs(x)
    top = mz - .06 + np.clip((ax - W * .95) / (.43 - W * .95), 0, 1) ** 2.2 * (ez - mz - .06)
    return np.maximum(np.maximum(ell(P, (0, -.17, .15 - lo), (.455, .38, .27)), z - top), y - .10)

def moustache_zone(P, p):
    W = p['W']
    droop = .03 * (np.abs(P[0]) / W) ** 2
    return ell((P[0], P[1], P[2] + droop), (0, -.40, p['mz'] + .052), (W * 1.12, .13, .03))

def head_sdf(P, p):
    d = skull_sdf(P, p)
    x, y, z = P
    bump, t, zL, dz = _lips(P, p)
    d = d - bump
    if p.get('beard'):
        # a beard is clay laid on the jaw and combed downward; it is part of the head, so it moves with the mouth
        d = d - (.022 * p['beard'] + .004 * np.sin(x * 70 + 2.2 * LUMP(P, 2.2)) * np.sin(z * 34)) * sm_(.02, -.02, beard_zone(P, p))
    if p.get('moustache'):
        d = d - (.024 * p['moustache'] + .003 * np.sin(x * 120)) * sm_(.012, -.012, moustache_zone(P, p))
    mz = p['mz']
    # philtrum, and the soft crease under the lower lip
    d = d + .0035 * np.exp(-(x / .02) ** 2) * ((z > mz + .03) & (z < mz + .13)) * (y < -.3)
    d = d + .005 * np.exp(-((z - (mz - .083)) / .016) ** 2) * np.exp(-(x / .075) ** 2) * (y < -.3)
    # the lines a smile leaves, from the wing of the nose past the corner of the mouth: faint, but a face without them is a mask
    cr = p.get('crease', .0026)
    if cr:
        ax, W_ = np.abs(x), p['W']
        zl = mz + .112 - 1.15 * (ax - .075) - 2.6 * np.maximum(ax - W_ - .012, 0)
        d = d + cr * np.exp(-((z - zl) / .0125) ** 2) * sm_(.062, .092, ax) * sm_(W_ + .075, W_ + .03, ax) * (y < -.28)
    d = smax(d, -slit_sdf(P, p), .0035)
    d = smax(d, -pocket_sdf(P, p), .004)
    # thumbprint scale only: the clay stays tactile, the face stays calm
    return d + .0022 * LUMP(P, 1.4)

def natural_skin(p):
    """Skin is never one colour, and a face is never clean. Warmth gathers at the nose, the ears and the apples of the cheeks,
    it goes a little cool under the eyes, the sun has been at the bridge of the nose and the brow, and everybody has their own
    few freckles and moles. Painted the way a puppet maker would: thin washes, then a few dots with a fine brush."""
    sk = p['skin']
    flush, sun, cool = mixhex(sk, '#d4604e', .30), mixhex(sk, '#a8683c', .24), mixhex(sk, '#7d6f86', .17)
    mark, fr = mixhex(p['skinD'], '#5a3424', .62), mixhex(sk, '#8a5230', .46)
    es, ez = p['es'], p['ez']
    R = [(lambda P: MOTTLE(P, 1.7) * 1.3 + .03, sun, .20, 0),                     # uneven tone, a hand wide
         (lambda P: FINE(P, 3.4) * 1.5 + .16, mixhex(sk, '#c8705a', .16), .10, 0),  # the fine blotch under it
         (lambda P: ell(P, (0, -.50, .36), (.085, .09, .10)), flush, .05, 0),        # nose
         (lambda P: ell(P, (0, -.40, .655), (.24, .12, .06)), sun, .07, 0)]          # across the brow
    for s in (-1, 1):
        R.append((lambda P, s=s: ell(P, (s * .445, .02, .46), (.07, .10, .13)), flush, .05, 0))             # ears
        R.append((lambda P, s=s: ell(P, (s * es, -.40, ez - .115), (.105, .08, .036)), cool, .04, 0))       # under the eye
    r = np.random.default_rng(p.get('seed', 3))
    for _ in range(p.get('freckle', 0)):
        s = r.choice((-1, 1))
        x, z = s * abs(r.normal(.13, .075)), r.normal(.405, .034)
        y, q = surface_y(p, x, z), r.uniform(.0052, .0098)
        R.append((lambda P, c=(x, y, z), q=q: ell(P, c, (q, q * 2, q * .9)), fr, .005, 0))
    for x, z, q in p.get('moles', ()):
        y = surface_y(p, x, z)
        R.append((lambda P, c=(x, y, z), q=q: ell(P, c, (q, q * 2, q)), mark, .0045, 0))
    return R

def head_paint(p):
    bl = p.get('blush', p['skin'])
    sd = p['skinD']
    es, ez, mz, W = p['es'], p['ez'], p['mz'], p['W']
    lo = p.get('long', 0)
    lip = p.get('lip', '#8a3f33')
    R = natural_skin(p)
    if p.get('stubble'):
        st = p['stubble']
        R.append((lambda P: np.maximum(ell(P, (0, -.2, .17 - lo), (.42, .34, .24)), mz + .015 - P[2] + .9 * np.maximum(.26 - np.abs(P[0]), 0) * 0), st, .09, 0))
    for s in (-1, 1):
        R.append((lambda P, s=s: ell(P, (s * .265, -.32, .345), (.12, .16, .08)), bl, .12, 0))
        # a little warm shadow round the eye: painted, like the real thing
        R.append((lambda P, s=s: ell(P, (s * es, -.42, ez + .012), (.135, .12, .105)), sd, .06, 0))
        R.append((lambda P, s=s: ell(P, (s * .47, .0, .47), (.07, .09, .12)), bl, .05, 0))
    R.append((lambda P: ell(P, (0, -.52, .35), (.06, .05, .05)), bl, .04, 0))
    R.append((lambda P: ell(P, (0, -.3, .09 - lo * 1.3), (.1, .1, .06)), bl, .05, 0))
    R.append((lambda P: P[2] - (.075 - lo) - .1 * np.maximum(P[1] + .25, 0), sd, .06, 0))
    def lips(P):
        bump, t, zL, dz = _lips(P, p)
        return np.where((np.abs(P[0]) < W) & (P[1] < -.15), (np.abs(t) - 1) * .012, .05)
    R.append((lips, lip, .0035, 0))
    hc = p.get('facehair', p['hair'])
    if p.get('beard'):
        R.append((lambda P: beard_zone(P, p), hc, .016, 0))
    if p.get('moustache'):
        R.append((lambda P: moustache_zone(P, p), hc, .01, 0))
    if p.get('bindi'):
        zb = p['ez'] + .185
        R.append((lambda P: ell(P, (0, surface_y(p, 0, zb), zb), (.019, .03, .019)), p['bindi'], .003, 0))
    def inner(P):
        return np.maximum(np.minimum(pocket_sdf(P, p), slit_sdf(P, p)) - .009, -.395 - P[1])
    # the wet inside of the lips: when the jaw drops this is what catches the light, and bare skin there reads as grey clay
    R.append((lambda P: slit_sdf(P, p) - .012, '#9a4648', .005, 0))
    R.append((inner, '#2a0c12', .006, 0))
    return R

def make_head(p, out):
    b = (-.62, -.72, -.14)
    B = (.62, .62, 1.12)
    return mesh(lambda P: head_sdf(P, p), b, B, p.get('res', 205), paint=head_paint(p), base=p['skin'], path_=out, smooth=.4, cavity=.36)

def surface_y(p, x, z):
    """Where the skin is, along y, at (x, z): places brows, teeth and lashes on the face."""
    ys = np.linspace(-.75, -.1, 700)
    d = skull_sdf((np.full_like(ys, x), ys, np.full_like(ys, z)), p)
    i = np.argmax(d < 0)
    return float(ys[i])

def make_teeth(p, d_):
    """A dental arch: one flat-faced row following the curve of the jaw, wider than the lips, so a smile shows teeth reaching back into shadow,
    not a bar floating in the middle of the mouth. The gum line sits above the lip, so nobody ever shows a gap over their teeth."""
    W, mz = p['W'], p['mz']
    ym = surface_y(p, 0, mz)
    Ry = .135
    cy = ym + .036 + Ry
    def band(P, zt, wx, h, up, back):
        x, y, z = P
        e = (np.sqrt((x / wx) ** 2 + ((y - cy) / Ry) ** 2) - 1) * min(wx, Ry)
        ring = np.abs(e + .011) - .011
        th = np.arctan2(x / wx, -(y - cy) / Ry)
        # the biting edge rounds a little at each tooth's corners, and no more
        bite = .0016 * (1 - np.abs(np.cos(th * 6.6))) ** 2
        q = smax(ring, np.abs(z - zt) - h + bite * (z < zt if up else z > zt), .0045)
        q = smax(q, y - (cy - back), .008)
        # separated by a tool, not by painting; the tool stops short of the biting edge, or every tooth ends in a point
        face = 1 - sm_(h - .012, h - .002, np.abs(z - zt))
        return q + (.0028 * np.exp(-(np.sin(th * 6.6) / .10) ** 2) - .0007 * np.cos(th * 13.2)) * face
    # teeth go back into the shadow of the cheeks
    shade = [(lambda P: W * .80 - np.abs(P[0]), '#5c4a44', .045, 0)]
    zu, zl = mz + .034, mz - .024
    mesh(lambda P: band(P, zu, W * 1.12, .034, True, .03), (-W * 1.25, cy - Ry - .02, zu - .06), (W * 1.25, cy + .03, zu + .06), 120, paint=shade, base='#fdfaf2', path_=d_ + 'teethU.npz', smooth=.3, cavity=.12)
    mesh(lambda P: band(P, zl, W * 1.0, .030, False, .065), (-W * 1.25, cy - Ry - .02, zl - .05), (W * 1.25, cy + .03, zl + .05), 120, paint=shade, base='#faf5ea', path_=d_ + 'teethL.npz', smooth=.3, cavity=.12)
    mesh(lambda P: ell(P, (0, cy + .012, mz - .05), (W * .62, Ry * .86, .026)) + .002 * LUMP(P, 6), (-W, cy - Ry, mz - .1), (W, cy + Ry, mz), 72, base='#c4515c', path_=d_ + 'tongue.npz', smooth=.4, cavity=.12)

# ---- replacement mouths ----
# W half width, H half height, bend corner lift, skew, T lip thickness, teeth 0/1(upper)/2(both), tongue
VIS = dict(
    A=dict(W=.088, H=.0, bend=.010, T=.020),
    B=dict(W=.126, H=.022, bend=.020, T=.016, teeth=2),
    C=dict(W=.118, H=.046, bend=.016, T=.016, teeth=1, tongue=1),
    D=dict(W=.118, H=.088, bend=.012, T=.016, teeth=1, tongue=1),
    E=dict(W=.086, H=.056, bend=.006, T=.020, teeth=1, tongue=1),
    F=dict(W=.050, H=.030, bend=.0, T=.028),
    G=dict(W=.106, H=.016, bend=.012, T=.016, teeth=1),
    H=dict(W=.106, H=.052, bend=.010, T=.016, teeth=1, tongue=2),
    warm=dict(W=.118, H=.0, bend=.030, T=.020),
    smile=dict(W=.140, H=.0, bend=.056, T=.020),
    grin=dict(W=.146, H=.040, bend=.060, T=.016, teeth=1),
    flat=dict(W=.098, H=.0, bend=.0, T=.018),
    frown=dict(W=.098, H=.0, bend=-.036, T=.018),
    smirk=dict(W=.118, H=.0, bend=.018, skew=.030, T=.018),
    gasp=dict(W=.080, H=.082, bend=.0, T=.018, tongue=1),
    worry=dict(W=.110, H=.010, bend=-.022, T=.015, teeth=1),
)

# ---- eyes ----
def make_eye(p, out):
    """Unit-placed eyeball at origin; rotates whole. Vertex-painted sclera, limbal ring, iris gradient, pupil."""
    r = p.get('eye', .108)
    iris, iris2 = p['iris'], p.get('iris2', p['iris'])
    ir = r * p.get('irisr', .56)
    def ang(P):
        n = np.sqrt(P[0] ** 2 + P[1] ** 2 + P[2] ** 2) + 1e-6
        return np.arccos(np.clip(-P[1] / n, -1, 1)) * r  # arc distance from the front pole
    paint = [
        (lambda P: ang(P) - ir * 1.08, '#1c120c', .003, 0),
        (lambda P: ang(P) - ir, iris, .006, 0),
        (lambda P: ang(P) - ir * .62, iris2, .012, 0),
        (lambda P: ang(P) - ir * .46, '#050303', .002, 0),
    ]
    # cornea bump: pupil region bulges so the highlight slides as the eye turns
    return mesh(lambda P: smin(ell(P, (0, 0, 0), (r, r, r)), ell(P, (0, -r * .78, 0), (ir * 1.05, r * .34, ir * 1.05)), .012), (-r * 1.2, -r * 1.3, -r * 1.2), (r * 1.2, r * 1.2, r * 1.2), 64, paint=paint, base='#f4ece0', path_=out)

def make_lids(p, out_u, out_l):
    r = p.get('eye', .108) + .007
    sk = p['skin']
    lash = p.get('lash', '#20140e')
    wing = p.get('wing', 0)
    lw = p.get('lashw', .0052) + wing * .0028
    crease = [(-r * .92, -r * .22, r * .34), (-r * .55, -r * .78, r * .44), (0, -r * .96, r * .47), (r * .55, -r * .78, r * .44), (r * .92, -r * .22, r * .34)]
    def upper(P):
        sh = np.abs(np.sqrt(P[0] ** 2 + P[1] ** 2 + P[2] ** 2) - r) - .006
        return smax(sh, -P[2], .006)
    def lower(P):
        sh = np.abs(np.sqrt(P[0] ** 2 + P[1] ** 2 + P[2] ** 2) - r + .001) - .0035
        return smax(sh, P[2], .006)
    rim = [(-r * .99, -.012, .002), (-r * .6, -r * .82, .004), (0, -r * 1.005, .004), (r * .6, -r * .82, .004), (r * .99, -.012, .002)]
    def u(P):
        d = U(upper(P), path(P, rim, lw), k=.004)
        if wing:
            for s_ in (-1, 1):
                d = smin(d, cone(P, (s_ * r * .93, -.03, .004), (s_ * r * 1.2, -.0, .03), lw * 1.1, .0015), .004)
        return d
    paint = [(lambda P: P[2] - (.006 + wing * .004), lash, .0025, 0), (lambda P: np.maximum(path(P, crease, .007), -(P[2] - .02)), p['skinD'], .003, 0)]
    mesh(u, (-r * 1.3, -r * 1.25, -.02), (r * 1.3, r * 1.25, r * 1.2), 64, paint=paint, base=p.get('lidc', p['skin']), path_=out_u, smooth=.4, cavity=0)
    mesh(lower, (-r * 1.25, -r * 1.25, -r * 1.2), (r * 1.25, r * 1.25, .02), 56, base=p.get('lidc', p['skin']), path_=out_l, smooth=.4, cavity=0)

def make_brow(p, out, side):
    """Shaped, not rolled: flat against the skin, thick at the nose end, feathered by tool strokes."""
    w, h = p.get('browW', .105), p.get('browH', .017)
    a = p.get('browArch', .022)
    # the brow follows the skin round the head: kept straight, its tail stands off the face like a stuck-on worm
    yc = surface_y(p, p['es'], p['browz'])
    dy = lambda x, z: surface_y(p, p['es'] + x, p['browz'] + z) - yc
    pts = [(-w * side, dy(-w, -.006), -.006), (-w * .35 * side, dy(-w * .35, a) - .002, a), (w * .4 * side, dy(w * .4, a * .9) - .002, a * .9), (w * side, dy(w, -a * .55), -a * .55)]
    def sdf(P):
        Q = (P[0], P[1] * 2.1, P[2])
        d = path(Q, pts, h, h * .32, k=.012)
        return d + .0012 * LUMP(P, 7)
    return mesh(sdf, (-w * 1.3, -.11, -.06), (w * 1.3, .11, .08), 84, base=p.get('browc', p['hair']), path_=out, smooth=.4, cavity=.2)
