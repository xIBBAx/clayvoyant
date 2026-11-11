"""Bring your own 3D characters: inspect, import and wire up glTF/GLB, FBX and OBJ models.

A model becomes a character's body in the clay stop-motion renderer (sastudio.stopmotion), scaled
to the cast and placed by the shot plan. A rigged model acts: bones named the common way (Mixamo,
Unreal, Blender rigify-style "upperarm.L" and similar) turn the head and arms for gestures and
eyelines, and face shape keys named the common way (ARKit "jawOpen"/"eyeBlinkLeft", Oculus
"viseme_aa", or plain "mouthOpen"/"blink") open the mouth with the words and blink. A model
without them still appears, posed as it was made.

glTF/GLB files are read here without Blender, so `sastudio model inspect` can say what will move
before anything is rendered. FBX and OBJ are checked when Blender loads them.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import ConfigError

FORMATS = {".glb": "glTF binary", ".gltf": "glTF", ".fbx": "FBX", ".obj": "Wavefront OBJ"}
MAX_BYTES = 300 * 1024 * 1024

# The joints the renderer drives, and the names rigs commonly give them (compared after
# lower-casing and dropping prefixes such as "mixamorig:" and anything that isn't a letter or digit).
BONES: dict[str, list[str]] = {
    "head": ["head"],
    "neck": ["neck", "neck01", "neck1"],
    "spine": ["spine2", "chest", "upperchest", "spine1", "spine03", "spine02", "spine"],
    # the character's own left and right
    "left_upper_arm": ["leftarm", "upperarml", "leftupperarm", "larm", "lupperarm", "upperarmleft", "arml"],
    "left_forearm": ["leftforearm", "lowerarml", "forearml", "leftlowerarm", "lforearm", "lowerarmleft"],
    "right_upper_arm": ["rightarm", "upperarmr", "rightupperarm", "rarm", "rupperarm", "upperarmright", "armr"],
    "right_forearm": ["rightforearm", "lowerarmr", "forearmr", "rightlowerarm", "rforearm", "lowerarmright"],
}
SHAPES: dict[str, list[str]] = {
    "mouth_open": ["jawopen", "mouthopen", "visemeaa", "mouthaa", "aa", "jaw", "mouthwide", "a"],
    "blink_left": ["eyeblinkleft", "eyeblinkl", "blinkleft", "blinkl", "eyecloseleft", "eyeclosedl"],
    "blink_right": ["eyeblinkright", "eyeblinkr", "blinkright", "blinkr", "eyecloseright", "eyeclosedr"],
    "blink": ["blink", "eyesclosed", "eyeblink", "eyesblink", "eyeclose"],
}


def norm(name: str) -> str:
    name = re.split(r"[:|]", name)[-1]
    return re.sub(r"[^a-z0-9]", "", name.lower())


def match(names, table: dict[str, list[str]]) -> dict[str, str]:
    """For each wanted part, the first name in `names` that is a known alias (in alias order)."""
    by_norm: dict[str, str] = {}
    for n in names:
        by_norm.setdefault(norm(n), n)
    out = {}
    for part, aliases in table.items():
        for a in aliases:
            if a in by_norm:
                out[part] = by_norm[a]
                break
    return out


@dataclass
class ModelInfo:
    path: str
    format: str
    bytes: int
    triangles: int | None = None
    meshes: int | None = None
    bones: list[str] = field(default_factory=list)
    shape_keys: list[str] = field(default_factory=list)
    animations: int | None = None
    rig: dict[str, str] = field(default_factory=dict)
    face: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def moves(self) -> list[str]:
        out = []
        if "head" in self.rig or "neck" in self.rig:
            out.append("head turns and nods")
        if any(k in self.rig for k in ("left_upper_arm", "right_upper_arm")):
            out.append("arm gestures")
        if "mouth_open" in self.face:
            out.append("mouth follows the words")
        if any(k in self.face for k in ("blink", "blink_left", "blink_right")):
            out.append("blinks")
        return out


def _gltf_json(path: Path) -> dict:
    data = path.read_bytes()
    if path.suffix.lower() == ".gltf":
        return json.loads(data.decode("utf-8"))
    if len(data) < 20 or data[:4] != b"glTF":
        raise ConfigError(f"{path.name} is not a GLB file.", "Export it again as glTF binary (.glb).")
    length, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise ConfigError(f"{path.name}: the first GLB chunk is not JSON.")
    return json.loads(data[20:20 + length].decode("utf-8"))


def inspect(path: str | Path) -> ModelInfo:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in FORMATS:
        raise ConfigError(f"{p.name}: {ext or 'no extension'} is not a model format this tool reads.",
                          f"Use one of: {', '.join(FORMATS)} (glTF binary .glb is the most reliable).")
    if not p.is_file():
        raise ConfigError(f"No file at {p}.")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise ConfigError(f"{p.name} is {size / 1e6:.0f} MB; the limit is {MAX_BYTES / 1e6:.0f} MB.",
                          "Reduce textures or polygons, or export only the character.")
    info = ModelInfo(str(p), FORMATS[ext], size)
    if ext in (".glb", ".gltf"):
        g = _gltf_json(p)
        if ext == ".gltf" and any("uri" in b and not str(b["uri"]).startswith("data:") for b in g.get("buffers", [])):
            raise ConfigError(f"{p.name} keeps its data in separate files.",
                              "Export as glTF binary (.glb), which packs everything into one file.")
        nodes = g.get("nodes", [])
        joints = {j for s in g.get("skins", []) for j in s.get("joints", [])}
        info.bones = [nodes[j].get("name", f"joint{j}") for j in sorted(joints)]
        tris = 0
        accessors = g.get("accessors", [])
        for m in g.get("meshes", []):
            names = (m.get("extras") or {}).get("targetNames") or []
            info.shape_keys += [n for n in names if n not in info.shape_keys]
            for prim in m.get("primitives", []):
                idx = prim.get("indices")
                if idx is not None and idx < len(accessors):
                    tris += accessors[idx].get("count", 0) // 3
                elif "POSITION" in prim.get("attributes", {}):
                    tris += accessors[prim["attributes"]["POSITION"]].get("count", 0) // 3
        info.triangles, info.meshes = tris, len(g.get("meshes", []))
        info.animations = len(g.get("animations", []))
        info.rig, info.face = match(info.bones, BONES), match(info.shape_keys, SHAPES)
        if not info.bones:
            info.notes.append("No skeleton: the model appears as made, without gestures or head turns.")
        elif not info.rig:
            info.notes.append("The bones have names this tool does not recognise; the model will stand still.")
        if not info.face:
            info.notes.append("No face shape keys for the mouth or eyes: the face will not move.")
        if tris > 300_000:
            info.notes.append(f"{tris:,} triangles is heavy for a character; rendering will be slow.")
    else:
        info.notes.append(f"{FORMATS[ext]} files are checked when Blender loads them (bones and shape keys are "
                          "matched the same way).")
    return info


def _flow(v) -> str:
    """A value written as YAML flow style (strings double-quoted, so any text is safe)."""
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k}: {_flow(x)}" for k, x in v.items()) + " }" if v else "{}"
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v), ensure_ascii=False)


def _set_look(text: str, cid: str, fields: dict) -> str:
    """Add or replace `look` fields of one character, keeping the rest of the file and its comments.

    The result is checked: it must parse, and the character's look must hold exactly the old values
    plus the new ones. Otherwise nothing is changed and the user is told what to add by hand.
    """
    data = yaml.safe_load(text) or {}
    chars = data.get("characters") or []
    current = next((c for c in chars if isinstance(c, dict) and c.get("id") == cid), None)
    hint = "Add " + ", ".join(f"`{k}: {_flow(v)}`" for k, v in fields.items()) + f" to {cid}'s look by hand."
    if current is None:
        raise ConfigError(f"No character '{cid}' in studio.yaml.", "Use the id of an existing character.")
    want = dict(current.get("look") or {})
    want.update(fields)
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^(\s*)- id: [\"']?{re.escape(cid)}[\"']?\s*(#.*)?$", ln)),
                 None)
    if start is None:
        raise ConfigError(f"Could not find `- id: {cid}` in studio.yaml.", hint)
    item_indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() and not ln.lstrip().startswith("#") and (len(ln) - len(ln.lstrip()) <= item_indent):
            break
        end += 1
    for i in range(start + 1, end):
        m = re.match(r"^(\s+)look:\s*\{.*\}\s*(#.*)?$", lines[i])
        if m:  # flow style: write the whole mapping again
            lines[i] = f"{m.group(1)}look: {_flow(want)}" + (f"  {m.group(2)}" if m.group(2) else "")
            break
        m = re.match(r"^(\s+)look:\s*(#.*)?$", lines[i])
        if m:  # block style: replace or add one line per key, straight after the last key
            inner = m.group(1) + "  "
            todo = dict(fields)
            j = i + 1
            while j < end and (not lines[j].strip() or lines[j].startswith(inner)):
                key = lines[j].strip().split(":", 1)[0]
                if lines[j].startswith(inner) and not lines[j].startswith(inner + " ") and key in todo:
                    lines[j] = f"{inner}{key}: {_flow(todo.pop(key))}"
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            lines[j:j] = [f"{inner}{k}: {_flow(v)}" for k, v in todo.items()]
            break
    else:  # no look yet
        if any(re.match(r"^\s+look\s*:", lines[i]) for i in range(start + 1, end)):  # written some other way
            raise ConfigError("studio.yaml writes this character's look in a way that cannot be changed safely.", hint)
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, f"{' ' * (item_indent + 2)}look: {_flow(want)}")
    out = "\n".join(lines)
    try:
        check = yaml.safe_load(out)
        got = next(c for c in check["characters"] if c.get("id") == cid).get("look")
    except Exception:
        got = None
    if got != want:
        raise ConfigError("Could not change studio.yaml safely, so it was left as it was.", hint)
    return out


def import_model(project_root: Path, src: str | Path, cid: str, licence: str, yaw: float | None = None) -> tuple[Path, ModelInfo]:
    """Copy a model into the project and make it character `cid`'s body. Nothing is written if a check fails."""
    info = inspect(src)
    licence = (licence or "").strip()
    if len(licence) < 3:
        raise ConfigError("Say under what licence you may use this model (--license).",
                          'For example: --license "CC BY 4.0, Jane Doe, https://example.org/model" or "made by me".')
    yml = project_root / "studio.yaml"
    data = yaml.safe_load(yml.read_text("utf-8"))
    if cid not in [c.get("id") for c in data.get("characters") or []]:
        raise ConfigError(f"No character '{cid}' in {yml}.", "Use the id of an existing character.")
    src = Path(src)
    dest_rel = f"assets/models/{cid}{src.suffix.lower()}"
    fields: dict = {"model": dest_rel, "model_license": licence[:200]}
    if yaw is not None:
        fields["model_yaw"] = float(yaw)
    new_text = _set_look(yml.read_text("utf-8"), cid, fields)  # checked: nothing is written if it would not parse
    dest = project_root / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    if src.suffix.lower() == ".obj":  # an OBJ's materials live beside it
        mtl = src.with_suffix(".mtl")
        if mtl.is_file():
            shutil.copyfile(mtl, dest.with_suffix(".mtl"))
    yml.write_text(new_text, "utf-8")
    return dest, info


def describe(info: ModelInfo) -> str:
    rows = [f"{Path(info.path).name}: {info.format}, {info.bytes / 1e6:.1f} MB"
            + (f", {info.triangles:,} triangles in {info.meshes} mesh(es)" if info.triangles is not None else "")]
    if info.bones:
        rows.append(f"  skeleton: {len(info.bones)} bones; drives " + (", ".join(f"{k} = {v}" for k, v in info.rig.items())
                                                                     or "none of them"))
    if info.shape_keys:
        rows.append(f"  face: {len(info.shape_keys)} shape keys; uses " + (", ".join(f"{k} = {v}" for k, v in info.face.items())
                                                                          or "none of them"))
    moves = info.moves()
    rows.append("  in the clay renderer: " + ("; ".join(moves) if moves else "appears as made, without moving"))
    rows += [f"  note: {n}" for n in info.notes]
    return "\n".join(rows)
