"""The clay renderer: real 3D clay puppets rendered in Blender.

* `build_rigs` sculpts each character's meshes from its parameter file (normal Python with the
  `clay` extra installed: numpy, scipy, scikit-image).
* `render_portraits` renders one still per character (used by the cards renderer and docs).
* `render_line_shot` renders one dialogue line as a shot on twos, with lip sync.

Blender only ever runs the engine script shipped in this package. A project can add its own
character parameter files (JSON numbers and colours); it cannot add code.

Release 0.1 ships this orchestration but not the engine files it drives (`ENGINE_FILES`). Every
entry point calls `require_engine()` first, so clay commands stop with a clear message.
Set SASTUDIO_CLAY_DEVICE=CPU to skip the GPU request; the default (GPU) falls back to the CPU itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

from ..errors import ConfigError, RenderError, ToolMissing
from ..safepath import atomic_write_text, resolve_inside

ENGINE = resources.files("sastudio").joinpath("engine")
CLAY_VERSION = "1"
# The Blender-side puppet engine and the sculpting code. Release 0.1 does not include them (see
# docs/RENDERING.md); every clay entry point checks for them so users get a clear message, not an ImportError.
ENGINE_FILES = ("clay/shot.py", "clay/puppet.py", "clay/faceops.py", "clay/claymat.py", "clay/handrig.py",
                "sculpt/build.py", "sculpt/heads.py", "sculpt/bodies.py", "sculpt/hair.py", "sculpt/sdfkit.py")
DEVICES = ("GPU", "CPU")
COLOR_KEYS = {  # look.colors -> parameter keys
    "skin": [("head", "skin")], "hair": [("head", "hair")], "eyes": [("head", "iris")],
    "top": [("body", "jacket"), ("body", "vest")],
    "accent": [("body", "lan"), ("body", "cuff")], "bottom": [("body", "pant")],
}
SHOT_PRESETS = {"draft": (640, 360, 8), "preview": (1280, 720, 24), "final": (1920, 1080, 64)}


def engine_included() -> bool:
    """True when this installation ships the clay engine files."""
    return all(ENGINE.joinpath(*rel.split("/")).is_file() for rel in ENGINE_FILES)


def require_engine() -> None:
    if not engine_included():
        raise ToolMissing("The clay renderer is not included in this release of Security Awareness Studio.",
                          "Use the cards renderer (the default): sastudio render <project>. "
                          "The bundled clay portraits still appear on cards. See docs/RENDERING.md.")


def clay_device() -> str:
    """Cycles device request: GPU (default; falls back to CPU automatically) or CPU, via SASTUDIO_CLAY_DEVICE."""
    dev = (os.environ.get("SASTUDIO_CLAY_DEVICE") or "GPU").strip().upper()
    if dev not in DEVICES:
        raise ConfigError(f"SASTUDIO_CLAY_DEVICE is '{dev}'.", "Set it to GPU or CPU, or unset it.")
    return dev


def blender_exe() -> str:
    exe = os.environ.get("SASTUDIO_BLENDER") or shutil.which("blender")
    if not exe:
        raise ToolMissing("Blender was not found.", "Install Blender 5.2 LTS and put it on PATH, or set SASTUDIO_BLENDER.")
    return exe


def rhubarb_exe() -> str | None:
    exe = os.environ.get("SASTUDIO_RHUBARB") or shutil.which("rhubarb")
    return exe if exe and Path(exe).is_file() else None


def rig_dir(project) -> Path:
    return project.root / ".studio" / "rig"


def preset_params(project, cid: str) -> dict:
    ch = project.characters[cid]
    preset = (ch.look or {}).get("preset")
    if not preset:
        raise ConfigError(f"Character '{cid}' has no look.preset.", "Pick a clay preset (docs/CHARACTERS.md) or use the cards renderer.")
    local = project.root / "characters" / f"{preset}.json"
    if local.exists():
        path = resolve_inside(project.root, f"characters/{preset}.json", what="character preset", must_exist=True)
        if path.stat().st_size > 200_000:
            raise ConfigError(f"characters/{preset}.json is too large.")
        data = json.loads(path.read_text("utf-8"))
    else:
        f = ENGINE.joinpath("characters").joinpath(f"{preset}.json")
        if not f.is_file():
            raise ConfigError(f"No clay preset '{preset}' for character '{cid}'.",
                              "Built-in presets: " + ", ".join(sorted(p.name[:-5] for p in ENGINE.joinpath("characters").iterdir()
                                                                      if p.name.endswith(".json"))))
        data = json.loads(f.read_text("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("head"), dict) or not isinstance(data.get("body"), dict):
        raise ConfigError(f"Preset '{preset}' must have 'head' and 'body' objects.")
    for section in ("head", "body"):
        for k, v in data[section].items():
            if not isinstance(v, (int, float, str, list)) or (isinstance(v, str) and len(v) > 40):
                raise ConfigError(f"Preset '{preset}': {section}.{k} must be a number, short string or list.")
    for name, color in ((ch.look or {}).get("colors") or {}).items():
        for section, key in COLOR_KEYS.get(name, []):
            if key in data[section] or name in ("skin", "hair", "eyes", "bottom"):
                data[section][key] = color
    colors = (ch.look or {}).get("colors") or {}
    if "skin" in colors:
        data["body"]["skin"] = colors["skin"]
    if "top" in colors and data["body"].get("torso") in ("blazer", "suit_jacket"):
        data["body"]["sleeve"] = colors["top"]  # a jacket's sleeves are the jacket
    return data


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def build_rigs(project, ids: list[str] | None = None, jobs: int = 2, log=print) -> Path:
    require_engine()
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import skimage  # noqa: F401
    except ImportError:
        raise ToolMissing("Building clay characters needs numpy, scipy and scikit-image.",
                          "Install them with: pip install \"security-awareness-studio[clay]\"")
    root = rig_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    todo = []
    with tempfile.TemporaryDirectory(prefix="sas-cast-") as tmp:
        for cid in ids or list(project.characters):
            params = preset_params(project, cid)
            stamp = root / cid / ".params"
            h = _hash({"p": params, "v": CLAY_VERSION})
            if stamp.exists() and stamp.read_text() == h and (root / cid / "head.npz").exists():
                continue
            Path(tmp, f"{cid}.json").write_text(json.dumps(params), encoding="utf-8")
            todo.append((cid, stamp, h))
        if not todo:
            log("Clay characters are up to date.")
            return root
        with resources.as_file(ENGINE.joinpath("sculpt").joinpath("build.py")) as script:
            cmd = [sys.executable, "-I", str(script), tmp, str(root), ",".join(c for c, _, _ in todo), "--jobs", str(jobs)]
            log(f"Sculpting {len(todo)} character(s)...")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
        if res.returncode != 0:
            raise RenderError("Building clay characters failed: " + res.stderr.strip()[-600:])
    for _cid, stamp, h in todo:
        stamp.write_text(h)
    return root


def run_blender(spec: dict, work: Path, log=print, timeout: float = 24 * 3600) -> None:
    require_engine()
    work.mkdir(parents=True, exist_ok=True)
    spec_path = work / "spec.json"
    atomic_write_text(spec_path, json.dumps(spec))
    with resources.as_file(ENGINE.joinpath("clay").joinpath("shot.py")) as script:
        cmd = [blender_exe(), "-b", "--factory-startup", "-P", str(script), "--", str(spec_path)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail: list[str] = []
        done = 0
        for line in proc.stdout:
            tail = (tail + [line.rstrip()])[-25:]
            if line.startswith("SHOT device"):
                # Say which device Blender actually used; a CPU fallback after a GPU request is a warning.
                fell_back = spec.get("device") == "GPU" and line.startswith("SHOT device CPU")
                log(("    warning: " if fell_back else "    ") + line.strip()
                    + (" - rendering on the CPU is much slower; check your GPU driver" if fell_back else ""))
            if line.startswith("SHOT frame"):
                done += 1
                if done % 20 == 0:
                    log("    " + line.strip())
        code = proc.wait(timeout=timeout)
    if code != 0 or not any(t.startswith("SHOT done") for t in tail):
        raise RenderError("Blender failed:\n    " + "\n    ".join(tail[-12:]))


def render_portraits(project, *, force: bool = False, samples: int = 64, log=print) -> list[Path]:
    from PIL import Image

    rig = build_rigs(project, log=log)
    out_dir = project.root / "assets" / "characters"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for cid in project.characters:
        target = out_dir / f"{cid}.png"
        if target.exists() and not force:
            log(f"  {cid}: {target.name} exists (use --force to replace)")
            continue
        work = project.root / ".studio" / "work" / "portraits" / cid
        shutil.rmtree(work / "frames", ignore_errors=True)
        run_blender({"rig": str(rig), "out": str(work / "frames"), "width": 1200, "height": 1600, "fps": 24, "frames": 1,
                     "step": 1, "samples": samples, "device": clay_device(), "transparent": True,
                     "cast": [{"id": cid, "x": 0, "yaw": 0.14}], "camera": {"target": cid, "shot": "portrait"},
                     "mood": {cid: 0.3}}, work, log)
        im = Image.open(work / "frames" / "00001.png")
        bb = im.getbbox() or (0, 0, im.width, im.height)
        im = im.crop((max(0, bb[0] - 24), max(0, bb[1] - 24), min(im.width, bb[2] + 24), min(im.height, bb[3] + 24)))
        im = im.resize((int(im.width * 820 / im.height), 820), Image.LANCZOS)
        im.save(target, optimize=True)
        made.append(target)
        log(f"  {cid}: portrait saved")
    return made


def mouth_cues(wav: Path, text: str, lang: str) -> list[list]:
    """Rhubarb mouth cues [[seconds, shape]]; [] when Rhubarb is not installed."""
    exe = rhubarb_exe()
    if not exe:
        return []
    with tempfile.TemporaryDirectory(prefix="sas-rh-") as tmp:
        out = Path(tmp) / "cues.json"
        cmd = [exe, "-f", "json", "-o", str(out), "-q"]
        if lang.startswith("en"):
            dialog = Path(tmp) / "dialog.txt"
            dialog.write_text(text, encoding="utf-8")
            cmd += ["-d", str(dialog)]
        else:
            cmd += ["-r", "phonetic"]
        res = subprocess.run(cmd + [str(wav)], capture_output=True, timeout=600, check=False)
        if res.returncode != 0 or not out.exists():
            return []
        data = json.loads(out.read_text("utf-8"))
    return [[round(c["start"], 3), c["value"]] for c in data.get("mouthCues", [])]


def render_line_shot(project, tl, beat, *, preset: str, step: int = 2, log=print) -> Path:
    """Render the clay frames for one dialogue beat; cached by content."""
    w, h, samples = SHOT_PRESETS[preset]
    rig = rig_dir(project)
    cast = tl.cast[:4] if tl.cast else [beat.speaker]
    gap = 1.9
    xs = {cid: (i - (len(cast) - 1) / 2) * gap for i, cid in enumerate(cast)}
    cues = mouth_cues(Path(beat.audio), beat.text, tl.language) if beat.audio else []
    spec = {
        "rig": str(rig), "width": w, "height": h, "fps": tl.fps, "frames": beat.frames, "step": step,
        "samples": samples, "device": clay_device(), "transparent": False,
        "set": {"wall": project.org.get("palette", {}).get("background", "#d9cbb5"), "floor": "#8a6a4a"},
        "cast": [{"id": cid, "x": xs[cid], "yaw": -0.12 * (1 if xs[cid] > 0 else -1) if xs[cid] else 0} for cid in cast],
        "camera": {"target": beat.speaker, "shot": "close" if len(cast) > 1 else "medium"},
        "speech": [{"who": beat.speaker, "start": beat.audio_offset, "end": beat.frames, "cues": cues,
                    "env": beat.env[beat.audio_offset:]}],
        "mood": {cid: 0.2 for cid in cast},
    }
    stamps = {cid: (rig / cid / ".params").read_text() if (rig / cid / ".params").exists() else "" for cid in cast}
    key = _hash({"spec": {k: v for k, v in spec.items() if k != "rig"}, "rigs": stamps, "v": CLAY_VERSION})
    work = project.root / ".studio" / "work" / "clay" / f"{beat.line_id}.{key}"
    frames = work / "frames"
    expected = len(range(0, beat.frames, step))
    if frames.exists() and len(list(frames.glob("*.png"))) >= expected:
        return frames
    spec["out"] = str(frames)
    log(f"  clay shot {beat.line_id}: {beat.frames} frames on {'twos' if step == 2 else step}"
        f"{' with Rhubarb lip sync' if cues else ' (loudness lip sync)'}")
    run_blender(spec, work, log)
    return frames
