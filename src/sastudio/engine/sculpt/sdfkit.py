"""Signed-distance sculpting kit: every prop and puppet part is a real blended form, then marching-cubed.
Coordinates: x right, y depth (-y faces camera), z up. All functions accept P=(x,y,z) arrays of any shape."""
import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

def rotm(rx=0, ry=0, rz=0):
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx

def _loc(P, c, rot):
    x, y, z = P[0] - c[0], P[1] - c[1], P[2] - c[2]
    if rot is not None:
        R = rotm(*rot).T
        x, y, z = R[0, 0] * x + R[0, 1] * y + R[0, 2] * z, R[1, 0] * x + R[1, 1] * y + R[1, 2] * z, R[2, 0] * x + R[2, 1] * y + R[2, 2] * z
    return x, y, z

def ell(P, c, r, rot=None):
    x, y, z = _loc(P, c, rot)
    k0 = np.sqrt((x / r[0]) ** 2 + (y / r[1]) ** 2 + (z / r[2]) ** 2)
    k1 = np.sqrt((x / r[0] ** 2) ** 2 + (y / r[1] ** 2) ** 2 + (z / r[2] ** 2) ** 2) + 1e-6
    return k0 * (k0 - 1) / k1

def cone(P, a, b, r1, r2=None):
    r2 = r1 if r2 is None else r2
    a, b = np.array(a, float), np.array(b, float)
    ba = b - a
    pa = (P[0] - a[0], P[1] - a[1], P[2] - a[2])
    t = np.clip((pa[0] * ba[0] + pa[1] * ba[1] + pa[2] * ba[2]) / (ba @ ba + 1e-9), 0, 1)
    d = np.sqrt((pa[0] - ba[0] * t) ** 2 + (pa[1] - ba[1] * t) ** 2 + (pa[2] - ba[2] * t) ** 2)
    return d - (r1 + (r2 - r1) * t)

def rbox(P, c, b, r=.02, rot=None):
    x, y, z = _loc(P, c, rot)
    qx, qy, qz = np.abs(x) - b[0] + r, np.abs(y) - b[1] + r, np.abs(z) - b[2] + r
    return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2) + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0) - r

def torus(P, c, R, r, rot=None):
    x, y, z = _loc(P, c, rot)
    return np.sqrt((np.sqrt(x ** 2 + z ** 2) - R) ** 2 + y ** 2) - r

def path(P, pts, r1, r2=None, k=.02):
    """Smooth tube through points (a sculpted coil of clay). Radius tapers r1 -> r2."""
    r2 = r1 if r2 is None else r2
    n = len(pts) - 1
    d = None
    for i in range(n):
        ra, rb = r1 + (r2 - r1) * i / n, r1 + (r2 - r1) * (i + 1) / n
        di = cone(P, pts[i], pts[i + 1], ra, rb)
        d = di if d is None else smin(d, di, k)
    return d

def smin(a, b, k):
    h = np.clip(.5 + .5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)

def smax(a, b, k):
    return -smin(-a, -b, k)

def sub(a, b, k=.02):
    return smax(a, -b, k)

def U(*ds, k=.03):
    d = ds[0]
    for x in ds[1:]:
        d = smin(d, x, k)
    return d

def smooth01(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

class Field:
    """Deterministic low-frequency thumb-press lumps, sampled by trilinear lookup so verts and grid agree."""
    def __init__(s, seed, sigma=9, n=64):
        rng = np.random.default_rng(seed)
        f = gaussian_filter(rng.normal(size=(n, n, n)), sigma, mode='wrap')
        s.f = f / (np.abs(f).max() + 1e-9)
        s.n = n

    def __call__(s, P, scale=1.2):
        from scipy.ndimage import map_coordinates
        c = [((np.asarray(p) * scale) % 1.0) * s.n for p in P]
        return map_coordinates(s.f, c, order=1, mode='wrap')

def srgb2lin(h):
    h = h.lstrip('#')
    c = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.where(c > .04045, ((c + .055) / 1.055) ** 2.4, c / 12.92)

def mesh(sdf, bmin, bmax, res, paint=None, base='#ffffff', metal=0.0, path_=None, smooth=.6, cavity=.45, pad=None):
    """sdf(P)->d. paint: list of (region_fn(P)->signed, hex, softness, metal). Region<0 is inside.
    cavity: darkens creases, measured from the sculpt itself, like the wash a puppet painter brushes in."""
    bmin, bmax = np.array(bmin, float), np.array(bmax, float)
    h = (bmax - bmin).max() / res
    ax = [np.arange(bmin[i], bmax[i] + h, h, dtype=np.float32) for i in range(3)]
    X, Y, Z = np.meshgrid(*ax, indexing='ij')
    d = sdf((X, Y, Z)).astype(np.float32)
    if smooth:
        d = gaussian_filter(d, smooth)
    v, f, n, _ = marching_cubes(d, 0.0, spacing=(h, h, h))
    v = v + bmin
    f = f[:, ::-1]
    P = (v[:, 0], v[:, 1], v[:, 2])
    col = np.tile(srgb2lin(base), (len(v), 1)).astype(np.float32)
    met = np.full(len(v), metal, np.float32)
    for reg in (paint or []):
        fn, hx, soft, m = (tuple(reg) + (0.0,))[:4] if len(reg) == 3 else reg
        w = smooth01(soft, -soft, fn(P))[:, None] if soft > 0 else (fn(P) < 0)[:, None].astype(float)
        col = col * (1 - w) + srgb2lin(hx) * w
        met = met * (1 - w[:, 0]) + m * w[:, 0]
    if cavity:
        # sample the field a little way out along the surface normal: a crease reads closer than it should
        n = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)
        from scipy.ndimage import map_coordinates
        def field(q):
            return map_coordinates(d, [(q[:, i] - bmin[i]) / h for i in range(3)], order=1, mode='nearest')
        delta = max(h * 3, .022)
        if np.mean(field(v + n * delta)) < 0:
            n = -n
        ao = np.clip(field(v + n * delta) / delta, 0, 1) * .6 + np.clip(field(v + n * delta * 2.2) / (delta * 2.2), 0, 1) * .4
        k = (1 - cavity * (1 - ao) ** 1.2) * (1 - met * .9) + met * .9
        col = col * k[:, None]
    out = dict(v=v.astype(np.float32), f=f.astype(np.int32), c=np.c_[col, met].astype(np.float32))
    if path_:
        np.savez_compressed(path_, **out)
    return out
