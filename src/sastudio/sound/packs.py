"""Sound packs: recordings you choose to download, once, by asking for them (`sastudio sounds install kenney`).

Nothing is ever downloaded while a film is made. A pack is fetched only by that command, checked against the checksum
pinned here (a pack that changed upstream is refused, not used), and only the files the engine uses are kept, laid out
by kind as sound.kit reads them, in ~/.cache/sastudio/sounds/<pack>, with the licence and a manifest of every file:
where it came from, who made it, its licence, when it was fetched, and its SHA-256. A project uses it with
`sound: { library: kenney }`.

Only recordings anyone may use and pass on, for any purpose, are offered: Kenney's packs are CC0 (public domain
dedication), checked in each archive's License.txt."""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

from ..errors import StudioError
from .config import PACKS_DIR

KENNEY = "Kenney Vleugels (kenney.nl)"
CC0 = "CC0 1.0 Universal, public domain dedication: https://creativecommons.org/publicdomain/zero/1.0/"

PACKS = {
    "kenney": dict(
        title="Kenney's Impact Sounds 1.0 and RPG Audio: real recordings of footsteps, doors and things put down",
        archives={
            "impact-sounds": dict(page="https://kenney.nl/assets/impact-sounds", bytes=800850,
                                  sha256="029d734af1582474edf3a694d1b0cebc97c1c152f2f39fa34d4c2bafc5de77f8"),
            "rpg-audio": dict(page="https://kenney.nl/assets/rpg-audio", bytes=964837,
                              sha256="6dbeaf8544da958d8f2adcb4a4a4b76c1ade34a05f8ab9edccd327da7375f38b"),
        },
        # where each kind of sound comes from (archive: pattern); a floor without a recording of its own borrows the
        # nearest one (concrete steps for paving, stone and tile; carpet steps for a rug)
        layout={
            "footstep/wood": ["impact-sounds:*/footstep_wood_*.ogg"],
            "footstep/carpet": ["impact-sounds:*/footstep_carpet_*.ogg"],
            "footstep/rug": ["impact-sounds:*/footstep_carpet_*.ogg"],
            "footstep/pavement": ["impact-sounds:*/footstep_concrete_*.ogg"],
            "footstep/stone": ["impact-sounds:*/footstep_concrete_*.ogg"],
            "footstep/tile": ["impact-sounds:*/footstep_concrete_*.ogg"],
            "door_open": ["rpg-audio:*/doorOpen_*.ogg"],
            "door_close": ["rpg-audio:*/doorClose_*.ogg"],
            "set_down": ["impact-sounds:*/impactPlate_light_*.ogg"],
        },
        creator=KENNEY, licence=CC0, attribution="not required; credit: Kenney (kenney.nl)",
    ),
}


def _fetch(slug: str, page: str, opener=urllib.request.urlopen) -> bytes:
    """Kenney's download link answers with a short-lived signed address for the archive."""
    link = "https://kenney.nl/download-link/" + f"assets/{slug}".encode().hex()
    head = {"User-Agent": "Mozilla/5.0 (compatible; clayvoyant sound packs)", "Referer": page}
    with opener(urllib.request.Request(link, headers=head), timeout=60) as r:       # noqa: S310 (fixed https URL)
        url = json.loads(r.read().decode("utf-8"))["url"]
    if not url.startswith("https://kenney.nl/"):
        raise StudioError(f"Kenney's site answered with an unexpected address for {slug}.", "Try again later.")
    with opener(urllib.request.Request(url, headers=head), timeout=300) as r:        # noqa: S310
        return r.read()


def install(name: str, log=print, fetch=_fetch, root: Path = PACKS_DIR) -> Path:
    """Download pack `name`, check it, keep what the engine uses, and write its manifest. -> the pack's folder."""
    if name not in PACKS:
        raise StudioError(f"There is no sound pack called '{name}'.", f"Packs: {', '.join(PACKS)}.")
    spec = PACKS[name]
    dest = root / name
    tmp = root / f".{name}.part"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    archives, licences = {}, {}
    for slug, a in spec["archives"].items():
        log(f"  {slug}: downloading from {a['page']}")
        data = fetch(slug, a["page"])
        got = hashlib.sha256(data).hexdigest()
        if got != a["sha256"]:
            raise StudioError(f"The {slug} archive is not the one this version of Clayvoyant checked (SHA-256 {got[:16]}..., "
                              f"expected {a['sha256'][:16]}...).", "It may have been updated upstream; nothing was installed.")
        z = zipfile.ZipFile(io.BytesIO(data))
        archives[slug] = z
        lic = next((n for n in z.namelist() if n.lower().endswith("license.txt")), None)
        text = z.read(lic).decode("utf-8", "replace") if lic else ""
        if "CC0" not in text and "Creative Commons Zero" not in text:
            raise StudioError(f"The {slug} archive does not say it is CC0.", "Nothing was installed.")
        licences[slug] = text
        (tmp / f"LICENSE-{slug}.txt").write_text(text, "utf-8")
    files = []
    when = time.strftime("%Y-%m-%d", time.gmtime())
    for kind, pats in spec["layout"].items():
        for pat in pats:
            slug, glob = pat.split(":", 1)
            z = archives[slug]
            for n in sorted(z.namelist()):
                if fnmatch.fnmatch(n, glob):
                    data = z.read(n)
                    out = tmp / kind / Path(n).name
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                    files.append(dict(file=f"{kind}/{Path(n).name}", archive=slug, source=spec["archives"][slug]["page"],
                                      path_in_archive=n, creator=spec["creator"], licence=spec["licence"],
                                      attribution=spec["attribution"], retrieved=when, redistributable=True,
                                      sha256=hashlib.sha256(data).hexdigest()))
    (tmp / "MANIFEST.json").write_text(json.dumps(dict(pack=name, title=spec["title"], files=files), indent=1), "utf-8")
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    tmp.rename(dest)
    log(f"  {len(files)} recordings kept in {dest}")
    return dest


def installed(root: Path = PACKS_DIR) -> dict[str, Path]:
    """The packs installed whole (a folder with its manifest; never one an interrupted install left behind)."""
    if not root.is_dir():
        return {}
    return {p.name: p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".") and (p / "MANIFEST.json").is_file()}
