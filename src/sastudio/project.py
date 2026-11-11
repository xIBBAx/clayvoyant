"""Load, validate and resolve a project folder.

A project is a folder with `studio.yaml` at its root (see docs/CONFIGURATION.md). Project files
are treated as untrusted: YAML is parsed with a safe loader that also refuses anchors/aliases,
file sizes are capped, every path is kept inside the project folder, and nothing in a project
file is ever executed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .errors import ConfigError, TemplateError, UnsafePathError
from .safepath import resolve_inside
from .text import template as tpl
from .text.speech import DEFAULT_LEXICON, SpeechRules, speak_email, speak_url

PROJECT_FILE = "studio.yaml"
MAX_FILE_BYTES = 1_000_000
SCHEMA_VERSION = 1
MODEL_EXTS = {".glb", ".gltf", ".fbx", ".obj"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

ORG_FIELDS = ("name", "short_name", "security_email", "reporting_url", "security_team", "it_team", "training_title")
ORG_DEFAULTS = {
    "security_team": "your security team",
    "it_team": "your IT team",
}


# --------------------------------------------------------------------------- YAML
class _NoAliasLoader(yaml.SafeLoader):
    """SafeLoader that rejects anchors and aliases (no 'billion laughs' expansion)."""

    def compose_node(self, parent, index):  # type: ignore[override]
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise ConfigError(
                f"YAML aliases are not allowed (line {event.start_mark.line + 1}).",
                "Write the value out in full instead of using '*name'.",
            )
        node = super().compose_node(parent, index)
        if getattr(node, "anchor", None):
            raise ConfigError("YAML anchors ('&name') are not allowed.", "Write values out in full.")
        return node


def read_yaml(path: Path) -> Any:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise ConfigError(f"File not found: {path}", "Check the path, or run `sastudio init` to create a project.")
    if size > MAX_FILE_BYTES:
        raise ConfigError(f"{path.name} is {size:,} bytes; the limit is {MAX_FILE_BYTES:,}.",
                          "Split long scenes into several scene files.")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ConfigError(f"{path.name} is not UTF-8 text ({e}).", "Save the file as UTF-8.")
    try:
        return yaml.load(text, Loader=_NoAliasLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name} is not valid YAML: {e}", "Check indentation and quotes around text with ':' in it.")


# --------------------------------------------------------------------------- issues
@dataclass
class Issue:
    level: str  # "error" | "warning"
    where: str
    message: str
    hint: str | None = None

    def __str__(self) -> str:
        s = f"[{self.level}] {self.where}: {self.message}"
        return s + (f"\n          fix: {self.hint}" if self.hint else "")


# --------------------------------------------------------------------------- model
@dataclass
class VoiceSpec:
    provider: str
    model: str | None = None
    speaker: str | None = None
    voice_id: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def identity(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "speaker": self.speaker,
                "voice_id": self.voice_id, "settings": dict(sorted(self.settings.items()))}


@dataclass
class Character:
    id: str
    name: str
    role: str = ""
    description: str = ""
    pronouns: str = "they"
    gender: str = "other"
    forms: dict[str, str] = field(default_factory=dict)
    spoken: dict[str, str] = field(default_factory=dict)
    pronunciation: dict[str, dict] = field(default_factory=dict)
    attrs: dict[str, str] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)
    look: dict[str, Any] = field(default_factory=dict)

    def voice_for(self, lang: str, defaults: dict[str, dict]) -> VoiceSpec:
        base = {k: v for k, v in self.voice.items() if k != "languages"}
        override = (self.voice.get("languages") or {}).get(lang)
        if override:
            if override.get("provider", base.get("provider")) != base.get("provider"):
                base = {}
            merged_settings = {**(base.get("settings") or {}), **(override.get("settings") or {})}
            base = {**base, **{k: v for k, v in override.items() if k != "languages"}, "settings": merged_settings}
        provider = base["provider"]
        pdef = defaults.get(provider, {})
        return VoiceSpec(
            provider=provider,
            model=base.get("model") or pdef.get("model"),
            speaker=base.get("speaker"),
            voice_id=base.get("voice_id"),
            settings={**(pdef.get("settings") or {}), **(base.get("settings") or {})},
        )

    def text_view(self) -> tpl.CharacterText:
        return tpl.CharacterText(
            id=self.id, name=self.name, pronouns=self.pronouns, gender=self.gender,
            forms=dict(self.forms), spoken=dict(self.spoken),
            pronunciation={k: dict(v) for k, v in self.pronunciation.items()}, attrs=dict(self.attrs),
        )


@dataclass
class Line:
    id: str
    scene_id: str
    who: str | None = None
    say: str | None = None
    translations: dict[str, str] = field(default_factory=dict)
    spoken: dict[str, str] = field(default_factory=dict)
    emotion: str | None = None
    to: str | None = None
    pause_after: float | None = None
    card: dict[str, Any] | None = None
    act: list[str] = field(default_factory=list)  # gestures (docs/DIRECTION.md)
    camera: str | None = None  # a camera preset for this line
    reactions: dict[str, str] = field(default_factory=dict)  # how the listeners take it: character id -> emotion
    go: str | None = None  # a mark of the set the speaker walks to as the line begins

    @property
    def is_card(self) -> bool:
        return self.card is not None

    def template_for(self, lang: str, default_lang: str, fallback: bool) -> str | None:
        if self.card is not None:
            if lang == default_lang:
                return self.card["text"]
            t = (self.card.get("translations") or {}).get(lang)
            return t if t is not None else (self.card["text"] if fallback else None)
        if lang == default_lang:
            return self.say
        t = self.translations.get(lang)
        return t if t is not None else (self.say if fallback else None)


@dataclass
class Scene:
    id: str
    title: str
    lines: list[Line]
    order: int
    source: str
    enabled: bool = True
    requires: list[str] = field(default_factory=list)
    topic: str = ""
    summary: str = ""
    setting: dict[str, Any] = field(default_factory=dict)
    headline: str = ""
    takeaway: str = ""
    policy_note: str = ""
    max_seconds: float | None = None
    translations: dict[str, dict[str, str]] = field(default_factory=dict)  # field -> lang -> text
    direction: dict[str, Any] = field(default_factory=dict)  # sets, light, shots (docs/DIRECTION.md)

    def field_for(self, name: str, lang: str, default_lang: str) -> str:
        base = getattr(self, name)
        if lang == default_lang or not base:
            return base
        return self.translations.get(name, {}).get(lang, base)


@dataclass
class Project:
    root: Path
    data: dict[str, Any]
    characters: dict[str, Character]
    scenes: list[Scene]
    speech: SpeechRules
    issues: list[Issue] = field(default_factory=list)

    # ---- convenience views
    @property
    def title(self) -> str:
        return self.data["project"]["title"]

    @property
    def language(self) -> str:
        return self.data["project"]["language"]

    @property
    def languages(self) -> list[str]:
        langs = self.data["project"].get("languages") or [self.language]
        return [self.language] + [lang for lang in langs if lang != self.language]

    @property
    def fallback(self) -> bool:
        return self.data["project"].get("missing_translation", "error") == "fallback"

    @property
    def org(self) -> dict[str, Any]:
        return self.data["organization"]

    @property
    def voices_cfg(self) -> dict[str, Any]:
        return self.data.get("voices") or {}

    @property
    def render_cfg(self) -> dict[str, Any]:
        return self.data.get("render") or {}

    def provider_defaults(self) -> dict[str, dict]:
        out = {k: dict(v) for k, v in (self.voices_cfg.get("providers") or {}).items()}
        # what the local providers need to know about the project (never written to the cache key)
        out.setdefault("recorded", {})["_project_root"] = str(self.root)
        out.setdefault("kokoro", {})["_genders"] = {cid: c.gender for cid, c in self.characters.items()}
        return out

    def enabled_scenes(self, only: Iterable[str] | None = None) -> list[Scene]:
        wanted = set(only) if only else None
        out = []
        for s in self.scenes:
            if wanted is not None:
                if s.id in wanted:
                    out.append(s)
            elif s.enabled:
                out.append(s)
        return out

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise ConfigError(f"No scene with id '{scene_id}'.", f"Scene ids: {', '.join(s.id for s in self.scenes)}")

    def path(self, raw: str, what: str, must_exist: bool = True) -> Path:
        return resolve_inside(self.root, raw, what=what, must_exist=must_exist)

    # ---- text
    def text_context(self) -> tpl.TextContext:
        org = self.org
        fields = {k: org[k] for k in ORG_FIELDS if org.get(k)}
        for k, v in ORG_DEFAULTS.items():
            fields.setdefault(k, v)
        fields.setdefault("short_name", org["name"])
        fields.setdefault("training_title", self.title)
        for k, v in (org.get("terms") or {}).items():
            if k in fields:
                continue
            fields[k] = v
        spoken = {}
        if org.get("spoken_name"):
            spoken["name"] = dict(org["spoken_name"])
            spoken.setdefault("short_name", dict(org["spoken_name"]))
        rules = self.speech
        return tpl.TextContext(
            characters={c.id: c.text_view() for c in self.characters.values()},
            org=tpl.OrgText(fields=fields, spoken=spoken, emails={"security_email"}, urls={"reporting_url"},
                            localized={k: dict(v) for k, v in (org.get("translations") or {}).items()}),
            speak_email=lambda addr, lang: speak_email(addr, lang, rules),
            speak_url=lambda url, lang: speak_url(url, lang, rules),
        )

    def resolve(self, text: str, lang: str) -> tpl.Resolved:
        return tpl.resolve(text, self.text_context(), lang)

    def display(self, text: str, lang: str) -> str:
        return self.resolve(text, lang).display if text else ""


# --------------------------------------------------------------------------- loading
_SCHEMA_CACHE: dict | None = None


def schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(resources.files("sastudio.schema").joinpath("project.schema.json").read_text("utf-8"))
    return _SCHEMA_CACHE


def _fmt_path(path: Iterable[Any]) -> str:
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(top level)"


def _schema_errors(data: Any, where: str) -> list[Issue]:
    v = Draft202012Validator(schema())
    issues = []
    for err in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = _fmt_path(err.absolute_path)
        msg = err.message
        if err.validator == "oneOf" and "lines" in loc:
            msg = "a line needs either `who` + `say` (dialogue) or `card` (on-screen text), not both"
        if err.validator == "additionalProperties":
            msg = msg.replace("Additional properties are not allowed", "Unknown setting")
        issues.append(Issue("error", f"{where} {loc}", msg))
    return issues


def load_project(root: str | Path, *, check: bool = True) -> Project:
    root = Path(root)
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        raise ConfigError(f"Project folder not found: {root}", "Run `sastudio init <folder>` to create one.")
    data = read_yaml(root / PROJECT_FILE)
    if not isinstance(data, dict):
        raise ConfigError(f"{PROJECT_FILE} must be a mapping of settings.", "See docs/CONFIGURATION.md.")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        from .migrate import migrate  # local import keeps the dependency obvious

        data = migrate(data)

    # Inline scene files before validating so the schema checks them too.
    scene_sources: list[str] = []
    expanded = []
    for i, entry in enumerate(data.get("scenes") or []):
        if isinstance(entry, dict) and "file" in entry and len(entry) <= 2:
            try:
                p = resolve_inside(root, entry["file"], what=f"scenes[{i}].file", must_exist=True)
            except UnsafePathError as e:
                raise ConfigError(str(e.message), e.hint)
            if p.suffix.lower() not in {".yaml", ".yml"}:
                raise ConfigError(f"Scene file {entry['file']} must be .yaml or .yml.")
            sdata = read_yaml(p)
            if not isinstance(sdata, dict):
                raise ConfigError(f"Scene file {entry['file']} must be a mapping.")
            if "enabled" in entry:
                sdata = {**sdata, "enabled": entry["enabled"]}
            expanded.append(sdata)
            scene_sources.append(entry["file"])
        else:
            expanded.append(entry)
            scene_sources.append(PROJECT_FILE)
    data = {**data, "scenes": expanded}

    issues = _schema_errors(data, PROJECT_FILE)
    if issues:
        raise ConfigError(
            "The project file has errors:\n  " + "\n  ".join(str(i) for i in issues[:25])
            + (f"\n  ... and {len(issues) - 25} more" if len(issues) > 25 else ""),
            "Compare with examples/ or docs/CONFIGURATION.md.",
        )

    characters = {}
    for c in data["characters"]:
        characters.setdefault(c["id"], Character(
            id=c["id"], name=c["name"].strip(), role=c.get("role", ""), description=c.get("description", ""),
            pronouns=c.get("pronouns", "they"), gender=c.get("gender", "other"), forms=c.get("forms") or {},
            spoken=c.get("spoken") or {}, pronunciation=c.get("pronunciation") or {}, attrs=c.get("attrs") or {},
            voice=c["voice"], look=c.get("look") or {},
        ))

    scenes = []
    for order, (s, src) in enumerate(zip(data["scenes"], scene_sources, strict=True)):
        lines = [
            Line(id=ln["id"], scene_id=s["id"], who=ln.get("who"), say=ln.get("say"),
                 translations=ln.get("translations") or {}, spoken=ln.get("spoken") or {},
                 emotion=ln.get("emotion"), to=ln.get("to"), pause_after=ln.get("pause_after"), card=ln.get("card"),
                 act=list(ln.get("act") or []), camera=ln.get("camera"),
                 reactions=dict(ln.get("reactions") or {}), go=ln.get("go"))
            for ln in s["lines"]
        ]
        scenes.append(Scene(
            id=s["id"], title=s["title"], lines=lines, order=order, source=src, enabled=s.get("enabled", True),
            requires=list(s.get("requires") or []), topic=s.get("topic", ""), summary=s.get("summary", ""),
            setting=s.get("setting") or {}, headline=s.get("headline", ""), takeaway=s.get("takeaway", ""),
            policy_note=s.get("policy_note", ""), max_seconds=s.get("max_seconds"), direction=s.get("direction") or {},
            translations={
                "title": s.get("title_translations") or {},
                "headline": s.get("headline_translations") or {},
                "takeaway": s.get("takeaway_translations") or {},
            },
        ))

    sp = data.get("speech") or {}
    lex = dict(DEFAULT_LEXICON)
    for term, forms in (sp.get("lexicon") or {}).items():
        if forms is None:
            lex.pop(term, None)
        else:
            lex[term] = dict(forms)
    rules = SpeechRules(lexicon=lex, email_words=sp.get("email_words") or {"default": {}})

    project = Project(root=root.resolve(), data=data, characters=characters, scenes=scenes, speech=rules)
    if check:
        project.issues = validate(project)
    return project


# --------------------------------------------------------------------------- semantic checks
# Reserved for documentation and testing (RFC 2606, RFC 6761): nobody can receive mail or reports there.
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
RESERVED_TLDS = ("example", "test", "invalid", "localhost")


def is_placeholder_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    return (any(h == d or h.endswith("." + d) for d in RESERVED_DOMAINS)
            or any(h == t or h.endswith("." + t) for t in RESERVED_TLDS))


def placeholder_contacts(project: Project) -> list[str]:
    """The reporting contacts a film would show that use reserved example domains, as 'field = value'.

    A finished film cannot be corrected after it is shared, and the reporting address is the one
    instruction every scene leads to, so a placeholder there sends real reports nowhere.
    """
    from urllib.parse import urlsplit

    org = project.org
    sources = [("organization", org)] + [(f"organization.translations.{lang}", t)
                                         for lang, t in (org.get("translations") or {}).items() if isinstance(t, dict)]
    found = []
    for where, block in sources:
        email, url = block.get("security_email"), block.get("reporting_url")
        if isinstance(email, str) and "@" in email and is_placeholder_host(email.rsplit("@", 1)[1]):
            found.append(f"{where}.security_email = {email}")
        if isinstance(url, str) and url and is_placeholder_host(urlsplit(url).hostname or ""):
            found.append(f"{where}.reporting_url = {url}")
    return found


def validate(project: Project, *, only: Iterable[str] | None = None) -> list[Issue]:
    from .voices.registry import validate_voice  # avoid import cycle

    issues: list[Issue] = []
    data = project.data

    # duplicates
    seen: dict[str, str] = {}
    for c in data["characters"]:
        if c["id"] in seen:
            issues.append(Issue("error", f"characters.{c['id']}", "This character id is used twice.",
                                "Give every character a unique id."))
        seen[c["id"]] = c["name"]
    names: dict[str, list[str]] = {}
    for cid, ch in project.characters.items():
        names.setdefault(ch.name.casefold(), []).append(cid)
        if any(b in ch.name for b in "{}"):
            issues.append(Issue("error", f"characters.{cid}.name", "Names cannot contain braces."))
    for _nm, ids in names.items():
        if len(ids) > 1:
            issues.append(Issue("warning", f"characters.{','.join(ids)}",
                                f"{len(ids)} characters share the display name '{project.characters[ids[0]].name}'.",
                                "Viewers will not know who is speaking. Use different names or a full_name form."))

    scene_ids: dict[str, int] = {}
    line_ids: set[str] = set()
    for s in project.scenes:
        if s.id in scene_ids:
            issues.append(Issue("error", f"scenes.{s.id}", "This scene id is used twice."))
        scene_ids[s.id] = s.order
        for ln in s.lines:
            if ln.id in line_ids:
                issues.append(Issue("error", f"{s.id}.{ln.id}", "This line id is used twice in the project.",
                                    "Line ids must be unique so cached audio maps to one line."))
            line_ids.add(ln.id)

    # paths
    org = project.org
    if org.get("logo"):
        _check_file(project, org["logo"], "organization.logo", IMAGE_EXTS, issues)
    for cid, ch in project.characters.items():
        if ch.look.get("portrait"):
            _check_file(project, ch.look["portrait"], f"characters.{cid}.look.portrait", IMAGE_EXTS, issues)
        if ch.look.get("model"):
            _check_file(project, ch.look["model"], f"characters.{cid}.look.model", MODEL_EXTS, issues, 300_000_000)
            if not str(ch.look.get("model_license") or "").strip():
                issues.append(Issue("error", f"characters.{cid}.look.model_license",
                                    "A 3D model needs its licence recorded.",
                                    'Add `model_license: "..."` (for example "CC BY 4.0, author, link" or "made by me").'))
    if project.render_cfg.get("music"):
        _check_file(project, project.render_cfg["music"], "render.music", AUDIO_EXTS, issues)
    for s in project.scenes:
        if s.setting.get("image"):
            _check_file(project, s.setting["image"], f"{s.id}.setting.image", IMAGE_EXTS, issues)
    if project.render_cfg.get("output"):
        try:
            resolve_inside(project.root, project.render_cfg["output"], what="render.output")
        except UnsafePathError as e:
            issues.append(Issue("error", "render.output", e.message, e.hint))
    if project.render_cfg.get("renderer") == "clay":
        from .render.clay import engine_included

        if not engine_included():
            issues.append(Issue("error", "render.renderer", "The clay renderer is not included in this release.",
                                "Set render.renderer to cards (docs/RENDERING.md)."))

    # scene dependencies, against what will actually be built
    building = {s.id for s in project.enabled_scenes(only)}
    for s in project.scenes:
        if s.id not in building:
            continue
        for req in s.requires:
            if req not in scene_ids:
                issues.append(Issue("error", f"{s.id}.requires", f"Unknown scene '{req}'."))
            elif req not in building:
                issues.append(Issue(
                    "error", f"{s.id}.requires",
                    f"Scene '{s.id}' builds on scene '{req}', which is turned off.",
                    f"Turn '{req}' back on, turn '{s.id}' off, or edit '{s.id}' so it stands alone and remove the requirement.",
                ))
            elif scene_ids[req] > s.order:
                issues.append(Issue("error", f"{s.id}.requires", f"Scene '{req}' comes after '{s.id}' in the film.",
                                    "Move the required scene earlier."))

    # dialogue: speakers, tokens in every language, literal names, voices
    ctx = project.text_context()
    literal_names = {cid: c.name for cid, c in project.characters.items() if len(c.name) >= 3}
    voice_checked: set[tuple] = set()
    for s in project.enabled_scenes(only):
        for field_name in ("title", "headline", "takeaway"):
            for lang in project.languages:
                txt = s.field_for(field_name, lang, project.language)
                if txt:
                    _check_tokens(txt, ctx, lang, f"{s.id}.{field_name}", issues)
        for ln in s.lines:
            where = f"{s.id}.{ln.id}"
            if ln.who and ln.who not in project.characters:
                issues.append(Issue("error", where, f"Speaker '{ln.who}' is not a character.",
                                    f"Character ids: {', '.join(project.characters)}"))
                continue
            if ln.to and ln.to not in project.characters:
                issues.append(Issue("error", where, f"Addressee '{ln.to}' is not a character."))
            for lang in project.languages:
                t = ln.template_for(lang, project.language, project.fallback)
                if t is None:
                    issues.append(Issue("error", where, f"No {lang} text.",
                                        f"Add translations.{lang}, or set project.missing_translation: fallback."))
                    continue
                if lang != project.language and ln.template_for(lang, project.language, False) is None:
                    issues.append(Issue("warning", where, f"No {lang} text; the {project.language} text is used."))
                _check_tokens(t, ctx, lang, where, issues)
                if lang == project.language:
                    for cid, hit in tpl.find_literal_names(t, literal_names):
                        issues.append(Issue("warning", where,
                                            f"'{hit}' is written as plain text. Renaming {cid} will not change it.",
                                            f"Write {{{cid}}} instead."))
                if ln.who:
                    spec = project.characters[ln.who].voice_for(lang, project.provider_defaults())
                    key = (ln.who, lang)
                    if key not in voice_checked:
                        voice_checked.add(key)
                        for msg, hint in validate_voice(spec, lang):
                            issues.append(Issue("error", f"characters.{ln.who}.voice ({lang})", msg, hint))
    from . import direction

    for pr in direction.validate(project):
        issues.append(Issue(pr.level, pr.where, pr.message, pr.hint))
    return issues


def _check_tokens(text: str, ctx: tpl.TextContext, lang: str, where: str, issues: list[Issue]) -> None:
    try:
        tpl.resolve(text, ctx, lang)
    except TemplateError as e:
        issues.append(Issue("error", where, e.message, e.hint))


def _check_file(project: Project, raw: str, where: str, exts: set[str], issues: list[Issue],
                max_bytes: int = 50_000_000) -> None:
    try:
        p = resolve_inside(project.root, raw, what=where, must_exist=True)
    except UnsafePathError as e:
        issues.append(Issue("error", where, e.message, e.hint))
        return
    if p.suffix.lower() not in exts:
        issues.append(Issue("error", where, f"'{raw}' must be one of: {', '.join(sorted(exts))}."))
    elif p.stat().st_size > max_bytes:
        issues.append(Issue("error", where, f"'{raw}' is larger than {max_bytes // 1_000_000} MB."))
    elif exts is IMAGE_EXTS:
        from .render.style import load_image  # decode it now, so a broken image fails here, not mid-render

        try:
            load_image(p, max_side=64)
        except ConfigError as e:
            issues.append(Issue("error", where, f"'{raw}': {e.message}", e.hint))


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "error"]
