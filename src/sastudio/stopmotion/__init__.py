"""Clay stop-motion renderer (experimental): films one planned shot in Blender.

This is the first working piece of the clay-motion renderer described in docs/CLAY_MOTION.md.
It builds a Blender job from the project, the shot plan (sastudio.direction) and the characters'
`look.design`, runs Blender in the background and encodes the drawings, animated on twos, into a
clip. What it does today: clay characters on a branded set, lighting presets, the planned camera
and its move, replacement mouths following the words, blinks, eyelines, breathing and arm and head
gestures. Not yet: walking, sitting, props in hands, real audio, and assembly into the full film.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from .. import direction as D
from ..errors import ConfigError, RenderError, ToolMissing
from ..render import figures

FPS = 24
SCENE_VERSION = "1"  # bump when the Blender scene builder changes what it draws
PRESETS = {"draft": (960, 540, 8), "preview": (1280, 720, 16), "final": (1920, 1080, 48)}
NOT_YET = {"sit_down", "stand_up", "walk_in", "walk_out"}
HEAD_Z, CHEST_Z, BODY_Z = 0.312, 0.215, 0.17
SIDES_X = {"left": [-0.13, -0.29], "right": [0.13, 0.29]}
# frame height (m) and the height the camera aims at: room above the hair, never cutting the head
FRAME_H = {"establishing": None, "wide": 0.50, "medium": 0.27, "two_shot": 0.31, "over_shoulder": 0.22,
           "close_up": 0.15, "extreme_close_up": 0.075, "reaction": 0.15, "insert": 0.09}
# faces sit in the upper half of the frame, so subtitles never cover a mouth
AIM_Z = {"wide": 0.19, "medium": 0.255, "two_shot": 0.26, "close_up": 0.305, "reaction": 0.305,
         "extreme_close_up": 0.300, "over_shoulder": 0.300}


def find_blender() -> tuple[str, bool]:
    """Blender to run, and whether it is a Windows build used from WSL. SASTUDIO_BLENDER wins."""
    exe = os.environ.get("SASTUDIO_BLENDER") or shutil.which("blender") or shutil.which("blender.exe")
    if not exe:
        raise ToolMissing("The clay stop-motion renderer needs Blender 4.2 or newer.",
                          "Install it from blender.org and put it on PATH, or set SASTUDIO_BLENDER to blender's path. "
                          "On WSL2, point SASTUDIO_BLENDER at the Windows blender.exe: its EEVEE uses the GPU.")
    return exe, exe.lower().endswith(".exe") and os.name != "nt"


def _winpath(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True, check=True).stdout.strip()


def _vfov(lens: float) -> float:
    return 2 * math.atan((36 * 9 / 16) / 2 / lens)


def _positions(plan: D.ScenePlan) -> dict[str, tuple[tuple[float, float, float], float]]:
    used = {"left": 0, "right": 0}
    out = {}
    for cid, side in plan.sides.items():
        xs = SIDES_X[side]
        x = xs[min(used[side], len(xs) - 1)]
        used[side] += 1
        out[cid] = ((x, 0.18, 0.0), 0.42 if side == "left" else -0.42)  # cheated toward the camera
    return out


def camera_keys(shot: D.Shot, pos: dict, frames: int) -> dict:
    lens = shot.lens or D.SHOTS[shot.camera]["lens"]
    if shot.camera == "establishing":
        start, aim = (0.0, -1.05, 0.46), (0.0, 0.25, 0.20)
        end = start
    else:
        who = [c for c in shot.who if c in pos] or list(pos)[:1]
        heads = [Vector3(pos[c][0][0], pos[c][0][1], HEAD_Z) for c in who]
        aim_z = AIM_Z.get(shot.camera, HEAD_Z)
        cx = sum(h.x for h in heads) / len(heads)
        cy = sum(h.y for h in heads) / len(heads)
        aim = (cx, cy, aim_z)
        dist = (FRAME_H[shot.camera] / 2) / math.tan(_vfov(lens) / 2)
        if shot.camera == "over_shoulder" and len(who) == 2:
            sp, ls = pos[who[0]][0], pos[who[1]][0]
            dx, dy = sp[0] - ls[0], sp[1] - ls[1]
            n = math.hypot(dx, dy) or 1.0
            aim = (sp[0], sp[1], AIM_Z["over_shoulder"])
            back = dist + n
            side = 1 if ls[0] > sp[0] else -1
            start = (sp[0] - dx / n * back + side * 0.025, sp[1] - dy / n * back - 0.30, HEAD_Z + 0.01)
        else:
            # stand on the side the character is looking towards, for a three-quarter view of the face
            facing = sum(pos[c][1] for c in who) / len(who)
            ang = facing * (0.75 if len(who) == 1 else 0.35)
            start = (cx + math.sin(ang) * dist, cy - math.cos(ang) * dist, aim_z + 0.01)
        height = {"low": -0.05, "high": 0.07}.get(shot.height, 0.0)
        start = (start[0], start[1], start[2] + height)
        end = start
        if shot.move in ("push_in", "pull_out"):
            k = (0.90 if shot.camera in ("close_up", "extreme_close_up", "reaction") else 0.80) if shot.move == "push_in" \
                else 1.22
            end = tuple(a + (s - a) * k for s, a in zip(start, aim, strict=True))
        elif shot.move == "orbit":
            ang = 0.18
            dx, dy = start[0] - aim[0], start[1] - aim[1]
            end = (aim[0] + dx * math.cos(ang) - dy * math.sin(ang), aim[1] + dx * math.sin(ang) + dy * math.cos(ang), start[2])
    return {"lens": lens, "fstop": shot.fstop, "focus": shot.focus if shot.camera != "establishing" else None,
            "keys": {1: [start, aim], max(1, frames): [end, aim]}}


class Vector3:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


REST = {"left": {"shoulder": [0.0, 0.10, 0.0], "elbow": [-0.12, 0.0, 0.0]},
        "right": {"shoulder": [0.0, -0.10, 0.0], "elbow": [-0.12, 0.0, 0.0]}}
POSES = {  # arm targets for gestures that hold a pose (left/right shoulder and elbow, Euler radians)
    "point": {"right": {"shoulder": [-1.25, -0.10, 0.0], "elbow": [-0.15, 0.0, 0.0]}},
    "wave": {"right": {"shoulder": [-0.20, -2.30, 0.0], "elbow": [0.0, -0.35, 0.0]}},
    "open_palms": {"left": {"shoulder": [-0.25, 0.30, 0.0], "elbow": [-1.35, 0.0, 0.0]},
                   "right": {"shoulder": [-0.25, -0.30, 0.0], "elbow": [-1.35, 0.0, 0.0]}},
    "shrug": {"left": {"shoulder": [-0.15, 0.55, 0.0], "elbow": [-1.20, 0.0, 0.0]},
              "right": {"shoulder": [-0.15, -0.55, 0.0], "elbow": [-1.20, 0.0, 0.0]}},
    "thumbs_up": {"right": {"shoulder": [-0.55, -0.15, 0.0], "elbow": [-1.45, 0.0, 0.0]}},
    "hand_on_chin": {"right": {"shoulder": [-0.55, 0.25, 0.0], "elbow": [-2.35, 0.0, 0.0]}},
    "arms_folded": {"left": {"shoulder": [-0.35, -0.15, 0.0], "elbow": [-1.85, 0.0, 0.0]},
                    "right": {"shoulder": [-0.35, 0.15, 0.0], "elbow": [-1.85, 0.0, 0.0]}},
    "phone_to_ear": {"left": {"shoulder": [-0.45, 0.45, 0.0], "elbow": [-2.45, 0.0, 0.0]}},
    "typing": {"left": {"shoulder": [-0.60, 0.05, 0.0], "elbow": [-0.95, 0.0, 0.0]},
               "right": {"shoulder": [-0.60, -0.05, 0.0], "elbow": [-0.95, 0.0, 0.0]}},
}


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def tracks(project, scene, shot: D.Shot, pos: dict, step: int) -> tuple[dict, int]:
    """Per-drawing acting for everyone in the scene: mouth, blink, head, breath, arms."""
    lines = [ln for ln in scene.lines if ln.id in shot.lines]
    for ln in lines:
        for g in ln.act or []:
            if g in NOT_YET:
                raise ConfigError(f"Line {ln.id}: the clay renderer cannot film '{g}' yet.",
                                  "Remove it from `act`; walking and sitting are planned (docs/CLAY_MOTION.md).")
    spans, t = [], 0.35
    for ln in lines:
        dur = D._estimate(ln)
        spans.append((ln, t, t + dur))
        t += dur + 0.25
    frames = max(int(round((t + 0.3) * FPS)), int(shot.seconds * FPS))
    out: dict = {}
    for cid in pos:
        h = int(hashlib.sha256(cid.encode()).hexdigest()[:6], 16)
        body_yaw = pos[cid][1]
        tr = {}
        for f in range(1, frames + 1, step):
            ts = (f - 1) / FPS
            cur = next(((ln, a, b) for ln, a, b in spans if a <= ts < b), None)
            speaker = cur[0].who if cur else (lines[-1].who if lines else None)
            mouth = 0
            if cur and cur[0].who == cid:
                mouth = figures.mouth_for(cur[0].say or "", (ts - cur[1]) / max(0.01, cur[2] - cur[1]))
            look_at = speaker if speaker and speaker != cid else ((cur[0].to if cur else None) or
                                                                   next((c for c in pos if c != cid), None))
            yaw = 0.0
            if look_at and look_at in pos:
                dx = pos[look_at][0][0] - pos[cid][0][0]
                yaw = max(-0.55, min(0.55, (0.6 if dx > 0 else -0.6) - body_yaw))
            pitch = 0.035 * math.sin(ts * 7.0 + h) if mouth else 0.0
            roll = 0.03 * math.sin(ts * 0.8 + h)
            arms = json.loads(json.dumps(REST))
            for ln, a, b in spans:
                if ln.who != cid:
                    continue
                for g in ln.act or []:
                    info = D.GESTURES[g]
                    if info["kind"] == "once":
                        k = _ease((ts - a - 0.15) / 0.3) * (1 - _ease((ts - a - 0.15 - info["seconds"]) / 0.3))
                    else:
                        k = _ease((ts - a) / 0.35) * (1 - _ease((ts - b) / 0.35))
                    if k <= 0:
                        continue
                    if g == "nod":
                        pitch += 0.20 * k * math.sin(min(1.0, (ts - a) / info["seconds"]) * math.pi)
                    elif g == "shake_head":
                        yaw += 0.25 * k * math.sin((ts - a) * 14)
                    elif g == "tilt_head":
                        roll += 0.18 * k
                    elif g in ("turn_to", "lean_in"):
                        pitch += 0.08 * k
                    for side, pose in POSES.get(g, {}).items():
                        for joint in ("shoulder", "elbow"):
                            arms[side][joint] = [r + (p - r) * k for r, p in zip(arms[side][joint], pose[joint], strict=True)]
                    if g == "wave":
                        arms["right"]["elbow"][1] += 0.35 * k * math.sin((ts - a) * 12)
                    if g == "typing":
                        for side in ("left", "right"):
                            arms[side]["elbow"][0] += 0.06 * k * math.sin((ts - a) * 20 + (side == "left"))
            blink = f > 6 and (f + h - h % 2) % (70 + h % 37 - h % 37 % 2) < 4
            tr[f] = {"mouth": mouth, "blink": blink, "head": [pitch, yaw, roll],
                     "breath": 1.0 + 0.012 * math.sin(ts * 2 * math.pi / 3.6 + h), "arms": arms}
        out[cid] = tr
    return out, frames


def build_job(project, plan: D.ScenePlan, shot_index: int, preset: str, out_dir: Path) -> dict:
    scene = next(s for s in project.scenes if s.id == plan.scene)
    shot = plan.shots[shot_index]
    pos = _positions(plan)
    w, h, samples = PRESETS[preset]
    step = 2
    trk, frames = tracks(project, scene, shot, pos, step)
    chars = [_char_job(project, cid, p, yaw) for cid, (p, yaw) in pos.items()]
    st = D.SETS.get(plan.set, D.SETS["office"])
    logo = project.org.get("logo")
    return {"palette": project.org.get("palette") or {}, "lighting": D.LIGHTING[plan.lighting],
            "props": st["props"], "furniture": ["desk"] if st["seats"] else [],
            "logo": str(project.path(logo, "organization.logo")) if logo else None,
            "characters": chars, "camera": camera_keys(shot, pos, frames), "tracks": trk,
            "frame_start": 1, "frame_end": frames, "step": step, "width": w, "height": h, "samples": samples,
            "aliases": _aliases(), "out": str(out_dir)}


def _aliases() -> dict:
    from .. import models

    return {"bones": models.BONES, "shapes": models.SHAPES}


def _char_job(project, cid: str, pos=(0.0, 0.0, 0.0), yaw: float = 0.0) -> dict:
    """One character for the Blender job: its clay design, or the model it was given."""
    if cid not in project.characters:
        raise ConfigError(f"No character '{cid}'.", "List them with `sastudio characters`.")
    look = project.characters[cid].look or {}
    c = {"id": cid, "pos": list(pos), "yaw": yaw, "design": figures.normalize(look.get("design"), look.get("preset"))}
    if look.get("model"):
        path = project.path(look["model"], f"characters.{cid}.look.model")
        if not path.is_file():
            raise ConfigError(f"{cid}'s model {look['model']} is missing.", "Import it again with `sastudio model import`.")
        c["model"] = str(path)
        c["model_yaw"] = float(look.get("model_yaw") or 0.0)
        c["model_sha"] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]  # a changed file re-films the shot
    return c


def _rest_track() -> dict:
    return {1: {"mouth": 0, "blink": False, "head": [0.0, 0.0, 0.0], "breath": 1.0,
                "arms": json.loads(json.dumps(REST))}}


def _run_blender(job: dict, work: Path, log=print, marker: str = "STOPMOTION done") -> str:
    """Run the Blender scene builder on a job; paths are converted for a Windows Blender under WSL."""
    exe, wsl_win = find_blender()
    conv = _winpath if wsl_win else str
    for key in ("out", "logo", "export", "save_blend"):
        if job.get(key):
            job[key] = conv(Path(job[key]))
    for c in job["characters"]:
        if c.get("model"):
            c["model"] = conv(Path(c["model"]))
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.json").write_text(json.dumps(job), "utf-8")
    with resources.as_file(resources.files("sastudio.stopmotion").joinpath("blender_scene.py")) as script:
        cmd = [exe, "-b", "--factory-startup", "-P", conv(Path(script)), "--", conv(work / "job.json")]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if marker not in res.stdout:
        raise RenderError("Blender did not finish:\n" + (res.stdout + res.stderr).strip()[-1500:])
    return res.stdout


def render_portrait(project, cid: str, *, samples: int = 32, log=print) -> Path:
    """A still of one character (clay or imported model) for the cards styles; sets `look.portrait`.

    Saved as assets/characters/<id>_3d.png (never over a portrait someone made), cropped to the figure
    on a transparent background, like the bundled clay portraits.
    """
    from PIL import Image

    from .. import models

    c = _char_job(project, cid, (0.0, 0.0, 0.0), 0.30)
    aim, lens = (0.0, 0.0, 0.215), 50.0
    dist = (0.36 / 2) / math.tan(_vfov(lens) / 2)
    cam = (math.sin(0.30) * dist * 0.4, -dist, 0.24)
    job = {"mode": "portrait", "palette": project.org.get("palette") or {}, "lighting": D.LIGHTING["soft_studio"],
           "props": [], "furniture": [], "logo": None, "characters": [c],
           "camera": {"lens": lens, "fstop": 8.0, "focus": cid, "keys": {1: [cam, aim]}},
           "tracks": {cid: _rest_track()}, "frame_start": 1, "frame_end": 1, "step": 1,
           "width": 900, "height": 1200, "samples": samples, "aliases": _aliases()}
    work = project.root / ".studio" / "work" / "portraits" / cid
    shutil.rmtree(work, ignore_errors=True)
    job["out"] = str(work / "frames")
    (work / "frames").mkdir(parents=True)
    log(f"Rendering a portrait of {cid}...")
    _run_blender(job, work, log)
    shots = sorted((work / "frames").glob("*.png"))
    if not shots:
        raise RenderError("Blender wrote no portrait.")
    im = Image.open(shots[0]).convert("RGBA")
    bb = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not bb:
        raise RenderError(f"The portrait of {cid} is empty: the model may be too small, hidden or facing away.",
                          "Check it with `sastudio model inspect`, or set `--yaw` when importing.")
    im = im.crop((max(0, bb[0] - 24), max(0, bb[1] - 24), min(im.width, bb[2] + 24), min(im.height, bb[3] + 24)))
    im = im.resize((max(1, int(im.width * 820 / im.height)), 820), Image.LANCZOS)
    rel = f"assets/characters/{cid}_3d.png"
    target = project.root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, optimize=True)
    yml = project.root / "studio.yaml"
    yml.write_text(models._set_look(yml.read_text("utf-8"), cid, {"portrait": rel}), "utf-8")
    return target


EXPORT_FORMATS = (".glb", ".fbx", ".obj", ".blend")


def export_character(project, cid: str, out: Path, log=print) -> Path:
    """Write one character (its clay figure, or its model as fitted to the cast) to GLB, FBX, OBJ or .blend."""
    out = Path(out).resolve()
    if out.suffix.lower() not in EXPORT_FORMATS:
        raise ConfigError(f"Cannot export to {out.suffix or 'a file without an extension'}.",
                          "Use .glb (most tools and the web), .fbx (game engines), .obj (any 3D tool) or .blend.")
    job = {"mode": "export", "characters": [_char_job(project, cid)], "export": str(out), "aliases": _aliases()}
    out.parent.mkdir(parents=True, exist_ok=True)
    work = project.root / ".studio" / "work" / "export" / cid
    shutil.rmtree(work, ignore_errors=True)
    log(f"Exporting {cid} to {out.name}...")
    _run_blender(job, work, log, marker="STOPMOTION exported")
    if not out.is_file() or out.stat().st_size == 0:
        raise RenderError(f"Blender did not write {out}.")
    return out


def render_shot(project, scene_id: str, shot_index: int, preset: str, out: Path, log=print,
                blend: Path | None = None) -> Path:
    """Film one planned shot and encode it (on twos) into `out` (an .mp4); `blend` also saves it as a .blend."""
    plans = {p.scene: p for p in D.plan(project)}
    if scene_id not in plans:
        raise ConfigError(f"No enabled scene '{scene_id}'.", "List scenes with `sastudio scenes`.")
    plan = plans[scene_id]
    if not 0 <= shot_index < len(plan.shots):
        raise ConfigError(f"Scene {scene_id} has {len(plan.shots)} shots.", "See them with `sastudio direct`.")
    if plan.shots[shot_index].camera == "insert":
        raise ConfigError("Insert shots (props and cards) are not filmed in clay yet.", "Choose another shot.")
    job = build_job(project, plan, shot_index, preset, Path("frames"))
    digest = hashlib.sha256(json.dumps({k: v for k, v in job.items() if k != "out"}, sort_keys=True,
                                       default=str).encode() + SCENE_VERSION.encode()).hexdigest()[:16]
    cached = project.root / ".studio" / "cache" / "stopmotion" / f"{digest}.mp4"
    if cached.is_file() and cached.stat().st_size > 0 and not blend:  # nothing that affects this shot changed
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, out)
        log(f"Reused {scene_id} shot {shot_index + 1} (unchanged)")
        return out
    work = project.root / ".studio" / "work" / "stopmotion" / f"{scene_id}_{shot_index + 1:02d}_{preset}"
    if work.exists():
        shutil.rmtree(work)
    (work / "frames").mkdir(parents=True)
    job["out"] = str(work / "frames")
    if blend:
        job["save_blend"] = str(Path(blend).resolve())
        Path(blend).resolve().parent.mkdir(parents=True, exist_ok=True)
    log(f"Filming {scene_id} shot {shot_index + 1} ({plan.shots[shot_index].camera}, {job['frame_end']} frames on twos)...")
    _run_blender(job, work, log)
    drawings = sorted((work / "frames").glob("*.png"))
    if not drawings:
        raise RenderError("Blender wrote no frames.")
    out.parent.mkdir(parents=True, exist_ok=True)
    from ..audio.ffmpeg import ffmpeg_exe

    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-framerate", str(FPS // job["step"]), "-pattern_type", "glob",
                    "-i", str(work / "frames" / "*.png"), "-vf", f"fps={FPS}", "-c:v", "libx264", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-map_metadata", "-1", str(out)], check=True)
    cached.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, cached)
    log(f"Wrote {out} ({len(drawings)} drawings)")
    return out


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def render_scene(project, scene_id: str, preset: str, out: Path, log=print) -> Path:
    """Film every shot of a scene (reusing unchanged ones), join them and add subtitles from the plan."""
    from ..audio.ffmpeg import ffmpeg_exe

    plans = {p.scene: p for p in D.plan(project)}
    if scene_id not in plans:
        raise ConfigError(f"No enabled scene '{scene_id}'.", "List scenes with `sastudio scenes`.")
    plan = plans[scene_id]
    scene = next(s for s in project.scenes if s.id == scene_id)
    work = project.root / ".studio" / "work" / "stopmotion" / f"{scene_id}_{preset}_scene"
    work.mkdir(parents=True, exist_ok=True)
    parts, cues, offset = [], [], 0.0
    for i, shot in enumerate(plan.shots):
        if shot.camera == "insert":
            log(f"  shot {i + 1}: insert shots are not filmed in clay yet; skipped")
            continue
        clip = render_shot(project, scene_id, i, preset, work / f"shot_{i + 1:02d}.mp4", log)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(clip)], capture_output=True, text=True, check=True).stdout.strip())
        t = 0.35
        for ln in (x for x in scene.lines if x.id in shot.lines):
            d = D._estimate(ln)
            cues.append((offset + t, offset + t + d, project.display(ln.say or "", project.language)))
            t += d + 0.25
        parts.append(clip)
        offset += dur
    listing = work / "shots.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), "utf-8")
    srt = work / "scene.srt"
    srt.write_text("".join(f"{n}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n\n" for n, (a, b, text) in enumerate(cues, 1)),
                   "utf-8")
    joined = work / "joined.mp4"
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    str(joined)], check=True)
    fonts = resources.files("sastudio").joinpath("data").joinpath("fonts")
    with resources.as_file(fonts) as fdir:
        style = "FontName=Atkinson Hyperlegible Next,FontSize=17,Bold=1,BorderStyle=3,Outline=6,BackColour=&H90202020,MarginV=24"
        vf = f"subtitles={srt.as_posix()}:fontsdir={Path(fdir).as_posix()}:force_style='{style}'"
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(joined), "-vf", vf, "-c:v", "libx264", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-map_metadata", "-1", str(out)], check=True)
    out.with_suffix(".srt").write_text(srt.read_text("utf-8"), "utf-8")
    log(f"Wrote {out} ({len(parts)} shots, {offset:.1f} s)")
    return out
