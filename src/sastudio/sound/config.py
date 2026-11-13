"""What a project asks of its sound, read from studio.yaml, with the defaults filled in.

Nothing is required: a film with no `sound:` section gets the sounds of what happens on screen (clay films), the air of
each place, and a mastered mix. One music file (`render.music`, as before, or `sound.music`) is enough for a scored
film. Everything else is there to change a default:

    sound:
      effects: true               # footsteps, doors, seats, chairs, laptops, typing: what the picture shows happening
      ambience: true              # the air of each place
      library: sounds             # your own recordings, by kind (sastudio.sound.kit); a pack name or a list also works
      music:
        - { file: music/theme.mp3, scenes: [cafe], start: 12, volume_db: -2, fade_in: 2, fade_out: 3, loop: true }
      levels: { effects_db: 0, ambience_db: 0, music_db: 0, duck_db: 11 }
      master: { loudness: -16, true_peak: -1.5, bitrate: 192 }
      credits: ["Theme by ..., CC BY 4.0"]

and in a scene's direction:

    direction:
      sound:
        ambience: cafe            # or off, or a file of your own
        music: off                # no music under this scene
        mute: [footstep]          # leave these out of this scene
        cues:                     # sounds no motion makes, at a moment of a line
          - { sound: phone_ring, line: s1, at: 0, offset: -2.5, seconds: 3, who: mei }
          - { sound: sounds/knock.wav, line: l2, at: 1.0 }"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import ambience
from .events import CUE_KINDS, KINDS, Event
from .master import Target
from .mix import Levels, MusicCue

PACKS_DIR = Path.home() / ".cache" / "sastudio" / "sounds"


@dataclass
class SoundPlan:
    effects: bool = True
    ambience: bool = True
    library: list[Path] = field(default_factory=list)
    music: list[MusicCue] = field(default_factory=list)
    levels: Levels = field(default_factory=Levels)
    target: Target = field(default_factory=Target)
    credits: list[str] = field(default_factory=list)


def _path(project, p: str, where: str) -> Path:
    return project.path(p, where)


def plan(project) -> SoundPlan:
    """The project's sound settings, defaults filled in (validate() has already checked them)."""
    s = project.data.get("sound") or {}
    rc = project.render_cfg
    sp = SoundPlan(effects=bool(s.get("effects", True)), ambience=bool(s.get("ambience", True)))
    lib = s.get("library")
    for i, item in enumerate([lib] if isinstance(lib, str) else (lib or [])):
        sp.library.append(PACKS_DIR / item if "/" not in item and not (project.root / item).exists() and (PACKS_DIR / item).is_dir()
                          else _path(project, item, f"sound.library[{i}]"))
    lv = s.get("levels") or {}
    base = Levels()
    sp.levels = Levels(effects=base.effects + float(lv.get("effects_db", 0)), ambience=base.ambience + float(lv.get("ambience_db", 0)),
                       music=base.music + float(lv.get("music_db", 0)), duck=float(lv.get("duck_db", base.duck)))
    ms = s.get("master") or {}
    sp.target = Target(loudness=float(ms.get("loudness", -16.0)), true_peak=float(ms.get("true_peak", -1.5)),
                       bitrate=int(ms.get("bitrate", 192)))
    for i, m in enumerate(s.get("music") or []):
        sp.music.append(MusicCue(file=_path(project, m["file"], f"sound.music[{i}].file"),
                                 scenes=tuple(m["scenes"]) if m.get("scenes") else None, start=float(m.get("start", 0)),
                                 level=sp.levels.music + float(m.get("volume_db", 0)), fade_in=float(m.get("fade_in", 1.5)),
                                 fade_out=float(m.get("fade_out", 2.5)), loop=bool(m.get("loop", True))))
    if rc.get("music") and not sp.music:
        # render.music, as before: one track under the whole film. Its volume is now relative to the voices, so a quiet
        # track and a loud one end up at the same level; music_volume_db moves it from there as it always did (-24, the
        # old default, is the new default level; -18 is 6 dB louder)
        sp.music.append(MusicCue(file=_path(project, rc["music"], "render.music"),
                                 level=sp.levels.music + float(rc.get("music_volume_db", -24)) + 24.0))
    sp.credits = [str(c) for c in s.get("credits") or []]
    return sp


def scene_sound(scene) -> dict:
    return (getattr(scene, "direction", None) or {}).get("sound") or {}


def bed_for(project, scene, set_name: str | None, sp: SoundPlan) -> tuple[str | None, Path | None, float]:
    """The air under a scene: (bed kind, a file of the user's, dB to add)."""
    d = scene_sound(scene)
    a = d.get("ambience", "auto")
    db = float(d.get("ambience_db", 0))
    if a in (False, "off", "none") or not sp.ambience and a == "auto":
        return None, None, 0.0
    if a == "auto" or a is True:
        return (ambience.room_of(set_name)["bed"] if set_name else None), None, db
    if a in ambience.BEDS:
        return a, None, db
    return "file", project.path(a, f"scenes.{scene.id}.direction.sound.ambience"), db


def cue_events(project, scene, beats_at: dict, fps: int) -> list[Event]:
    """The scene's direction.sound.cues as events on the scene's clock. beats_at: line id -> (first second of the line's
    voice, its last second), measured from the scene's start."""
    out = []
    for i, c in enumerate(scene_sound(scene).get("cues") or []):
        span = beats_at.get(c["line"])
        if span is None:
            continue
        t = span[0] + float(c.get("at", 0.0)) * (span[1] - span[0]) + float(c.get("offset", 0.0))
        snd = c["sound"]
        kind, params = (snd, {}) if snd in KINDS else ("file", {"file": str(project.path(snd, f"scenes.{scene.id}.direction.sound.cues[{i}].sound"))})
        params["volume_db"] = float(c.get("volume_db", 0.0))
        out.append(Event(kind=kind, t=max(0.0, t), scene=scene.id, who=c.get("who"), thing=c.get("thing"),
                         duration=float(c.get("seconds", 0.0)), intensity=1.0, params=params, source="cue"))
    return out


def problems(project) -> list[tuple[str, str, str]]:
    """What is wrong with the sound settings: [(level, where, message)], for `sastudio validate`."""
    out = []
    s = project.data.get("sound") or {}
    scenes = {sc.id: sc for sc in project.scenes}
    for i, m in enumerate(s.get("music") or []):
        for sid in m.get("scenes") or []:
            if sid not in scenes:
                out.append(("error", f"sound.music[{i}].scenes", f"no scene called '{sid}'"))
        if float(m.get("fade_in", 1.5)) < 0 or float(m.get("fade_out", 2.5)) < 0:
            out.append(("error", f"sound.music[{i}]", "fades cannot be negative"))
    ms = s.get("master") or {}
    if "true_peak" in ms and float(ms["true_peak"]) > -.5:
        out.append(("warning", "sound.master.true_peak", "above -0.5 dBTP, lossy encoding may clip on playback"))
    for sc in project.scenes:
        d = scene_sound(sc)
        ids = {ln.id for ln in sc.lines}
        for i, c in enumerate(d.get("cues") or []):
            where = f"scenes.{sc.id}.direction.sound.cues[{i}]"
            if c.get("line") not in ids:
                out.append(("error", where, f"no line '{c.get('line')}' in scene {sc.id}"))
            snd = str(c.get("sound", ""))
            if snd not in CUE_KINDS and "." not in snd:
                out.append(("error", where, f"'{snd}' is not a sound this studio makes ({', '.join(k for k in CUE_KINDS if k != 'file')}) "
                                            "or a sound file"))
        for k in d.get("mute") or []:
            if k not in KINDS:
                out.append(("error", f"scenes.{sc.id}.direction.sound.mute", f"'{k}' is not a kind of sound ({', '.join(KINDS)})"))
        a = d.get("ambience")
        if isinstance(a, str) and a not in ("auto", "off", "none") and a not in ambience.BEDS and "." not in a:
            out.append(("error", f"scenes.{sc.id}.direction.sound.ambience",
                        f"'{a}' is not a place's air ({', '.join(ambience.BEDS)}), off, or a sound file"))
    return out
