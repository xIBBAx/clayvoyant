"""Environment diagnostics: what is installed, what is missing, and how to fix it."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import features


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail | info
    detail: str
    fix: str | None = None


def _run(cmd: list[str], timeout: float = 20) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        return (r.stdout or r.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return None


def _mem_gb() -> float | None:
    try:
        if sys.platform.startswith("linux"):
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullAvailPhys / 1024 ** 3
    except (OSError, ValueError, AttributeError):
        return None
    return None


# Under WSL2 the NVIDIA tools live outside PATH and the GPU is exposed through /dev/dxg.
WSL_NVIDIA_SMI = Path("/usr/lib/wsl/lib/nvidia-smi")
WSL_GPU_DEVICE = Path("/dev/dxg")


def gpu_check() -> Check:
    """Name the GPU when we can; never fail (the cards renderer needs no GPU)."""
    smi = shutil.which("nvidia-smi") or (str(WSL_NVIDIA_SMI) if WSL_NVIDIA_SMI.is_file() else None)
    if smi:
        try:
            r = subprocess.run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                               capture_output=True, timeout=20, check=False)
            first = r.stdout.decode("utf-8", "replace").strip().splitlines()
            if r.returncode == 0 and first:
                return Check("GPU", "info", first[0].strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    if WSL_GPU_DEVICE.exists():
        return Check("GPU", "info", "a WSL GPU device is present (/dev/dxg), but no NVIDIA tools could name it")
    return Check("GPU", "info", "no GPU detected; the cards renderer does not need one")


def run_checks(project_dir: Path | None = None) -> list[Check]:
    out: list[Check] = []
    py = sys.version_info
    out.append(Check("Python", "ok" if py >= (3, 11) else "fail", platform.python_version(),
                     None if py >= (3, 11) else "Install Python 3.11 or newer."))
    out.append(Check("System", "info", f"{platform.system()} {platform.release()} ({platform.machine()})"
                     + (" under WSL" if "microsoft" in platform.release().lower() else "")))

    ff = os.environ.get("SASTUDIO_FFMPEG") or shutil.which("ffmpeg")
    if not ff:
        out.append(Check("FFmpeg", "fail", "not found", "Install FFmpeg 6 or newer and put it on PATH (docs/INSTALLATION.md)."))
    else:
        txt = _run([ff, "-hide_banner", "-version"]) or ""
        m = re.search(r"ffmpeg version (\S+)", txt)
        has_x264 = "--enable-libx264" in txt
        out.append(Check("FFmpeg", "ok" if has_x264 else "fail", m.group(1) if m else "unknown version",
                         None if has_x264 else "This FFmpeg has no libx264 encoder; install a full build."))
        if "--enable-libsoxr" not in txt:
            out.append(Check("FFmpeg soxr", "warn", "not built in; the default resampler is used",
                             "Optional. A build with libsoxr resamples speech slightly more cleanly."))
    probe = os.environ.get("SASTUDIO_FFPROBE") or shutil.which("ffprobe")
    out.append(Check("ffprobe", "ok" if probe else "fail", probe or "not found", None if probe else "It ships with FFmpeg."))

    out.append(Check("Text shaping (Raqm)", "ok" if features.check("raqm") else "warn",
                     "available" if features.check("raqm") else "missing: Hindi and other Indic scripts will render incorrectly",
                     None if features.check("raqm") else "Install the official Pillow wheel, or libraqm on Linux."))

    from .voices.offline import find_espeak

    es = find_espeak()
    out.append(Check("espeak-ng (free offline voice)", "ok" if es else "info", es or "not installed; offline voices will be timed silence",
                     None if es else "Optional: install espeak-ng to hear a robotic placeholder voice."))

    from .render.clay import engine_included

    blender = os.environ.get("SASTUDIO_BLENDER") or shutil.which("blender")
    if not engine_included():
        out.append(Check("Clay renderer", "info", "engine files missing from this installation; reinstall to make clay films",
                         "The cards renderer (the default) is the supported renderer (docs/RENDERING.md)."))
    elif blender:
        txt = _run([blender, "--version"], timeout=60) or ""
        m = re.search(r"Blender (\d+\.\d+(?:\.\d+)?)", txt)
        ver = m.group(1) if m else "unknown"
        ok = bool(m) and tuple(int(x) for x in ver.split(".")[:2]) >= (4, 2)
        out.append(Check("Blender (for Sultan, the clay engine)", "ok" if ok else "warn", ver,
                         None if ok else "The clay renderer is tested with Blender 5.2 LTS."))
    else:
        out.append(Check("Blender (for Sultan, the clay engine)", "info", "not found (only needed for 3D clay scenes)",
                         "Optional: install Blender 5.2 LTS and set SASTUDIO_BLENDER if it is not on PATH."))
    if engine_included():
        rh = os.environ.get("SASTUDIO_RHUBARB") or shutil.which("rhubarb")
        out.append(Check("Rhubarb Lip Sync", "ok" if rh else "info", rh or "not found (clay lip sync falls back to loudness)",
                         None if rh else "Optional: better mouth shapes for clay scenes (docs/RENDERING.md)."))

    out.append(gpu_check())

    mem = _mem_gb()
    if mem is not None:
        out.append(Check("Free memory", "ok" if mem >= 2 else "warn", f"{mem:.1f} GB available",
                         None if mem >= 2 else "Close other programs or render with --jobs 1."))
    target = project_dir or Path.cwd()
    try:
        free = shutil.disk_usage(target).free / 1024 ** 3
        out.append(Check("Free disk", "ok" if free >= 5 else ("warn" if free >= 1 else "fail"), f"{free:.1f} GB at {target}",
                         None if free >= 5 else "A 10-minute final render needs about 1-2 GB of working space."))
    except OSError:
        pass
    out.append(Check("CPU threads", "info", str(os.cpu_count())))

    if project_dir is not None:
        from .voices.engine import credentials, redact

        env = credentials(project_dir)
        for k in ("SARVAM_API_KEY", "ELEVENLABS_API_KEY"):
            out.append(Check(k, "info", redact(env.get(k)), None))
    return out


def format_checks(checks: list[Check]) -> str:
    sym = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    lines = []
    for c in checks:
        lines.append(f"[{sym[c.status]}] {c.name}: {c.detail}")
        if c.fix and c.status in ("warn", "fail", "info"):
            lines.append(f"         {c.fix}")
    return "\n".join(lines)
