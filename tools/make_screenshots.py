"""Render the README's terminal captures from real command output (run from the repository root).

    python tools/make_screenshots.py

Each capture runs a real command in a fresh temporary project called `my-film` and draws its
output as an image. Long output is cut after its first lines, and the render capture stops before
the final JSON summary (which lists absolute paths). The manifest capture shows selected fields
with checksums shortened, and says so. Paths are relative, so no user name or home folder appears.
The doctor capture drops the exact kernel build and GPU driver version (a machine fingerprint) and
says so on the image. Needs FFmpeg (one scene is rendered) and a monospaced font (DejaVu Sans Mono or Noto Sans Mono; pass --font to choose another).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("docs/media/screenshots")
BG, FG, DIM, PROMPT = "#16191D", "#E4E7EA", "#8C969C", "#F0A06B"
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
         "C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc"]


def run(args: list[str], cwd: Path) -> str:
    env = {**os.environ, "SARVAM_API_KEY": "", "ELEVENLABS_API_KEY": ""}  # captures never show a key
    r = subprocess.run([sys.executable, "-m", "sastudio", *args], cwd=cwd, capture_output=True, text=True,
                       env=env, timeout=600, check=False)
    if r.returncode != 0:
        raise SystemExit(f"sastudio {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def generalize_doctor(text: str) -> str:
    """Keep what the reader needs (OS family, GPU model and memory), drop the exact kernel build and driver."""
    text, a = re.subn(r"(System: \S+) \S+ (\([^)]*\))", r"\1 \2", text)
    text, b = re.subn(r"(GPU: [^\n]*?, \d+ MiB), [\w.]+", r"\1", text)
    return text.rstrip("\n") + ("\n... (kernel build and GPU driver version removed from this capture)" if a or b else "")


def draw(command: str, output: str, path: Path, font_path: str, max_lines: int = 26) -> None:
    lines = output.rstrip("\n").splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines)"]
    f = ImageFont.truetype(font_path, 22)
    cw = f.getbbox("M")[2]
    lh, pad = 31, 34
    cols = max(len(command) + 2, *(len(ln) for ln in lines), 70)
    w, h = pad * 2 + cw * cols, pad * 2 + lh * (len(lines) + 1)
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.text((pad, pad), "$", font=f, fill=PROMPT)
    d.text((pad + cw * 2, pad), command, font=f, fill=FG)
    for i, ln in enumerate(lines):
        d.text((pad, pad + lh * (i + 1)), ln, font=f, fill=DIM if ln.startswith("...") else FG)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    print(f"wrote {path} {w}x{h}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default=next((p for p in FONTS if Path(p).is_file()), None))
    a = ap.parse_args()
    if not a.font:
        raise SystemExit("No monospaced font found; pass --font /path/to/font.ttf")
    with tempfile.TemporaryDirectory(prefix="sas-shots-") as tmp:
        cwd = Path(tmp)
        run(["init", "my-film"], cwd)
        draw("sastudio doctor my-film", generalize_doctor(run(["doctor", "my-film"], cwd)), OUT / "01-doctor.png", a.font)
        draw("sastudio scenes my-film", run(["scenes", "my-film"], cwd), OUT / "02-scenes.png", a.font)
        draw("sastudio script my-film --scenes too_good_email",
             run(["script", "my-film", "--scenes", "too_good_email"], cwd), OUT / "03-script.png", a.font, 18)
        grep = subprocess.run(["grep", "-n", "-A", "19", "^organization:", "my-film/studio.yaml"], cwd=cwd,
                              capture_output=True, text=True, check=True).stdout
        draw("grep -n -A 19 '^organization:' my-film/studio.yaml", grep, OUT / "04-studio-yaml.png", a.font)
        rendered = run(["render", "my-film", "--scenes", "first_day", "--preset", "draft"], cwd).splitlines()
        upto = next(i for i, ln in enumerate(rendered) if ln.startswith("Done:"))
        shown_render = "\n".join(rendered[:upto + 1]) + "\n... (JSON summary with file paths not shown)"
        draw("sastudio render my-film --scenes first_day --preset draft", shown_render, OUT / "05-render.png", a.font,
             30)
        out = cwd / "my-film" / "build" / "en-IN"
        man = json.loads((out / "manifest.json").read_text("utf-8"))
        shown = {k: man[k] for k in ("tool", "version", "language", "preset", "renderer", "fps", "scenes", "rendered")}
        shown["outputs"] = {k: {"bytes": v.get("bytes"), "sha256": (v.get("sha256") or "")[:16] + "..."}
                            for k, v in list(man["outputs"].items())[:2]}
        draw("cat my-film/build/en-IN/manifest.json   # selected fields, checksums shortened", json.dumps(shown, indent=1),
             OUT / "06-manifest.png",
             a.font, 30)


if __name__ == "__main__":
    main()
