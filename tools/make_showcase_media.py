"""Rebuild the README's pictures of a sample film from a finished render of it.

    sastudio film examples/the-fast-one --preset preview --allow-placeholder-contacts
    python tools/make_showcase_media.py examples/the-fast-one
    python tools/make_showcase_media.py examples/nineteen-thirty --lang hi-IN --no-gif

Writes docs/media/film/<name>-sheet.jpg (twelve frames) and <name>.gif (a short loop), where <name> is the
project folder's name unless --name gives another. Run from the repository root; needs FFmpeg.
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

OUT = Path("docs/media/film")
# moments of the film worth showing, as fractions of its length
MOMENTS = (0.085, 0.16, 0.235, 0.30, 0.375, 0.44, 0.535, 0.565, 0.625, 0.70, 0.79, 0.89)
LOOP = (0.335, 5.2)      # where the loop starts (fraction of the film) and how long it runs (seconds)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default="examples/the-fast-one")
    ap.add_argument("--lang", help="which language's film (default: the first one built)")
    ap.add_argument("--name", help="the file names' stem (default: the project folder's name)")
    ap.add_argument("--no-gif", action="store_true", help="the sheet only")
    a = ap.parse_args()
    project = Path(a.project)
    films = sorted(project.glob(f"build/{a.lang or '*'}/*.mp4"))
    if not films:
        raise SystemExit(f"No film in {project}/build. Render it first: sastudio film {project} --preset preview")
    film, name = films[0], a.name or project.resolve().name
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(film)],
                               capture_output=True, text=True, check=True).stdout)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet, gif = OUT / f"{name}-sheet.jpg", OUT / f"{name}.gif"
    with tempfile.TemporaryDirectory(prefix="sas-media-") as tmp:
        for i, m in enumerate(MOMENTS):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m * dur:.3f}", "-i", str(film), "-frames:v", "1",
                            f"{tmp}/{i:02d}.png"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob", "-i", f"{tmp}/*.png", "-vf",
                        "scale=800:-1,tile=4x3:padding=6:color=0x16191D", "-frames:v", "1", "-q:v", "3", "-map_metadata", "-1", "-bitexact",
                        str(sheet)], check=True)
    if not a.no_gif:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{LOOP[0] * dur:.3f}", "-t", str(LOOP[1]), "-i", str(film), "-vf",
                        "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                        "-map_metadata", "-1", "-bitexact", str(gif)], check=True)
    print("wrote", sheet, *(() if a.no_gif else ("and", gif)), f"from {film} ({dur:.1f} s)")


if __name__ == "__main__":
    main()
