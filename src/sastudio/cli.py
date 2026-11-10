"""Command line: `sastudio <command>`. Run `sastudio --help`."""

from __future__ import annotations

import argparse
import errno
import json
import re
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .errors import StudioError
from .safepath import atomic_write_text

TEMPLATES = ("starter", "short", "education")


def _scenes(arg: str | None) -> list[str] | None:
    return [s.strip() for s in arg.split(",") if s.strip()] if arg else None


def _load(path: str):
    from .project import load_project
    from .voices.registry import set_provider_configs

    p = load_project(path)
    set_provider_configs(p.provider_defaults())
    return p


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _init_options(a) -> dict:
    """Check every `init` option before anything is created, so a typo never leaves a half-made folder."""
    from .render import figures

    out: dict = {}
    for flag, value, limit in (("--org", a.org, 80), ("--short-name", a.short_name, 30)):
        if value is not None:
            value = value.strip()
            if not value or len(value) > limit or any(ord(c) < 32 for c in value) or any(c in value for c in "{}"):
                raise StudioError(f"{flag} must be 1-{limit} characters on one line, without braces.")
            out[flag] = value
    if a.email is not None:
        if not EMAIL_RE.match(a.email) or len(a.email) > 254:
            raise StudioError(f"--email '{a.email}' is not an email address.", "Use the address people should report to.")
        out["--email"] = a.email
    if a.report_url is not None:
        if not re.match(r"^https://[^\s]+$", a.report_url) or len(a.report_url) > 300:
            raise StudioError("--report-url must be an https:// address without spaces.")
        out["--report-url"] = a.report_url
    if a.style is not None:
        code = figures.STYLE_ALIASES.get(a.style.lower())
        if code is None:
            raise StudioError(f"Unknown style '{a.style}'.", "Use v1 (sketch), v2 (flat), v3 (cutout) or v4 (clay).")
        out["--style"] = code
    if a.logo is not None:
        from PIL import Image

        logo = Path(a.logo)
        try:
            with Image.open(logo) as im:
                im.load()
                out["--logo"] = im.convert("RGBA")
        except (OSError, ValueError) as e:
            raise StudioError(f"--logo {logo} is not a readable image ({e}).", "Use a PNG or JPEG file.") from None
    return out


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid YAML double-quoted string


def _short_name(org: str) -> str:
    if len(org) <= 18:
        return org
    words = [w.strip(",.") for w in org.split() if w.lower() not in ("the", "a")]
    return (words[0] if words else org)[:30]


def cmd_init(a) -> int:
    dest = Path(a.folder)
    if dest.exists() and any(dest.iterdir()):
        raise StudioError(f"{dest} already exists and is not empty.", "Choose a new folder name.")
    if a.template not in TEMPLATES:
        raise StudioError(f"Unknown template '{a.template}'.", f"Templates: {', '.join(TEMPLATES)}")
    opts = _init_options(a)
    skip = shutil.ignore_patterns("__pycache__", "__init__.py")
    # Every template shares the starter's scenes and artwork; a template folder only overrides studio.yaml.
    for name in dict.fromkeys(["starter", a.template]):
        with resources.as_file(resources.files("sastudio.templates").joinpath(name)) as s:
            shutil.copytree(s, dest, dirs_exist_ok=True, ignore=skip)
    if opts:
        yml = dest / "studio.yaml"
        text = yml.read_text("utf-8")
        fields = {"name": opts.get("--org"), "short_name": opts.get("--short-name"),
                  "security_email": opts.get("--email"), "reporting_url": opts.get("--report-url")}
        if fields["name"] and not fields["short_name"]:
            fields["short_name"] = _short_name(fields["name"])
        for key, value in fields.items():
            if value is not None:
                # replace only the value: the comments that explain each line stay
                text, n = re.subn(rf'^  {key}: "[^"\n]*"', lambda _m, k=key, v=value: f"  {k}: {_yaml_str(v)}",
                                  text, count=1, flags=re.M)
                if n != 1:
                    raise StudioError(f"The {a.template} template has no organization.{key} line to set.")
        if "--style" in opts:
            text, n = re.subn(r"^  # character_style: v2 [^\n]*$", f"  character_style: {opts['--style']}", text,
                              count=1, flags=re.M)
            if n != 1:
                raise StudioError(f"The {a.template} template has no character_style line to set.")
        atomic_write_text(yml, text)
        if "--logo" in opts:
            opts["--logo"].save(dest / "assets" / "logo.png")
    print(f"Created {dest}.")
    from .project import load_project, placeholder_contacts

    p = load_project(dest)
    for found in placeholder_contacts(p):
        print(f"  Still a placeholder: {found}. Set it with --email / --report-url, or in studio.yaml,"
              " before a final render.")
    print(f"Next:\n  sastudio validate {dest}\n  sastudio characters {dest} --sheet {dest / 'cast.png'}\n"
          f"  sastudio render {dest} --preset draft")
    return 0


def cmd_doctor(a) -> int:
    from .doctor import format_checks, run_checks

    checks = run_checks(Path(a.project) if a.project else None)
    print(f"Security Awareness Studio {__version__}")
    print(format_checks(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0


def cmd_validate(a) -> int:
    from .project import validate

    p = _load(a.project)
    issues = validate(p, only=_scenes(a.scenes))
    for i in issues:
        print(i)
    errs = sum(1 for i in issues if i.level == "error")
    warns = len(issues) - errs
    from .project import placeholder_contacts

    for found in placeholder_contacts(p):
        print(f"[note] {found}: a placeholder nobody receives. Replace it before a final render; "
              "`render --preset final` refuses it.")
    print(f"{errs} error(s), {warns} warning(s) in {len(p.enabled_scenes(_scenes(a.scenes)))} scene(s), "
          f"{len(p.characters)} character(s), languages {', '.join(p.languages)}.")
    return 2 if errs or (a.strict and warns) else 0


def cmd_scenes(a) -> int:
    p = _load(a.project)
    for s in p.scenes:
        speak = sum(1 for ln in s.lines if not ln.is_card)
        req = f" requires {', '.join(s.requires)}" if s.requires else ""
        print(f"{'on ' if s.enabled else 'off'}  {s.id:<22} {speak:>3} lines  {s.title}{req}")
    return 0


def cmd_characters(a) -> int:
    p = _load(a.project)
    used: dict[str, list[str]] = {}
    for s in p.scenes:
        for ln in s.lines:
            if ln.who and s.id not in used.setdefault(ln.who, []):
                used[ln.who].append(s.id)
    for cid, c in p.characters.items():
        print(f"{cid:<14} {c.name:<18} {c.role}")
        for lang in p.languages:
            v = c.voice_for(lang, p.provider_defaults())
            who = v.speaker or v.voice_id or "-"
            print(f"    {lang}: {v.provider} {v.model or ''} {who}")
        print(f"    scenes: {', '.join(used.get(cid, [])) or '(none)'}")
        print(f"    style: {_style_of(p, c)}")
    if getattr(a, "sheet", None):
        from .build import cast_sheet

        styles = [x.strip() for x in (a.styles or "v1,v2,v3,v4").split(",") if x.strip()]
        out = Path(a.sheet)
        if out.suffix.lower() != ".png":
            raise StudioError("The sheet is written as a PNG image.", "Give a file name ending in .png.")
        im = cast_sheet(p, styles)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, optimize=True)
        print(f"Cast sheet: {out} ({im.width}x{im.height}, styles {', '.join(styles)})")
    return 0


def _style_of(p, c) -> str:
    from .render import figures

    look = c.look or {}
    code = figures.style_code(look.get("style") or p.render_cfg.get("character_style"))
    if code == "v4" and not look.get("portrait") and look.get("design"):
        code = "v2"
    drawable = look.get("design") or look.get("preset") in figures.BUILTIN_DESIGNS
    if code in figures.DRAWN_STYLES and not drawable:
        return f"{code} requested, but there is no look.design or bundled preset to draw; the portrait is used"
    return f"{code} {figures.STYLES[code]}" + (" (drawn, animated)" if code in figures.DRAWN_STYLES else " (portrait)")


def cmd_script(a) -> int:
    """Print every line as viewers will read it and as the voice will say it."""
    from .voices.engine import build_plan

    p = _load(a.project)
    lang = a.lang or p.language
    plan = {it.utt.line_id: it for it in build_plan(p, [lang], _scenes(a.scenes)).items}
    for s in p.enabled_scenes(_scenes(a.scenes)):
        print(f"\n== {s.id}: {p.display(s.field_for('title', lang, p.language), lang)}")
        for ln in s.lines:
            tmpl = ln.template_for(lang, p.language, p.fallback)
            if ln.is_card:
                print(f"  [card] {p.display(tmpl, lang)}")
                continue
            name = p.characters[ln.who].text_view().form("name", lang)
            print(f"  {name}: {p.display(tmpl, lang)}")
            it = plan.get(ln.id)
            if it and it.req.text != p.display(tmpl, lang):
                print(f"      says ({it.req.provider}): {it.req.text}")
            for adv in (it.advice if it else []):
                print(f"      note: {adv}")
    return 0


def _print_plan(p, plan) -> None:
    summ = plan.summary()
    for prov, info in summ.items():
        print(f"{prov}: {info['lines']} lines, {info['cached']} cached, {info['to_generate']} to generate, "
              f"{info['characters']:,} characters")
    rows = plan.cost(p.voices_cfg.get("prices") or {})
    for r in rows:
        if r["provider"] == "offline":
            continue
        if "estimate" in r:
            print(f"  {r['provider']} {r['model']}: {r['characters']:,} chars ~ {r['estimate']} {r['currency']} "
                  f"(your price table, checked {r['price_checked']}; providers can change prices)")
        else:
            print(f"  {r['provider']} {r['model']}: {r['characters']:,} chars (no price in voices.prices; "
                  f"see your provider's pricing page)")


def cmd_voices(a) -> int:
    from .voices.engine import build_plan, generate

    p = _load(a.project)
    langs = [a.lang] if a.lang else p.languages
    plan = build_plan(p, langs, _scenes(a.scenes))
    if a.action == "plan":
        _print_plan(p, plan)
        return 0
    if a.action == "generate":
        _print_plan(p, plan)
        if not a.live:
            print("Dry run: free offline voices are generated; nothing paid is requested. Add --live to call paid providers.")
        rep = generate(p, plan, live=a.live, max_characters=a.max_characters, max_requests=a.max_requests)
        print(f"generated {rep.generated}, reused {rep.reused}, paid lines waiting {rep.skipped_paid}, "
              f"billable characters sent {rep.characters_billed:,}, requests {rep.requests}")
        return 0
    if a.action == "lexicon":
        from .voices.lexicon import export

        out = Path(a.out)
        export(p, a.format, out)
        print(f"Wrote {out}")
        return 0
    return 2


def cmd_credentials(a) -> int:
    from .voices.engine import credentials, redact

    root = Path(a.project) if a.project else Path.cwd()
    env = credentials(root)
    for k in ("SARVAM_API_KEY", "ELEVENLABS_API_KEY"):
        print(f"{k}: {redact(env.get(k))}")
    print("Keys are only read from the environment or a .env file; they are never written to project files, "
          "caches, logs or manifests. This check makes no network request.")
    return 0


def cmd_render(a) -> int:
    from .build import build

    p = _load(a.project)
    res = build(p, language=a.lang, scene_ids=_scenes(a.scenes), preset=a.preset, fallback=a.voice_fallback,
                burn=True if a.burn_subtitles else None, jobs=a.jobs, renderer=a.renderer,
                allow_placeholder_contacts=a.allow_placeholder_contacts)
    for w in res.warnings:
        print(f"warning: {w}")
    print(json.dumps({"video": str(res.video), "srt": str(res.srt), "vtt": str(res.vtt),
                      "transcript": str(res.transcript), "rendered": res.rendered, "reused": res.reused}, indent=1))
    return 0


def cmd_clay(a) -> int:
    from .render import clay

    p = _load(a.project)
    if a.action == "build":
        print(f"Rigs: {clay.build_rigs(p, jobs=a.jobs)}")
    else:
        made = clay.render_portraits(p, force=a.force)
        print(f"{len(made)} portrait(s) written to assets/characters/")
    return 0


def cmd_clean(a) -> int:
    from .build import clean

    p = _load(a.project)
    clean(p)
    print("Removed scene videos and work files (.studio/work). Kept: finished films in the output folder "
          "and the voice cache.")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sastudio", description="Build captioned security-awareness training films.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a new project from a template")
    s.add_argument("folder")
    s.add_argument("--template", default="starter", choices=TEMPLATES)
    s.add_argument("--org", help="your organisation's name, as shown and spoken")
    s.add_argument("--short-name", help="a short form of the name (default: taken from --org)")
    s.add_argument("--email", help="where people report incidents, e.g. security@your-org.in")
    s.add_argument("--report-url", help="an https:// form or portal for reports (optional)")
    s.add_argument("--style", help="character style: v1 sketch, v2 flat, v3 cutout, v4 clay (default)")
    s.add_argument("--logo", help="your logo (PNG or JPEG); saved as assets/logo.png")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="check your computer for everything needed")
    s.add_argument("project", nargs="?")
    s.set_defaults(fn=cmd_doctor)

    for name, fn, hlp in (("validate", cmd_validate, "check a project for mistakes"),
                          ("scenes", cmd_scenes, "list scenes"), ("characters", cmd_characters, "list characters and voices")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("project")
        if name == "validate":
            s.add_argument("--scenes")
            s.add_argument("--strict", action="store_true", help="treat warnings as errors")
        if name == "characters":
            s.add_argument("--sheet", metavar="FILE.png", help="draw the cast in every style into one image")
            s.add_argument("--styles", metavar="v1,v2,v3,v4", help="which styles the sheet shows (default: all four)")
        s.set_defaults(fn=fn)

    s = sub.add_parser("script", help="print the resolved script (what is shown and what is spoken)")
    s.add_argument("project")
    s.add_argument("--lang")
    s.add_argument("--scenes")
    s.set_defaults(fn=cmd_script)

    s = sub.add_parser("voices", help="plan or generate dialogue audio")
    s.add_argument("action", choices=["plan", "generate", "lexicon"])
    s.add_argument("project")
    s.add_argument("--lang")
    s.add_argument("--scenes")
    s.add_argument("--live", action="store_true", help="allow paid API requests (needs a budget)")
    s.add_argument("--max-characters", type=int, help="billable character budget for this run")
    s.add_argument("--max-requests", type=int)
    s.add_argument("--format", choices=["elevenlabs-rules", "elevenlabs-pls", "sarvam-dict"], default="elevenlabs-rules")
    s.add_argument("--out", default="pronunciations.json")
    s.set_defaults(fn=cmd_voices)

    s = sub.add_parser("credentials", help="show which API keys are set (never their values)")
    s.add_argument("project", nargs="?")
    s.set_defaults(fn=cmd_credentials)

    s = sub.add_parser("render", help="render the film or some scenes")
    s.add_argument("project")
    s.add_argument("--scenes", help="comma-separated scene ids")
    s.add_argument("--lang")
    s.add_argument("--preset", choices=["draft", "preview", "final"])
    s.add_argument("--voice-fallback", choices=["offline"], help="use free placeholder voices for lines not generated yet")
    s.add_argument("--burn-subtitles", action="store_true")
    s.add_argument("--allow-placeholder-contacts", action="store_true",
                   help="allow a final film whose reporting address is an example placeholder (demos only)")
    s.add_argument("--jobs", type=int)
    from .render.clay import engine_included

    clay_in = engine_included()
    s.add_argument("--renderer", choices=["cards", "clay"],
                   help="cards (any computer) or clay (Blender, GPU recommended)" if clay_in
                   else "cards (the default). clay is not included in this release")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("clay", help="build clay characters or render their portraits (needs Blender)" if clay_in
                       else "clay renderer tools (not included in this release)")
    s.add_argument("action", choices=["build", "portraits"])
    s.add_argument("project")
    s.add_argument("--force", action="store_true", help="replace existing portraits")
    s.add_argument("--jobs", type=int, default=2)
    s.set_defaults(fn=cmd_clay)

    s = sub.add_parser("clean", help="delete scene videos and work files (keeps finished films and the voice cache)")
    s.add_argument("project")
    s.set_defaults(fn=cmd_clean)
    return ap


def _utf8_output() -> None:
    """Dialogue may be Hindi or any script. On Windows, piped or redirected output defaults to a
    legacy code page that cannot encode it, so switch such streams to UTF-8 instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - stream already written to in an odd state
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except StudioError as e:
        print(f"error: {e.message}", file=sys.stderr)
        if e.hint:
            print(f"  fix: {e.hint}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("Interrupted. Finished voices and scenes are kept; run the same command again to continue.", file=sys.stderr)
        return 130
    except OSError as e:  # the computer, not the project: permissions, a full disk, a missing drive
        where = f": {e.filename}" if getattr(e, "filename", None) else ""
        print(f"error: {e.strerror or e}{where}", file=sys.stderr)
        if e.errno == errno.ENOSPC:
            print("  fix: free some disk space and run the same command again; finished work is kept.", file=sys.stderr)
        else:
            print("  fix: check that the folder exists and that you are allowed to write to it.", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
