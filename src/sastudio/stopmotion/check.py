"""Checking that nothing passes through anything, before filming or after it.

Blender poses every drawing of every shot exactly as filming does, and draws nothing: the engine's contact probe
(engine/clay/contacts.py) measures each drawing triangle against triangle, on the meshes as they are drawn. It finds a
body inside the set or a prop, two people inside each other, a body inside itself away from its joints, and a hand or
a foot whose path between two drawings runs through something solid.

    sastudio check my-film                  the planned shots, timed from the words: before anything is filmed
    sastudio check my-film --filmed         the shots of the last filming, exactly as they were filmed
    python tools/check_contacts.py my-film  the same, for maintainers (it checks the last filming)

A check that could not finish (Blender crashed, a shot raised an error) is a failure, never a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

KINDS = {"set": "inside", "cast": "inside", "self": "inside", "between": "passed through", "dressing": "inside"}


@dataclass
class ShotResult:
    label: str
    contacts: list = field(default_factory=list)
    drawings: int = 0
    error: str = ""
    notes: list = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return not self.error


@dataclass
class Report:
    shots: list

    @property
    def contacts(self) -> list:
        return [dict(c, shot=s.label) for s in self.shots for c in s.contacts]

    @property
    def failed(self) -> list:
        return [s for s in self.shots if not s.finished]

    @property
    def drawings(self) -> int:
        return sum(s.drawings for s in self.shots)

    def exit_code(self) -> int:
        """0 clean, 1 something passes through something, 2 the check did not finish."""
        return 2 if self.failed else (1 if self.contacts else 0)


def said(c: dict) -> str:
    """One contact in words: who, which part, inside what, when."""
    deep = f", {c['depth'] * 50:.1f} cm deep" if c.get("depth") else ""
    where = KINDS.get(c.get("kind"), "inside")
    shot = f"{c['shot']} " if c.get("shot") else ""
    return (f"{shot}frame {c['frame']}: {c['actor']}'s {c['what']} {where} {c['other']} "
            f"({c['kind']}, {c['pairs']} crossing faces{deep})")


def summary(found: list, top: int = 14) -> list[tuple[int, str]]:
    """How often each kind of contact happened: [(count, words)], most first."""
    by: dict[str, int] = {}
    for c in found:
        k = f"{c['actor']}'s {c['what']} {KINDS.get(c['kind'], 'inside')} {c['other']} ({c['kind']})"
        by[k] = by.get(k, 0) + 1
    return sorted(((n, k) for k, n in by.items()), reverse=True)[:top]


def filmed_jobs(project, shots: str = "") -> list[tuple[str, dict]]:
    """The jobs of the last filming of a project (written next to each shot's frames when it was filmed)."""
    root = Path(project.root if hasattr(project, "root") else project) / ".studio" / "work" / "clay"
    out = []
    for j in sorted(root.glob("*/job.json")):
        label = j.parent.name
        if label == "lines" or shots not in label:
            continue
        out.append((label, json.loads(j.read_text("utf-8"))))
    return out


def planned_jobs(project, scene_ids=None, preset: str = "draft", shots: str = "", log=print) -> list[tuple[str, dict]]:
    """Jobs for every planned shot, timed from the words (no voices needed): what filming would pose."""
    from .. import direction as D
    from .. import stopmotion as SM
    from ..render import clay

    out = []
    for plan in D.plan(project):
        if scene_ids and plan.scene not in scene_ids:
            continue
        scene = next(s for s in project.scenes if s.id == plan.scene)
        spans = SM.spans_estimated(project, scene)
        clay.build_rigs(project, ids=list(plan.sides), log=log)
        part = SM.scene_job(project, scene, plan, spans)
        cues = SM.line_cues(part)
        for i, shot in enumerate(plan.shots):
            if SM.is_card(shot):
                continue
            frames = SM.shot_frames(shot, spans, cues)
            if not frames:
                continue
            label = f"{plan.scene}_s{i + 1:02d}"
            if shots in label:
                out.append((label, dict(SM.shot_job(part, shot, frames, preset), rig=str(clay.rig_dir(project)), font=str(SM._font()))))
    return out


def run_check(label: str, job: dict, every: int = 1) -> ShotResult:
    """Pose every drawing of one shot's job in Blender and measure it; nothing is drawn."""
    from .. import stopmotion as SM
    from ..render import clay

    clay.require_engine()
    exe, wsl_win = SM.find_blender()
    conv = SM._winpath if wsl_win else str
    job = dict(job, mode="check", check_every=max(1, int(every)), device="CPU")
    for key in ("rig", "font"):
        if job.get(key):
            job[key] = conv(Path(job[key]))
    job["cast"] = [dict(c, model=conv(Path(c["model"]))) if c.get("model") else c for c in job.get("cast") or []]
    with tempfile.TemporaryDirectory(prefix="sas-check-") as tmp:
        jp = Path(tmp) / "job.json"
        jp.write_text(json.dumps(job), "utf-8")
        film = clay.ENGINE.joinpath("clay").joinpath("film.py")
        try:
            r = subprocess.run([exe, "-b", "--factory-startup", "-P", conv(Path(str(film))), "--", conv(jp)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=6 * 3600)
        except subprocess.TimeoutExpired:
            return ShotResult(label, error="Blender did not finish within six hours")
    out = r.stdout or ""
    res = ShotResult(label)
    for ln in out.splitlines():
        if ln.startswith("CONTACT "):
            try:
                res.contacts.append(json.loads(ln[8:]))
            except ValueError:
                res.error = f"an unreadable line from Blender: {ln[:120]}"
        elif ln.startswith("CHECKED "):
            res.drawings = int(ln.split()[1])
        elif ln.startswith("FILM ") and not ln.startswith(("FILM device", "FILM seat ", "FILM route")):
            res.notes.append(ln[5:])
    if r.returncode != 0 or not any(ln.startswith("CHECKED ") for ln in out.splitlines()):
        tail = "\n    ".join((out + (r.stderr or "")).strip().splitlines()[-12:])
        res.error = res.error or f"Blender stopped before the check was done (exit {r.returncode}):\n    {tail}"
    return res


def check(jobs: list[tuple[str, dict]], every: int = 1, workers: int = 2, log=print) -> Report:
    """Check every job, a few Blenders at a time (each one needs about a gigabyte of memory)."""
    workers = max(1, min(int(workers or 1), os.cpu_count() or 1))
    results = []
    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(lambda lj: run_check(lj[0], lj[1], every), jobs):
            results.append(res)
            if res.error:
                log(f"  {res.label}: did not finish ({res.error.splitlines()[0]})")
            else:
                log(f"  {res.label}: {res.drawings} drawings, {len(res.contacts)} contact(s)")
    return Report(results)
