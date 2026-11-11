"""Build clay character assets from parameter files. Runs in normal Python (not Blender).

    python engine/sculpt/build.py <characters folder or .json> <output rig folder> [ids] [--jobs N]

Needs numpy, scipy and scikit-image (`pip install security-awareness-studio[clay]`).
Each character file is JSON: {"head": {...}, "body": {..., "torso": "knit_vest|blazer|suit_jacket"}}.
Output: <rig>/<id>/*.npz and <rig>/meta.json, which engine/clay/puppet.py loads inside Blender.
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'clay'))  # faceops and handrig are shared with the Blender side
from heads import VIS, eye_y, make_brow, make_eye, make_head, make_lids, make_teeth, surface_y  # noqa: E402
from bodies import HAND, blazer, knit_vest, make_hand, make_hand_rig, make_shoe, mesh, suit_jacket  # noqa: E402
import hair as H  # noqa: E402

TORSO = dict(knit_vest=knit_vest, blazer=blazer, suit_jacket=suit_jacket)
FACE = ('es', 'ez', 'eye', 'W', 'mz', 'mcurve', 'mh', 'browz', 'browy', 'eyey', 'lidU', 'lidL', 'toe')
HEAD_DEFAULTS = dict(es=.176, ez=.50, eye=.098, W=.108, mz=.198, mcurve=.012, mh=.0095, browz=.648, lipU=.028,
                     lipL=.036, lidU=-11, lidL=9, irisr=.58)
CAST = {}
ROOT = None


def _mix(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def load_cast(src):
    files = [src] if src.endswith('.json') else sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith('.json'))
    cast = {}
    for f in files:
        cid = os.path.splitext(os.path.basename(f))[0]
        data = json.load(open(f, encoding='utf-8'))
        head = dict(HEAD_DEFAULTS)
        head.update(data['head'])
        body = dict(data['body'])
        body.setdefault('skin', head['skin'])
        if body.get('torso') not in TORSO:
            raise SystemExit(f'{cid}: body.torso must be one of {sorted(TORSO)}')
        if head.get('hairstyle') not in H.STYLE:
            raise SystemExit(f'{cid}: head.hairstyle must be one of {sorted(H.STYLE)}')
        head.setdefault('lidc', _mix(head['skin'], head['skinD'], .35))
        head.setdefault('browc', _mix(head['hair'], head['skinD'], .22))
        head['browy'] = surface_y(head, head['es'], head['browz']) - .004
        head['eyey'] = eye_y(head['eye'])
        head.setdefault('toe', .17)
        cast[cid] = dict(head=head, body=body)
    return cast


def job(a):
    kind, name, *r = a
    d = os.path.join(ROOT, name) + '/'
    os.makedirs(d, exist_ok=True)
    p, c = CAST[name]['head'], CAST[name]['body']
    t = time.time()
    if kind == 'head':
        make_head(p, d + 'head.npz'); make_eye(p, d + 'eye.npz'); make_lids(p, d + 'lidu.npz', d + 'lidl.npz')
        make_brow(p, d + 'browL.npz', 1); make_brow(p, d + 'browR.npz', -1); make_teeth(p, d)
    elif kind == 'hair':
        H.make_hair(name, p, d + 'hair.npz')
        H.make_acc(name, p, d + 'acc.npz')
    elif kind == 'torso':
        sdf, paint, base = TORSO[c['torso']](c)
        mesh(sdf, (-.82, -.62, -.34), (.82, .62, c['L'] + .34), 215, paint=paint, base=base, path_=d + 'torso.npz',
             smooth=.5, cavity=.55)
    elif kind == 'hand':
        make_hand(c, r[0], r[1], d + f'h_{r[0]}_{"R" if r[1] > 0 else "L"}.npz')
    elif kind == 'handrig':
        make_hand_rig(c, r[0], d + f'hand_{"R" if r[0] > 0 else "L"}.npz')
    elif kind == 'shoe':
        make_shoe(c, d + 'shoe.npz')
    return f'{name}:{kind}:{r} {round(time.time() - t, 1)}s'


def init(cast, root):
    global CAST, ROOT
    CAST, ROOT = cast, root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('characters')
    ap.add_argument('rig')
    ap.add_argument('ids', nargs='?', default='all')
    ap.add_argument('--jobs', type=int, default=2)
    a = ap.parse_args()
    cast = load_cast(a.characters)
    root = os.path.abspath(a.rig)
    os.makedirs(root, exist_ok=True)
    names = list(cast) if a.ids == 'all' else a.ids.split(',')
    jobs = []
    for n in names:
        jobs += [('head', n), ('hair', n), ('torso', n), ('shoe', n)]
        jobs += [('hand', n, h, s) for h in HAND for s in (1, -1)]
        jobs += [('handrig', n, s) for s in (1, -1)]
    t = time.time()
    with Pool(a.jobs, initializer=init, initargs=(cast, root)) as P:
        for o in P.imap_unordered(job, jobs):
            print(o, flush=True)
    meta_path = os.path.join(root, 'meta.json')
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    for n in names:
        meta[n] = {k: v for k, v in cast[n]['body'].items() if isinstance(v, (int, float, str))}
        meta[n]['face'] = {k: cast[n]['head'][k] for k in FACE}
    json.dump(meta, open(meta_path, 'w'), indent=1)
    print('built', len(jobs), 'assets in', round(time.time() - t, 1), 's')


if __name__ == '__main__':
    main()
