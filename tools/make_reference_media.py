"""Rebuild the reference films, their release files, the README stills and docs/media/film/VERIFY.md.

Run from the repository root with the package installed (for example inside `uv run`):

    python tools/make_reference_media.py projects WORK        # create WORK/starter, WORK/trailer, WORK/northgate
    python tools/make_reference_media.py render WORK          # render the four films (free offline voices)
    python tools/make_reference_media.py stills WORK          # docs/media/film/stills/*.png and loop.gif
    python tools/make_reference_media.py stage WORK DEST      # release files and MEDIA_SHA256SUMS in DEST
    python tools/make_reference_media.py verify DEST          # write docs/media/film/VERIFY.md from DEST
    python tools/make_reference_media.py all WORK DEST        # all of the above, in order

Every film is made from files in this repository alone: the starter template with the fictional
Northgate Logistics branding, five trailer scenes whose lines are copied word for word from the
starter, and examples/northgate. Voices are the free offline placeholder; nothing paid is called.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STARTER_SCENES = REPO / "src/sastudio/templates/starter/scenes"
FILM_MEDIA = REPO / "docs/media/film"
MASTER = "Security_Awareness_in_Twelve_Stories"
TRAILER = "Security_Awareness_Trailer"
EXAMPLE = "Example_Northgate_Security_Essentials"

# The starter project, rebranded for the fictional example organisation.
BRANDING = {
    '  name: "Example Organization"': '  name: "Northgate Logistics"',
    '  short_name: "Example"': '  short_name: "Northgate"',
    '  security_email: "security@example.com"        # where people report incidents': '  security_email: "security@northgate.example"  # where people report incidents',
    '  reporting_url: "https://example.com/report"   # optional: a form or portal': '  reporting_url: "https://northgate.example/report"   # optional: a form or portal',
    '  security_team: "the security team"': '  security_team: "the Northgate security team"',
    '  it_team: "the IT service desk"': '  it_team: "the Northgate IT desk"',
    '    primary: "#1E4E5F"': '    primary: "#23493B"',
    '    accent: "#E07A3F"': '    accent: "#D9A441"',
    '    background: "#F4EFE6"': '    background: "#F3EFE6"',
    '    # creator: "Your name or team"        # optional; nothing is required on screen': '    creator: "Ibrahim Sultan"',
}

# Trailer scenes. Every spoken line and card must exist word for word in a starter scene.
TRAILER_SCENES = {
    "t1_cold_open": (
        "Rook",
        "introduction",
        "Never who they say they are",
        "evening",
        [
            (
                "tr_01",
                "rook",
                "Honestly, I liked this place. Friendly people. Doors held open. Passwords handed out like biscuits.",
            )
        ],
    ),
    "t3_email": (
        "The Too-Good Email",
        "phishing",
        "Pause before you click",
        "day",
        [
            (
                "tr_03",
                "leo",
                "{aarav}! I've won a tablet. A free tablet. All I have to do is confirm my login in the next ten minutes.",
            ),
            (
                "tr_05",
                "mira",
                "Three warning signs in one email: a reward you didn't expect, a countdown, and a link that goes somewhere else.",
            ),
        ],
    ),
    "t4_two_step": (
        "One Password, Everywhere",
        "passwords",
        "Long, unique, and backed by a second step",
        "day",
        [
            ("tr_06", None, ("New sign-in request. Approve?", 2.5)),
            ("tr_07", "nadia", "Are you signing in right now?"),
            ("tr_08", "leo", "I'm standing in a corridor holding a muffin."),
        ],
    ),
    "t5_caller": (
        "The Helpful Caller",
        "social_engineering",
        "Hang up and call back",
        "day",
        [
            (
                "tr_09",
                "rook",
                "Hi {leo}, it's Sam from IT. We're seeing errors on your account. I'm sending you a code. Could you read it back to me?",
            )
        ],
    ),
    "t6_money": (
        "Urgent, From the Top",
        "payment_fraud",
        "Verify payment requests another way",
        "day",
        [
            (
                "tr_11",
                "aarav",
                "A new supplier, new bank details, urgent and secret. That's four warning signs before lunch.",
            ),
            ("tr_12", None, ("The director: 'I sent nothing. Don't pay it.'", 3)),
        ],
    ),
}

# (seconds into the film, file name) for the README stills; the loop is 8 s from 80 s.
STILLS = [(2, "01-title"), (248, "02-dialogue"), (74, "03-key-point"), (858, "04-closing")]
HINDI_STILL = (95, "05-hindi")
LOOP = (80, 8, 10)  # start, length, frames per second (10 fps is exact in GIF's 1/100 s timing)


def run(*cmd: str, quiet: bool = False) -> str:
    res = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    if res.returncode != 0:
        sys.exit(f"failed ({res.returncode}): {' '.join(cmd)}\n{res.stdout[-1500:]}{res.stderr[-1500:]}")
    if not quiet and res.stdout.strip():
        print(res.stdout.strip()[-400:])
    return res.stdout + res.stderr


def sas(*args: str) -> str:
    return run(sys.executable, "-m", "sastudio", *args, quiet=True)


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        sys.exit(f"expected exactly one {old!r} in the starter studio.yaml; the template changed")
    return text.replace(old, new)


def fresh_project(path: Path) -> None:
    if path.exists():
        if not (path / "studio.yaml").exists():
            sys.exit(f"{path} exists and is not a project; refusing to replace it")
        shutil.rmtree(path)
    sas("init", str(path))


def projects(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    starter, trailer, northgate = work / "starter", work / "trailer", work / "northgate"
    logo = REPO / "examples/northgate/assets/logo.png"

    fresh_project(starter)
    shutil.copyfile(logo, starter / "assets/logo.png")
    text = (starter / "studio.yaml").read_text("utf-8")
    for old, new in BRANDING.items():
        text = replace_once(text, old, new)
    (starter / "studio.yaml").write_text(text, "utf-8")

    corpus = "\n".join(p.read_text("utf-8") for p in sorted(STARTER_SCENES.glob("*.yaml")))
    fresh_project(trailer)
    shutil.copyfile(logo, trailer / "assets/logo.png")
    for old in (trailer / "scenes").glob("*.yaml"):
        old.unlink()
    for sid, (title, topic, headline, tod, lines) in TRAILER_SCENES.items():
        out = [
            f"id: {sid}",
            f"title: {title}",
            f"topic: {topic}",
            f"headline: {headline}",
            f"setting: {{ backdrop: office, time_of_day: {tod} }}",
            "lines:",
        ]
        for lid, who, say in lines:
            spoken = say[0] if isinstance(say, tuple) else say
            if spoken not in corpus:
                sys.exit(f"trailer line {lid} is not in the starter scenes word for word: {spoken!r}")
            if who:
                out.append(f'  - {{ id: {lid}, who: {who}, say: "{say}" }}')
            else:
                out.append(f'  - {{ id: {lid}, card: {{ text: "{say[0]}", seconds: {say[1]} }} }}')
        (trailer / "scenes" / f"{sid}.yaml").write_text("\n".join(out) + "\n", "utf-8")
    text = (starter / "studio.yaml").read_text("utf-8")
    text = replace_once(
        text,
        '  subtitle: "The attacks that target people, not computers"',
        '  subtitle: "Five scenes from the open-source starter film"',
    )
    text = replace_once(
        text,
        '  announcement: "Watch in order or pick any scene. Each one stands on its own unless it says otherwise."',
        '  announcement: "A preview of the starter film made with Security Awareness Studio."',
    )
    text, n = re.subn(
        r"scenes:\n(  - file: .*\n)+",
        "scenes:\n" + "".join(f"  - file: scenes/{k}.yaml\n" for k in TRAILER_SCENES),
        text,
    )
    if n != 1:
        sys.exit("could not find the scenes list in the starter studio.yaml")
    (trailer / "studio.yaml").write_text(text, "utf-8")

    if northgate.exists():
        if not (northgate / "studio.yaml").exists():
            sys.exit(f"{northgate} exists and is not a project; refusing to replace it")
        shutil.rmtree(northgate)
    shutil.copytree(REPO / "examples/northgate", northgate, ignore=shutil.ignore_patterns("build", ".studio"))

    for p in (starter, trailer, northgate):
        print(sas("validate", str(p), "--strict").strip().splitlines()[-1])


def render(work: Path, jobs: int = max(2, min(6, (os.cpu_count() or 4) // 2))) -> None:
    runs = [
        ("starter", ["--preset", "final"]),
        ("trailer", ["--preset", "final"]),
        ("northgate", ["--lang", "en-IN"]),
        ("northgate", ["--lang", "hi-IN"]),
    ]
    for name, extra in runs:
        t0 = time.monotonic()
        sas("render", str(work / name), *extra, "--voice-fallback", "offline", "--jobs", str(jobs))
        print(f"rendered {name} {' '.join(extra)} in {time.monotonic() - t0:.1f} s")


def built(work: Path, name: str, lang: str = "en-IN") -> Path:
    films = sorted((work / name / "build" / lang).glob("*.mp4"))
    if len(films) != 1:
        sys.exit(f"expected one film in {work / name / 'build' / lang}, found {len(films)}; run `render` first")
    return films[0]


def ffmpeg(*args: str) -> None:
    run("ffmpeg", "-v", "error", "-y", *args, quiet=True)


def no_metadata_chunks(png: Path) -> None:
    data = png.read_bytes()
    pos = 8
    while pos < len(data):
        n = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if kind in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"):
            sys.exit(f"{png} carries a {kind.decode()} chunk")
        pos += 12 + n


def stills(work: Path) -> None:
    master = built(work, "starter")
    (FILM_MEDIA / "stills").mkdir(parents=True, exist_ok=True)
    start, length, fps = LOOP
    ffmpeg(
        "-ss",
        str(start),
        "-t",
        str(length),
        "-i",
        str(master),
        "-map_metadata",
        "-1",
        "-vf",
        f"fps={fps},scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4",
        "-loop",
        "0",
        str(FILM_MEDIA / "loop.gif"),
    )
    for t, name in STILLS:
        out = FILM_MEDIA / "stills" / f"{name}.png"
        ffmpeg(
            "-ss",
            str(t),
            "-i",
            str(master),
            "-frames:v",
            "1",
            "-map_metadata",
            "-1",
            "-vf",
            "scale=1280:-1:flags=lanczos",
            str(out),
        )
        no_metadata_chunks(out)
    t, name = HINDI_STILL
    out = FILM_MEDIA / "stills" / f"{name}.png"
    ffmpeg(
        "-ss", str(t), "-i", str(built(work, "northgate", "hi-IN")), "-frames:v", "1", "-map_metadata", "-1", str(out)
    )
    no_metadata_chunks(out)
    print(f"wrote {FILM_MEDIA / 'loop.gif'} and {len(STILLS) + 1} stills")


def release_files(work: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name, stem, lang, extra in (
        ("starter", MASTER, "en-IN", (".transcript.txt",)),
        ("trailer", TRAILER, "en-IN", ()),
        ("northgate", EXAMPLE, "en-IN", ()),
        ("northgate", EXAMPLE, "hi-IN", ()),
    ):
        film = built(work, name, lang)
        base = film.name[: -len(".mp4")]
        for suffix in (".mp4", ".srt", ".vtt", *extra):
            files[f"{stem}.{lang}{suffix}"] = film.with_name(base + suffix)
        if name == "starter":
            files[f"{stem}.{lang}.manifest.json"] = film.with_name("manifest.json")
    return files


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(work: Path, dest: Path) -> None:
    files = release_files(work)
    dest.mkdir(parents=True, exist_ok=True)
    unknown = [p.name for p in dest.iterdir() if p.name not in files and p.name != "MEDIA_SHA256SUMS"]
    if unknown:
        sys.exit(f"{dest} holds files this tool did not make ({', '.join(sorted(unknown)[:5])}); use an empty folder")
    for p in dest.iterdir():
        p.unlink()
    for name, src in files.items():
        shutil.copyfile(src, dest / name)
    sums = "".join(f"{sha256(dest / n)}  {n}\n" for n in sorted(files))
    (dest / "MEDIA_SHA256SUMS").write_text(sums, "utf-8")
    print(f"staged {len(files)} files and MEDIA_SHA256SUMS in {dest}")


def probe(path: Path) -> dict:
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:format_tags",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels,pix_fmt",
        "-of",
        "json",
        str(path),
        quiet=True,
    )
    return json.loads(out[out.index("{") :])


def measure(path: Path, filt: str, pattern: str) -> list[str]:
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), *filt.split("|"), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    ).stderr
    return re.findall(pattern, log)


def verify(dest: Path) -> None:
    import yaml

    sums = dict(reversed(line.split("  ", 1)) for line in (dest / "MEDIA_SHA256SUMS").read_text("utf-8").splitlines())
    manifest = json.loads((dest / f"{MASTER}.en-IN.manifest.json").read_text("utf-8"))
    titles = {"_intro": ("Title card", ""), "_outro": ("Closing card", "")}
    for f in sorted(STARTER_SCENES.glob("*.yaml")):
        d = yaml.safe_load(f.read_text("utf-8"))
        titles[d["id"]] = (d["title"], d.get("topic", "").replace("_", " "))
    films = [
        ("Starter film (master)", f"{MASTER}.en-IN.mp4", "starter template, Northgate branding, `--preset final`"),
        ("Trailer", f"{TRAILER}.en-IN.mp4", "5 scenes built from starter lines, `--preset final`"),
        ("Example, English", f"{EXAMPLE}.en-IN.mp4", "`examples/northgate`, its own `draft` preset"),
        ("Example, Hindi", f"{EXAMPLE}.hi-IN.mp4", "`examples/northgate`, `--lang hi-IN`"),
    ]
    rows, black = [], 0
    for label, name, how in films:
        p = probe(dest / name)
        v = next(s for s in p["streams"] if s["codec_type"] == "video")
        rows.append(
            f"| {label} | `{name}` | {how} | {v['width']}x{v['height']} | {float(p['format']['duration']):.3f} s "
            f"| {int(v['nb_frames']):,} | {int(p['format']['size']):,} | `{sums[name][:16]}…` |"
        )
        black += len(measure(dest / name, "-an|-vf|blackdetect=d=0.25:pic_th=0.98", r"black_start"))
    master = dest / f"{MASTER}.en-IN.mp4"
    p = probe(master)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    a = next(s for s in p["streams"] if s["codec_type"] == "audio")
    peak = measure(master, "-vn|-af|volumedetect", r"max_volume: (-?[\d.]+) dB")
    holds = measure(master, "-an|-vf|freezedetect=n=0.001:d=1", r"freeze_duration: ([\d.]+)")
    held = sum(float(x) for x in holds)
    duration = float(p["format"]["duration"])
    tags = ", ".join(sorted((p["format"].get("tags") or {}).keys())) or "none"
    cues = (dest / f"{MASTER}.en-IN.srt").read_text("utf-8").count("-->")
    scene_rows, t = [], 0.0
    for s in manifest["scenes"]:
        name, topic = titles[s["id"]]
        mm, ss = divmod(t, 60)
        scene_rows.append(
            f"| `{s['id']}` | {name} | {topic} | {int(mm)}:{ss:05.2f} | {s['frames']:,} | {s['seconds']:.3f} |"
        )
        t += s["seconds"]
    total = sum(s["frames"] for s in manifest["scenes"])
    ffv = run("ffmpeg", "-version", quiet=True).splitlines()[0].split(" Copyright")[0]
    import PIL

    doc = f"""# Reference media verification

What was checked before the reference films were attached to the release, and how. Every film was
rendered from this repository alone by `tools/make_reference_media.py`, with
`sastudio {manifest["version"]}`, Pillow {PIL.__version__} and {ffv}, on the machine described in
[REQUIREMENTS.md](../../REQUIREMENTS.md).

**What the films are.** Illustrated cards with hard cuts: a still portrait of whoever is speaking,
the line in large on-screen text, key-point cards and title cards. The characters are not animated.
The voices are the free offline placeholder, which is digital silence (measured below); the
dialogue is in the burned-in text and in the `.srt` and `.vtt` files beside each film.

## Films

| Film | Release file | Made from | Size | Duration | Frames | Bytes | SHA-256 |
|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

Full checksums are in the release's `MEDIA_SHA256SUMS` file. (`SHA256SUMS` covers the wheel and
source archive built by the release workflow.)

## Checks on the starter film

| Check | Method | Result |
|---|---|---|
| Video stream | `ffprobe` | {v["codec_name"]}, {v["width"]}x{v["height"]}, {v["r_frame_rate"]} fps, {v["pix_fmt"]} |
| Audio stream | `ffprobe` | {a["codec_name"]}, {a["sample_rate"]} Hz, {a["channels"]} channels |
| Audio level | `ffmpeg -af volumedetect` | peak {peak[0] if peak else "n/a"} dB: digital silence (placeholder voices) |
| Still frames | `ffmpeg -vf freezedetect=n=0.001:d=1` | {len(holds)} holds of 1 s or more, {held:.1f} s of {duration:.1f} s ({100 * held / duration:.1f} %) |
| Frame count equals the timeline | manifest and `ffprobe` | {total:,} = {int(v["nb_frames"]):,} |
| Black frames | `ffmpeg -vf blackdetect=d=0.25:pic_th=0.98`, all four films | {black} found |
| Subtitles | build checks (overlap, width, reading speed) | {cues} cues, {len(manifest.get("warnings") or [])} warning(s) |
| Container metadata | `ffprobe -show_entries format_tags` | tags present: {tags} |

## Scenes in the starter film

| Id | Title | Topic | Starts at | Frames | Seconds |
|---|---|---|---|---:|---:|
{chr(10).join(scene_rows)}
| | **Total** | | | **{total:,}** | **{sum(s["seconds"] for s in manifest["scenes"]):.3f}** |

## Images in this folder

| File | What it is |
|---|---|
| `cover-1280x640.png` | README hero and GitHub social preview, composed by `tools/make_readme_media.py` |
| `cover-1920x1080.png` | 16:9 cover for slides and release pages, same tool |
| `thumbnail-1280x720.png` | video thumbnail, same tool |
| `loop.gif` | {LOOP[1]} seconds of the starter film ({LOOP[0]}-{LOOP[0] + LOOP[1]} s), 800 px wide, {LOOP[2]} fps |
| `stills/01-title.png` to `stills/04-closing.png` | frames from the starter film at {", ".join(f"{t} s" for t, _ in STILLS)}, scaled to 1280 px |
| `stills/05-hindi.png` | a frame from the Hindi example at {HINDI_STILL[0]} s (960 x 540) |

The stills are checked for embedded text, EXIF and time chunks when they are made; none are written.
"""
    (FILM_MEDIA / "VERIFY.md").write_text(doc, "utf-8")
    print(f"wrote {FILM_MEDIA / 'VERIFY.md'}: peak {peak} dB, {len(holds)} holds / {held:.1f} s, {black} black runs")


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in ("projects", "render", "stills", "stage", "verify", "all"):
        sys.exit(__doc__)
    cmd, a = argv[0], Path(argv[1]).resolve()
    if cmd in ("projects", "all"):
        projects(a)
    if cmd in ("render", "all"):
        render(a)
    if cmd in ("stills", "all"):
        stills(a)
    if cmd in ("stage", "all"):
        if len(argv) < 3:
            sys.exit("stage needs WORK and DEST")
        stage(a, Path(argv[2]).resolve())
    if cmd == "verify":
        verify(a)
    if cmd == "all":
        verify(Path(argv[2]).resolve())


if __name__ == "__main__":
    main(sys.argv[1:])
