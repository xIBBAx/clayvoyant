"""FFmpeg helpers. Arguments are always passed as lists; no shell is ever involved."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

from ..errors import RenderError, ToolMissing

RATE = 48000


def ffmpeg_exe() -> str:
    exe = os.environ.get("SASTUDIO_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise ToolMissing("FFmpeg was not found.", "Install FFmpeg (docs/INSTALLATION.md) or set SASTUDIO_FFMPEG.")
    return exe


def ffprobe_exe() -> str:
    exe = os.environ.get("SASTUDIO_FFPROBE") or shutil.which("ffprobe")
    if not exe:
        raise ToolMissing("ffprobe was not found.", "It ships with FFmpeg; install FFmpeg.")
    return exe


def run(args: list[str], *, input: bytes | None = None, timeout: float = 600, what: str = "FFmpeg") -> subprocess.CompletedProcess:
    try:
        res = subprocess.run(args, input=input, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise RenderError(f"{what} timed out after {timeout:.0f}s.")
    if res.returncode != 0:
        tail = res.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        raise RenderError(f"{what} failed: " + " | ".join(tail))
    return res


def version() -> str:
    out = run([ffmpeg_exe(), "-hide_banner", "-version"]).stdout.decode("utf-8", "replace")
    return out.splitlines()[0] if out else "unknown"


def decode_to_wav(data: bytes, rate: int = RATE) -> bytes:
    res = run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(rate),
               "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], input=data, what="Audio decoding")
    return res.stdout


def wav_info(path: Path) -> tuple[int, int, int, float]:
    with wave.open(str(path)) as w:
        n, rate = w.getnframes(), w.getframerate()
        return w.getnchannels(), w.getsampwidth(), rate, n / float(rate)


def is_silent(path: Path) -> bool:
    with wave.open(str(path)) as w:
        data = w.readframes(w.getnframes())
    return not any(data)


_I_RE = re.compile(r"I:\s+(-?[\d.]+|-inf)\s+LUFS")
_PEAK_RE = re.compile(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS")


def loudness(path: Path) -> tuple[float | None, float | None]:
    """Integrated loudness (LUFS) and true peak (dBTP) measured by FFmpeg's EBU R128 filter."""
    res = run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
               "-f", "null", "-"], what="Loudness measurement")
    err = res.stderr.decode("utf-8", "replace")
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else err
    i = _I_RE.search(summary)
    p = _PEAK_RE.search(summary)

    def num(m):
        if not m or m.group(1) == "-inf":
            return None
        return float(m.group(1))

    lufs = num(i)
    if lufs is not None and lufs <= -69.0:  # FFmpeg reports -70 LUFS for silence (its gating floor)
        lufs = None
    return lufs, num(p)


def prepare_line(src: Path, dst: Path, *, target_lufs: float = -18.0, peak_ceiling: float = -2.0) -> dict:
    """Clean one dialogue take: mono 48 kHz, trim edge silence, level to a loudness target.

    The gain is a single static value (no compression), capped so the true peak stays under
    `peak_ceiling`. Silent placeholder audio is only resampled.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".trim.wav")
    if is_silent(src):
        run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(RATE),
             "-c:a", "pcm_s16le", str(dst)])
        return {"gain_db": 0.0, "lufs": None, "peak": None, "silent": True}
    trim = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03,areverse,"
            "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03,areverse")
    run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1",
         "-af", f"{trim},aresample={RATE}:resampler=soxr" if _has_soxr() else f"{trim},aresample={RATE}",
         "-c:a", "pcm_s24le", str(tmp)])
    if wav_info(tmp)[3] < 0.08:  # trimming removed (almost) everything: keep the original
        run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(RATE),
             "-c:a", "pcm_s24le", str(tmp)])
    lufs, peak = loudness(tmp)
    gain = 0.0
    if lufs is not None:
        gain = target_lufs - lufs
        if peak is not None:
            gain = min(gain, peak_ceiling - peak)
    run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp), "-af", f"volume={gain:.2f}dB",
         "-c:a", "pcm_s16le", str(dst)])
    tmp.unlink(missing_ok=True)
    return {"gain_db": round(gain, 2), "lufs": lufs, "peak": peak, "silent": False}


_SOXR: bool | None = None


def _has_soxr() -> bool:
    global _SOXR
    if _SOXR is None:
        try:
            out = run([ffmpeg_exe(), "-hide_banner", "-version"]).stdout.decode("utf-8", "replace")
            _SOXR = "--enable-libsoxr" in out
        except (RenderError, ToolMissing):
            _SOXR = False
    return _SOXR


def silence_pcm(seconds: float, rate: int = RATE) -> bytes:
    return b"\x00\x00" * int(round(seconds * rate))


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
            raise RenderError(f"{path.name} is not 48 kHz mono 16-bit; run it through prepare_line first.")
        return w.readframes(w.getnframes())


def write_wav(path: Path, pcm: bytes, rate: int = RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, path)
