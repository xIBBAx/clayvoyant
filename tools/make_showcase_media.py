"""Rebuild the README's pictures of the sample film from a finished render of it.

    sastudio film examples/the-fast-one --preset preview --allow-placeholder-contacts
    python tools/make_showcase_media.py examples/the-fast-one

Writes docs/media/film/the-fast-one-sheet.jpg (twelve frames) and the-fast-one.gif (a short loop). Run from the
repository root; needs FFmpeg.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path("docs/media/film")
# moments of the film worth showing, as fractions of its length
MOMENTS = (0.085, 0.16, 0.235, 0.30, 0.375, 0.44, 0.535, 0.565, 0.63, 0.70, 0.79, 0.89)
LOOP = (0.335, 5.2)      # where the loop starts (fraction of the film) and how long it runs (seconds)


def main() -> None:
    project = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/the-fast-one")
    films = sorted(project.glob("build/*/*.mp4"))
    if not films:
        raise SystemExit(f"No film in {project}/build. Render it first: sastudio film {project} --preset preview")
    film = films[0]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(film)],
                               capture_output=True, text=True, check=True).stdout)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sas-media-") as tmp:
        for i, m in enumerate(MOMENTS):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m * dur:.3f}", "-i", str(film), "-frames:v", "1",
                            f"{tmp}/{i:02d}.png"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob", "-i", f"{tmp}/*.png", "-vf",
                        "scale=800:-1,tile=4x3:padding=6:color=0x16191D", "-frames:v", "1", "-q:v", "3", "-map_metadata", "-1",
                        str(OUT / "the-fast-one-sheet.jpg")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{LOOP[0] * dur:.3f}", "-t", str(LOOP[1]), "-i", str(film), "-vf",
                    "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                    "-map_metadata", "-1", str(OUT / "the-fast-one.gif")], check=True)
    print("wrote", OUT / "the-fast-one-sheet.jpg", "and", OUT / "the-fast-one.gif", f"from {film} ({dur:.1f} s)")


if __name__ == "__main__":
    main()
