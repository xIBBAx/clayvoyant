"""Sculpt and render the project's mark: a thumbprint pressed into clay whose whorl is an eye.

The mark is made the way the films are: a signed-distance form, marching-cubed, painted and lit by the clay engine.
A thumbprint is what stop motion leaves on everything it touches; it is also how a person is told from another,
and at its centre it looks back at you. Run from the repository root (needs the `clay` extra and Blender):

    python tools/make_clay_mark.py            # writes docs/media/brand/mark-clay-1024.png and the smaller sizes
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "sastudio" / "engine"
OUT = ROOT / "docs" / "media" / "brand"
TEAL, ORANGE, INK = "#1E4E5F", "#E07A3F", "#16191D"


def sculpt(path: Path) -> None:
    import numpy as np

    sys.path.insert(0, str(ENGINE / "sculpt"))
    from sdfkit import Field, ell, mesh, smax, smin, smooth01

    grain = Field(7, sigma=6)

    def ridges(P):
        """Thumbprint ridges on the face of the pebble: loops round a core, pushed off-centre like a real whorl."""
        x, z = P[0] + .05, P[2] + .03
        r = np.sqrt(x * x + (z * 1.12) ** 2)
        th = np.arctan2(z, x)
        phase = r * 46 + 1.15 * np.sin(th * 1 + .6) + .9 * grain(P, 1.3) + 1.0 * th      # a slow spiral (one whole turn, so it meets itself), never perfect circles
        face = smooth01(.0, -.12, P[1]) * smooth01(1.02, .86, np.sqrt(P[0] ** 2 + P[2] ** 2)) * smooth01(.2, .3, r)
        return .017 * np.sin(phase) * face

    def sdf(P):
        d = ell(P, (0, 0, 0), (1.0, .36, 1.0))                                    # the pebble
        d = smax(d, -ell(P, (0, -.62, 0), (.92, .34, .92)), .1)                      # the press of a thumb in its face
        d = d + ridges(P)
        d = smin(d, ell(P, (-.05, -.21, -.03), (.215, .09, .215)), .05)              # the iris, raised in the middle of the whorl
        d = smax(d, -ell(P, (-.05, -.31, -.03), (.092, .06, .092)), .02)             # the pupil, pressed in
        return d + .004 * grain(P, 2.2)

    paint = [
        (lambda P: ell(P, (-.05, -.24, -.03), (.225, .16, .225)), ORANGE, .012, 0),
        (lambda P: ell(P, (-.05, -.30, -.03), (.10, .1, .10)), INK, .008, 0),
        (lambda P: ell(P, (-.012, -.285, .012), (.03, .05, .03)), "#fff4e0", .004, 0),   # the light in the eye
    ]
    mesh(sdf, (-1.12, -.5, -1.12), (1.12, .5, 1.12), 300, paint=paint, base=TEAL, path_=str(path), smooth=.7, cavity=.62)


BLENDER = r'''
import json, math, sys
import bpy
job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
sys.path.insert(0, job["engine"])
bpy.ops.wm.read_factory_settings(use_empty=True)
from claymat import clayv, load, obj
s = bpy.context.scene
s.render.engine = "CYCLES"
s.cycles.samples = 256
s.cycles.use_denoising = True
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            s.cycles.device = "GPU"
            break
    except (TypeError, ValueError):
        pass
s.render.resolution_x = s.render.resolution_y = job["size"]
s.render.film_transparent = True
s.render.image_settings.file_format = "PNG"
s.render.image_settings.color_mode = "RGBA"
s.view_settings.view_transform = "AgX"
s.view_settings.look = "AgX - Medium High Contrast"
w = bpy.data.worlds.new("w"); s.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (.9, .82, .72, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = .32
o = obj("mark", load(job["mesh"], clayv("mark", .5, .08, 1.0, .25, cgrain=.03)))
o.rotation_euler = (math.radians(-9), 0, math.radians(7))
def light(loc, e, size, col):
    d = bpy.data.lights.new("l", "AREA"); d.energy, d.size, d.color = e, size, col
    l = bpy.data.objects.new("l", d); bpy.context.scene.collection.objects.link(l); l.location = loc
    from mathutils import Vector
    l.rotation_euler = (Vector((0, 0, 0)) - l.location).to_track_quat("-Z", "Y").to_euler()
light((-3.2, -4.2, 3.6), 900, 2.2, (1, .9, .78))     # a low warm key from the upper left: it rakes the ridges
light((3.6, -2.6, -1.0), 160, 4, (.7, .82, 1))       # cool fill
light((1.5, 2.5, 2.5), 500, 2, (1, .75, .5))         # rim
cam_d = bpy.data.cameras.new("c"); cam_d.type = "ORTHO"; cam_d.ortho_scale = 2.42
cam = bpy.data.objects.new("c", cam_d); bpy.context.scene.collection.objects.link(cam)
cam.location = (0, -6, 0); cam.rotation_euler = (math.radians(90), 0, 0); s.camera = cam
s.render.filepath = job["out"]
bpy.ops.render.render(write_still=True)
print("MARK done")
'''


def main() -> None:
    from PIL import Image

    sys.path.insert(0, str(ROOT / "src"))
    from sastudio.stopmotion import find_blender

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sas-mark-") as tmp:
        npz = Path(tmp) / "mark.npz"
        print("sculpting ...")
        sculpt(npz)
        script = Path(tmp) / "render.py"
        script.write_text(BLENDER, "utf-8")
        big = OUT / "mark-clay-1024.png"
        job = Path(tmp) / "job.json"
        job.write_text(json.dumps({"engine": str(ENGINE / "clay"), "mesh": str(npz), "out": str(big), "size": 1024}), "utf-8")
        exe, _ = find_blender()
        print("rendering ...")
        res = subprocess.run([exe, "-b", "--factory-startup", "-P", str(script), "--", str(job)], capture_output=True, text=True, check=False)
        if "MARK done" not in res.stdout:
            raise SystemExit(res.stdout[-1500:] + res.stderr[-500:])
    im = Image.open(big).convert("RGBA")
    for size in (512, 256, 64):
        im.resize((size, size), Image.LANCZOS).save(OUT / f"mark-clay-{size}.png", optimize=True)
    im.save(big, optimize=True)
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("mark-clay-*.png"))))


if __name__ == "__main__":
    main()
