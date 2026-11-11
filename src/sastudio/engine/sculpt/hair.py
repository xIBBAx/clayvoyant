"""Sculpted clay hair. A hair shape is one mass that hugs the real skull, carved with flowing valleys by a tool,
so it reads as hair and never as a pile of sausages."""
import numpy as np
from sdfkit import *
from heads import skull_sdf
HL = Field(37, sigma=6)

def _mixhex(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def hairline(P, tb):
    """Where the hair starts, as height by bearing round the head: tb = [(bearing 0 front..pi back, z), ...]."""
    th = np.arctan2(np.abs(P[0]), -P[1])
    return np.interp(th, [a for a, _ in tb], [b for _, b in tb]) - P[2]

MEN = [(0, .86), (.5, .83), (.85, .74), (1.1, .60), (1.32, .50), (1.52, .54), (1.8, .56), (2.2, .42), (3.15, .30)]

def shell(P, p, t, tb, k=.014, jag=.003):
    d = skull_sdf(P, p) - t
    return smax(d, hairline(P, tb) + jag * np.sin(np.arctan2(P[0], -P[1]) * 26), k)

def flow(c, big=26, a=.009, fine=104, b=.0022, warp=None):
    """Two scales of valley across a flow coordinate c: clumps, and the strands inside them."""
    w = 0 if warp is None else warp
    return a * np.abs(np.sin(c * big + w)) * -2 + a + b * np.sin(c * fine + w * 2)

def strands(P, ax=(1, 0, .3), f=70, a=.0045):
    return .6 * a * np.sin((P[0] * ax[0] + P[1] * ax[1] + P[2] * ax[2]) * f + 1.2 * HL(P, 2))

def tip(P, a, b, r1, r2=.008):
    return cone(P, a, b, r1, r2)

def curls(P, p):
    """A short crop of tight curls: lively, tidy enough for a client meeting, and his own."""
    d = shell(P, p, .03, [(0, .84), (.5, .82), (.9, .72), (1.15, .60), (1.35, .52), (1.8, .54), (2.3, .40), (3.15, .30)])
    d = smin(d, ell(P, (0, .02, .86), (.415, .44, .135)), .06)
    d = smax(d, hairline(P, MEN) - .03, .03)
    r = np.random.default_rng(5)
    # small whorls packed over the crown: texture you could press with a thumb, never a pile of sausages
    for i in range(190):
        th = r.uniform(0, 2 * np.pi)
        ph = np.arccos(r.uniform(.02, 1.0)) * 1.42
        R_ = .49 + r.uniform(0, .02)
        c = (R_ * np.sin(ph) * np.cos(th) * .96, .03 + R_ * np.sin(ph) * np.sin(th), .71 + .36 * np.cos(ph))
        if (c[1] < -.34 and c[2] < .86) or (c[1] < -.05 and c[2] < .80):
            continue
        rr = r.uniform(.034, .048)
        q = torus(P, c, rr * .7, rr * .62, rot=(r.uniform(-1.4, 1.4), r.uniform(-1.4, 1.4), r.uniform(-1.4, 1.4)))
        d = smin(d, q, .012)
    return d + .0015 * HL(P, 1.2)

def bob(P, p):
    """A sharp asymmetric bob: it cost more than her laptop, and it was worth it."""
    fw = p.get('fw', 1)
    outer = ell(P, (0, .07, .54), (.535 * fw, .535, .585))
    open_ = ell(P, (.0, -.48, .44), (.405 * fw, .40, .47))
    d = sub(outer, open_, .03)
    # the line of the cut: longer in front, on one side
    line = .20 + .07 * np.clip(P[1], -.4, .5) + .05 * np.cos(np.arctan2(P[0], P[1]) * 2) + .05 * np.clip(-P[0] * 2, -1, 1)
    d = smax(d, -(P[2] - line), .025)
    d = sub(d, ell(P, (.52, -.08, .40), (.10, .18, .24)), .04)
    az = np.arctan2(P[0], P[1] + .05)
    d = d + flow(az + .35 * HL(P, 1.5), 20, .007, 88, .0016) * smooth01(.86, .66, P[2])
    # the sweep of the fringe is one soft shape, combed across the brow
    sw = path(P, [(.34, -.16, 1.0), (.04, -.385, .975), (-.28, -.42, .83), (-.43, -.33, .66)], .07, .028, k=.06)
    d = smin(d, sw + flow(P[0] * .45 + P[2] * .9, 40, .0028, 130, .0009), .05)
    d = smin(d, path(P, [(.36, -.18, .98), (.45, -.27, .80), (.48, -.15, .62)], .05, .022, k=.03), .02)
    return d + .002 * HL(P, 1.2)

def side_sweep(P, p):
    """Short at the sides, swept across the top. Expensive haircut, nothing to hide. That's the point of him."""
    d = shell(P, p, .018, [(0, .87), (.5, .84), (.85, .75), (1.1, .62), (1.32, .52), (1.52, .55), (1.8, .56), (2.2, .42), (3.15, .30)], k=.012)
    top = smin(ell(P, (.0, -.03, .955), (.405, .465, .125)), ell(P, (.05, -.27, .985), (.335, .185, .105)), .10)
    top = smax(top, hairline(P, MEN) - .055, .03)
    sweep = P[0] * .9 + (P[1] + .5) * .3
    top = top + flow(sweep + .2 * HL(P, 1.8), 22, .0065, 96, .0015)
    d = smin(d, top, .03)
    # the parting, one stroke of the comb
    d = d + .009 * np.exp(-((P[0] - .25 + .05 * P[1]) / .012) ** 2) * (P[2] > .88) * (P[1] < .2)
    return d + .0012 * HL(P, 1.2)

def swept_back(P, p):
    """Thick hair swept up and back with a wave in it."""
    d = shell(P, p, .03, MEN)
    top = smin(ell(P, (-.01, -.02, .99), (.415, .47, .145)), ell(P, (.02, -.30, 1.03), (.35, .18, .125)), .09)
    top = smax(top, hairline(P, MEN) - .06, .03)
    d = smin(d, top, .05)
    side = smooth01(.22, .40, np.abs(P[0]))
    wave = .05 * np.sin(P[1] * 5.5 + 1.2)
    c = (P[0] + wave) * (1 - side) + (P[2] * .9 + .3 * np.sign(P[0])) * side
    d = d + flow(c + .2 * HL(P, 1.8), 24, .0085, 96, .0018) * smooth01(.5, .66, P[2] + .3 * (P[1] > .1))
    # the side part, drawn with one stroke of the tool
    d = d + .011 * np.exp(-((P[0] + .235 + .03 * P[1]) / .011) ** 2) * (P[2] > .9) * (P[1] < .18)
    # one forelock that won't stay put: the only thing out of place on him
    d = smin(d, path(P, [(.0, -.43, 1.07), (-.10, -.515, 1.0), (-.16, -.50, .885)], .034, .009, k=.015), .018)
    return d + .002 * HL(P, 1.2)

def low_bun(P, p):
    """A centre part, sleek as a verdict, to a low coiled bun with a gold pin."""
    d = shell(P, p, .022, [(0, .875), (.5, .84), (.85, .74), (1.1, .62), (1.32, .55), (1.8, .56), (2.2, .42), (3.15, .34)], k=.012, jag=0)
    d = d + .010 * np.exp(-(P[0] / .009) ** 2) * (P[2] > .7) * (P[1] < .25)
    # combed from the part down and back, into the bun
    c = np.arctan2(np.abs(P[0]) + .02, P[2] - .25)
    d = d + flow(c, 34, .0028, 130, .001)
    for s in (-1, 1):
        d = smin(d, path(P, [(s * .10, -.44, .92), (s * .38, -.30, .78), (s * .47, -.02, .60), (s * .26, .34, .50)], .05, .034, k=.03) + flow(P[2] + P[1] * .4, 60, .0026, 150, .0008), .022)
    a = np.arctan2(P[0], P[2] - .46)
    b = ell(P, (0, .52, .46), (.20, .17, .195)) + .0065 * np.sin(a * 3 + np.sqrt(P[0] ** 2 + (P[2] - .46) ** 2) * 62)
    d = smin(d, b, .02)
    return d + .0015 * HL(P, 1.2)

WOMEN = [(0, .875), (.5, .84), (.85, .74), (1.1, .62), (1.32, .55), (1.8, .56), (2.2, .42), (3.15, .34)]

def short(P, p):
    """A neat short cut: close at the sides, a little length on top, brushed forward."""
    d = shell(P, p, .02, MEN, k=.012)
    top = smax(ell(P, (0, -.03, .94), (.405, .455, .12)), hairline(P, MEN) - .05, .03)
    d = smin(d, top, .04)
    c = P[1] * .9 + .25 * np.abs(P[0]) + .2 * HL(P, 1.8)
    return d + flow(c, 30, .0045, 110, .0012) * smooth01(.55, .78, P[2]) + .0015 * HL(P, 1.2)

def long(P, p):
    """Long hair with a centre part, tucked behind the ears and falling to the shoulders."""
    fw = p.get('fw', 1)
    outer = ell(P, (0, .10, .47), (.525 * fw, .50, .66))
    d = sub(outer, ell(P, (0, -.50, .36), (.40 * fw, .42, .56)), .035)
    d = smax(d, -(P[2] + .16 - .10 * np.clip(-P[1], 0, .4)), .03)          # the ends: shoulder length, a little shorter in front
    d = smax(d, -(P[1] + .16 + .5 * np.maximum(.42 - P[2], 0)), .04)        # nothing hangs in front of the shoulders
    d = d + .006 * np.exp(-(P[0] / .008) ** 2) * (P[2] > .9) * (P[1] < .15)   # the part
    az = np.arctan2(P[0], P[1] + .05)
    d = d + flow(az * 1.6 + .3 * HL(P, 1.5), 16, .008, 76, .0018) * smooth01(.98, .72, P[2])
    for s_ in (-1, 1):
        d = smin(d, path(P, [(s_ * .06, -.42, .96), (s_ * .34, -.34, .84), (s_ * .47, -.10, .62), (s_ * .48, .05, .30)], .06, .04, k=.03), .03)
    return d + .002 * HL(P, 1.2)

def ponytail(P, p):
    """Swept back off the face into a high ponytail."""
    d = shell(P, p, .024, WOMEN, k=.012, jag=0)
    c = np.arctan2(np.abs(P[0]) + .02, P[2] - .2) + .6 * P[1]
    d = d + flow(c, 30, .0032, 120, .001)
    d = smin(d, ell(P, (0, .50, .70), (.085, .07, .085)), .03)               # the band
    tail = path(P, [(0, .52, .72), (0, .70, .56), (0, .70, .26), (0, .60, .02), (0, .55, -.10)], .10, .034, k=.05)
    d = smin(d, tail + flow(P[0] * 1.4 + .25 * HL(P, 1.6), 30, .006, 110, .0016), .03)
    return d + .0015 * HL(P, 1.2)

def headscarf(P, p):
    """A scarf wrapped close round the head and under the chin, the face framed in an oval."""
    fw = p.get('fw', 1)
    d = smin(skull_sdf(P, p) - .03, ell(P, (0, .07, .63), (.485 * fw, .50, .47)), .07)
    d = smin(d, cone(P, (0, .07, .34), (0, .09, -.10), .30, .36), .09)        # round the neck and into the collar
    d = sub(d, ell(P, (0, -.56, .43), (.325 * fw, .36, .40)), .03)            # the opening for the face
    d = smin(d, path(P, [(-.31 * fw, -.33, .78), (0, -.40, .90), (.31 * fw, -.33, .78)], .022), .02)   # the folded front edge
    # folds running back from the face and down from the crown
    d = d + .0045 * np.sin(P[2] * 30 + P[1] * 12 + 1.5 * HL(P, 1.4)) * smooth01(.10, .40, P[1] + .30) + .004 * np.sin(np.arctan2(P[0], P[1]) * 9) * (P[2] < .3)
    return d + .002 * HL(P, 1.2)

def bald(P, p):
    """No hair: the shadow of a close shave, a skin's thickness over the scalp."""
    return shell(P, p, .004, MEN, k=.006, jag=0)

STYLE = dict(curls=curls, bob=bob, side_sweep=side_sweep, swept_back=swept_back, low_bun=low_bun,
             short=short, long=long, ponytail=ponytail, headscarf=headscarf, bald=bald)
LOW = dict(long=-.36, ponytail=-.2, headscarf=-.13)     # how far below the neck pivot a style reaches
def make_hair(name, p, out):
    """Build the hair mesh for style p['hairstyle'] (see STYLE)."""
    style = p.get('hairstyle', name)
    fn = STYLE[style]
    hi = p.get('hairHi', p['hair'])
    paint = [(lambda P: HL(P, 1.6) * -.8 - .02, hi, .4, 0)]
    if style == 'bob' and p.get('hairTips'):
        paint.append((lambda P: P[2] - .40 + .03 * np.sin(P[0] * 9), p['hairTips'], .12, 0))
    if style == 'side_sweep':
        # the sides fade softly toward the skin
        paint.append((lambda P: (P[2] - .78) + .3 * np.maximum(P[1], 0), p.get('hairFade', '#5a4234'), .11, 0))
    if style == 'low_bun' and p.get('pin'):
        paint.append((lambda P: cone(P, (-.24, .56, .64), (.24, .44, .30), .014), p['pin'], .002, 1.0))

        def s2(P):
            return smin(fn(P, p), cone(P, (-.24, .56, .64), (.24, .44, .30), .011), .002)
        return mesh(s2, (-.7, -.72, .10), (.7, .78, 1.45), 150, paint=paint, base=p['hair'], path_=out, smooth=.5, cavity=.65)
    base = p['hair']
    if style == 'bald':
        paint, base = [], _mixhex(p['skin'], p['hair'], .14)
    lo = LOW.get(style, .10)
    return mesh(lambda P: fn(P, p), (-.72, -.72, lo), (.72, .86 if lo < .1 else .72, 1.5), 150 if lo >= .1 else 170, paint=paint, base=base, path_=out,
                smooth=.6, cavity=.75 if style not in ('headscarf', 'bald') else .4)


def make_acc(name, p, out):
    """Face accessories, listed in p['acc']: 'specs' (round glasses) and/or 'studs' (earrings).

    Each is a hard, separate object. Returns None when the character wears none.
    """
    acc = list(p.get('acc') or [])
    if not acc:
        return None
    es = p.get('es', .178)
    ez = p.get('ez', .5)
    fw = p.get('fw', 1)   # everything that sits on an ear follows the ear
    ex = .432 * fw + .026
    parts = []
    if 'specs' in acc:
        def specs(P):
            d = None
            for s in (-1, 1):
                r = torus(P, (s * es, -.492, ez + .005), .128, .0095)
                d = r if d is None else smin(d, r, .004)
                d = smin(d, path(P, [(s * (es + .126), -.49, ez + .03), (s * (.395 * fw + .022), -.26, ez + .05), (s * (.432 * fw + .004), -.03, ez + .02)], .008), .004)
            return smin(d, path(P, [(-.055, -.50, ez + .02), (0, -.525, ez + .045), (.055, -.50, ez + .02)], .009), .004)
        parts.append(specs)
    if 'studs' in acc:
        parts.append(lambda P: U(ell(P, (ex, .0, .385), (.024, .024, .024)), ell(P, (-ex, .0, .385), (.024, .024, .024)), k=.001))

    def sdf(P):
        d = parts[0](P)
        for f in parts[1:]:
            d = np.minimum(d, f(P))
        return d
    lo = (-ex - .06, -.62, .28) if 'specs' in acc else (-ex - .05, -.04, .345)
    hi = (ex + .06, .1, 1.08) if 'specs' in acc else (ex + .05, .04, .425)
    return mesh(sdf, lo, hi, 150 if 'specs' in acc else 200, base=p.get('accColor', '#2b2b30'), path_=out, smooth=.3, cavity=0)
