"""FFmpeg helpers. Arguments are always passed as lists; no shell is ever involved."""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
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


_WAVE_PCM, _WAVE_FLOAT, _WAVE_EXTENSIBLE = 1, 3, 0xFFFE


def wav_header(path: Path) -> tuple[int, int, int, int, int]:
    """(channels, bytes per sample, rate, where the samples start, how many bytes of them) of a WAV file.

    Read from the file's own chunks, so it takes integer and float samples and the extensible header alike. FFmpeg
    writes an extensible header for every sample wider than 16 bits, and Python's own wave module reads those only
    from 3.12 on. A header whose data size was never filled in (a stream) counts the bytes that are there."""
    name = Path(path).name
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        head = f.read(12)
        if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
            raise RenderError(f"{name} is not a WAV file.")
        fmt = None
        while True:
            chunk = f.read(8)
            if len(chunk) < 8:
                raise RenderError(f"{name} has no audio in it.")
            cid, n = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if cid == b"fmt ":
                body = f.read(n)
                if len(body) < 16:
                    raise RenderError(f"{name} has a broken format header.")
                tag, channels, rate = struct.unpack("<HHI", body[:8])
                bits = struct.unpack("<H", body[14:16])[0]
                if tag == _WAVE_EXTENSIBLE and len(body) >= 26:
                    tag = struct.unpack("<H", body[24:26])[0]       # the sub-format GUID starts with the real tag
                if tag not in (_WAVE_PCM, _WAVE_FLOAT) or not channels or not rate or bits % 8 or not bits:
                    raise RenderError(f"{name} is not plain PCM or float audio (format {tag}, {bits} bits).")
                fmt = (channels, bits // 8, rate)
                f.seek(n % 2, 1)                                     # chunks are padded to an even length
            elif cid == b"data":
                if fmt is None:
                    raise RenderError(f"{name} has its audio before its format header.")
                start = f.tell()
                return (*fmt, start, min(n, size - start) if n not in (0, 0xFFFFFFFF) else size - start)
            else:
                f.seek(n + n % 2, 1)


def wav_info(path: Path) -> tuple[int, int, int, float]:
    """(channels, bytes per sample, rate, seconds) of a WAV file of any sample format."""
    channels, width, rate, _start, n = wav_header(path)
    return channels, width, rate, n // (channels * width) / float(rate)


def is_silent(path: Path) -> bool:
    """True when every sample of a WAV file is zero: the digital silence of a placeholder voice."""
    _c, _w, _r, start, n = wav_header(path)
    with open(path, "rb") as f:
        f.seek(start)
        while n > 0:
            block = f.read(min(n, 1 << 20))
            if not block:
                break
            if any(block):
                return False
            n -= len(block)
    return True


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
