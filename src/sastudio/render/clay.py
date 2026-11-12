"""The clay characters: sculpting them, and the small things the clay renderer needs to know about this machine.

* `build_rigs` sculpts each character's meshes from its description (normal Python with the `clay` extra
  installed: numpy, scipy, scikit-image). Sculpts are cached per character and rebuilt only when its look changes.
* `render_portraits` renders one still per character, for the cards styles and for documents.
* Filming is in `sastudio.stopmotion`, which writes jobs for the engine in `engine/clay/film.py`.

Blender only ever runs the engine scripts shipped in this package. A project can describe characters and add its
own parameter files (JSON numbers and colours); it cannot add code.

Every entry point calls `require_engine()` first, so an installation without the engine files stops with a clear
message. Set SASTUDIO_CLAY_DEVICE=CPU to skip the GPU request; the default (GPU) falls back to the CPU itself.
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

ENGINE = resources.files("sastudio").joinpath("engine")
CLAY_VERSION = "2"  # bump when the sculpt code changes what a character looks like: every rig is sculpted again
ENGINE_FILES = ("clay/film.py", "clay/acting.py", "clay/guest.py", "clay/sets.py", "clay/setkit.py", "clay/puppet.py", "clay/faceops.py",
                "clay/claymat.py", "clay/handrig.py", "sculpt/build.py", "sculpt/heads.py", "sculpt/bodies.py", "sculpt/hair.py",
                "sculpt/sdfkit.py")
DEVICES = ("GPU", "CPU")


def engine_included() -> bool:
    """True when this installation ships the clay engine files."""
    return all(ENGINE.joinpath(*rel.split("/")).is_file() for rel in ENGINE_FILES)


def require_engine() -> None:
    if not engine_included():
        raise ToolMissing("The clay engine files are missing from this installation of Clayvoyant.",
                          "Reinstall the package, or use the cards renderer: sastudio render <project>.")


def clay_device() -> str:
    """Cycles device request: GPU (default; falls back to CPU automatically) or CPU, via SASTUDIO_CLAY_DEVICE."""
    dev = (os.environ.get("SASTUDIO_CLAY_DEVICE") or "GPU").strip().upper()
    if dev not in DEVICES:
        raise ConfigError(f"SASTUDIO_CLAY_DEVICE is '{dev}'.", "Set it to GPU or CPU, or unset it.")
    return dev


def blender_exe() -> str:
    exe = os.environ.get("SASTUDIO_BLENDER") or shutil.which("blender")
    if not exe:
        raise ToolMissing("Blender was not found.", "Install Blender 4.2 or newer and put it on PATH, or set SASTUDIO_BLENDER.")
    return exe


def rhubarb_exe() -> str | None:
    exe = os.environ.get("SASTUDIO_RHUBARB") or shutil.which("rhubarb")
    return exe if exe and Path(exe).is_file() else None


def rig_dir(project) -> Path:
    return project.root / ".studio" / "rig"


def preset_params(project, cid: str) -> dict:
    """Sculpt parameters for a character (kept under its old name; see sastudio.claydesign)."""
    from .. import claydesign

    return claydesign.params(project, cid)


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def build_rigs(project, ids: list[str] | None = None, jobs: int = 2, log=print) -> Path:
    """Sculpt the characters that are not already sculpted with their current look. Returns the rig folder."""
    require_engine()
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import skimage  # noqa: F401
    except ImportError:
        raise ToolMissing("Sculpting clay characters needs numpy, scipy and scikit-image.",
                          "Install them with: pip install \"clayvoyant[clay]\"")
    root = rig_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    todo = []
    with tempfile.TemporaryDirectory(prefix="sas-cast-") as tmp:
        for cid in ids or list(project.characters):
            if (project.characters[cid].look or {}).get("model"):
                continue        # a character brought in as a model is not sculpted
            params = preset_params(project, cid)
            stamp = root / cid / ".params"
            h = _hash({"p": params, "v": CLAY_VERSION})
            if stamp.exists() and stamp.read_text() == h and (root / cid / "head.npz").exists():
                continue
            Path(tmp, f"{cid}.json").write_text(json.dumps(params), encoding="utf-8")
            todo.append((cid, stamp, h))
        if not todo:
            return root
        with resources.as_file(ENGINE.joinpath("sculpt").joinpath("build.py")) as script:
            cmd = [sys.executable, "-I", str(script), tmp, str(root), ",".join(c for c, _, _ in todo), "--jobs", str(jobs)]
            log(f"Sculpting {len(todo)} character(s): {', '.join(c for c, _, _ in todo)} (about half a minute each)...")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
        if res.returncode != 0:
            raise RenderError("Sculpting the characters failed: " + (res.stderr.strip() or res.stdout.strip())[-600:])
    for _cid, stamp, h in todo:
        stamp.write_text(h)
    return root


def render_portraits(project, *, force: bool = False, samples: int = 48, log=print) -> list[Path]:
    """One clay still per character, in assets/characters/<id>_clay.png."""
    from .. import stopmotion

    made = []
    for cid in project.characters:
        target = project.root / "assets" / "characters" / f"{cid}_clay.png"
        if target.exists() and not force:
            log(f"  {cid}: {target.name} exists (use --force to replace)")
            continue
        made.append(stopmotion.render_portrait(project, cid, samples=samples, log=log))
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
