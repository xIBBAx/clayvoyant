"""Check that nothing solid passes through anything else in a filmed clay project.

    python tools/check_contacts.py examples/the-fast-one              # every shot of the last filming
    python tools/check_contacts.py examples/the-fast-one --every 2    # check more drawings (slower)

For each shot's job (`.studio/work/clay/*/job.json`, written when the project was filmed), Blender poses the scene
exactly as the film does and intersects every part of every character with every object of the set and with every
other character (triangle against triangle). Touching is fine; any intersection is reported with the frame, the part
and what it is inside. Exit status 1 when anything intersects. Needs Blender, like filming.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

PROBE = r'''
import sys, bpy
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
args = sys.argv[sys.argv.index('--') + 1:]
FILM, JOBF, EVERY = args[0], args[1], int(args[2])
sys.argv = [sys.argv[0], '--', JOBF]
src = open(FILM).read().split('# ------------------------------------------------------------------ film it')[0]
g = {'__file__': FILM, '__name__': '__contacts__'}
exec(compile(src, FILM, 'exec'), g)
PERF = g['PERF']
owner = {o.name: n for n, a in PERF.actors.items() for o in a.P.parts if o.type == 'MESH'}

def tree(o, dg):
    ev = o.evaluated_get(dg); me = ev.to_mesh(); M = o.matrix_world
    vs = [M @ v.co for v in me.vertices]; ps = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return BVHTree.FromPolygons(vs, ps) if ps else None

def box(o):
    bb = [o.matrix_world @ V(c) for c in o.bound_box]
    return (V((min(p.x for p in bb), min(p.y for p in bb), min(p.z for p in bb))),
            V((max(p.x for p in bb), max(p.y for p in bb), max(p.z for p in bb))))

for f in g['FRAMES'][::EVERY]:
    PERF.pose(f); g['door_at'](f); g['held_at'](f)
    if 'dress_at' in g:
        g['dress_at'](f)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    live = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render and o.visible_get()]
    boxes = {o.name: box(o) for o in live}
    cast = [o for o in live if o.name in owner]
    rest = [o for o in live if o.name not in owner and o.name.split('.')[0] not in ('steam', 'wing')]
    built = {}
    def T(o):
        if o.name not in built:
            built[o.name] = tree(o, dg)
        return built[o.name]
    for p in cast:
        pb = boxes[p.name]
        for o in rest + [q for q in cast if owner[q.name] != owner[p.name] and q.name > p.name]:
            ob = boxes[o.name]
            if not all(pb[0][i] <= ob[1][i] and ob[0][i] <= pb[1][i] for i in range(3)):
                continue
            a, b = T(p), T(o)
            if a and b:
                n = len(a.overlap(b))
                if n:
                    print(f'CONTACT f={f} {n} {p.name} {o.name}', flush=True)
print(f'CHECKED {len(g["FRAMES"][::EVERY])}', flush=True)
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project")
    ap.add_argument("--every", type=int, default=6, help="check every Nth drawing of each shot (default 6)")
    ap.add_argument("--shots", default="", help="only shots whose folder name contains this")
    a = ap.parse_args()
    from sastudio.render import clay
    from sastudio.stopmotion import find_blender

    exe, _ = find_blender()
    film = str(clay.ENGINE.joinpath("clay").joinpath("film.py"))
    jobs = sorted(p for p in Path(a.project, ".studio", "work", "clay").glob("*/job.json") if a.shots in p.parent.name)
    jobs = [j for j in jobs if not j.parent.name.endswith("_silent")]
    if not jobs:
        print(f"No filmed shots in {a.project}: film it first (sastudio film {a.project}).")
        return 2
    total, kinds, frames = 0, Counter(), 0
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp, "contacts.py")
        probe.write_text(PROBE, "utf-8")
        for j in jobs:
            out = subprocess.run([exe, "-b", "--factory-startup", "-P", str(probe), "--", film, str(j), str(a.every)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            hits = re.findall(r"^CONTACT f=(\d+) (\d+) (\S+) (\S+)$", out, re.M)
            checked = re.search(r"^CHECKED (\d+)", out, re.M)
            frames += int(checked.group(1)) if checked else 0
            for f, n, part, other in hits:
                kinds[(re.sub(r"^[^_]+_", "", part), re.sub(r"\.\d+$", "", re.sub(r"^[^_]+_(?=\w)", "", other)))] += 1
                print(f"  {j.parent.name}  frame {f}: {part} inside {other} ({n} triangle pairs)")
            total += len(hits)
            print(f"{j.parent.name}: {len(hits)} intersection(s)" + ("" if checked else "  (Blender did not finish)"))
    print(f"\n{len(jobs)} shots, {frames} drawings checked: {total} intersection(s).")
    for (part, other), n in kinds.most_common(12):
        print(f"  {n:4}  {part} inside {other}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
