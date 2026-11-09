"""Release-scope behaviour: the clay engine may be absent, diagnostics must tell the truth, and
documented promises (portrait copies, clean) must match what the code does."""

import os
import stat
import sys
from pathlib import Path

import pytest

from sastudio import build as build_mod
from sastudio import doctor
from sastudio.cli import main
from sastudio.errors import ConfigError, ToolMissing
from sastudio.project import load_project, validate
from sastudio.render import clay

from .conftest import write_project

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.setattr(clay, "engine_included", lambda: False)


def _with_clay_renderer(root: Path) -> Path:
    f = root / "studio.yaml"
    f.write_text(f.read_text("utf-8").replace("  preset: draft", "  renderer: clay\n  preset: draft"), "utf-8")
    return root


def test_clay_commands_explain_the_missing_engine(project_dir, no_engine, capsys):
    for action in ("build", "portraits"):
        assert main(["clay", action, str(project_dir)]) == ToolMissing.exit_code
        err = capsys.readouterr().err
        assert "not included in this release" in err and "cards renderer" in err
    assert not (project_dir / ".studio" / "rig").exists()


def test_clay_render_fails_before_any_voice_or_output_work(project_dir, no_engine):
    project = load_project(project_dir)
    with pytest.raises(ToolMissing, match="not included"):
        build_mod.build(project, renderer="clay", fallback="offline", log=lambda _m: None)
    assert not (project_dir / "build").exists()
    assert not (project_dir / ".studio").exists()


def test_validate_flags_clay_only_when_engine_is_absent(tmp_path, monkeypatch):
    root = _with_clay_renderer(write_project(tmp_path / "p"))
    monkeypatch.setattr(clay, "engine_included", lambda: False)
    issues = validate(load_project(root))
    assert any(i.where == "render.renderer" and i.level == "error" for i in issues)
    monkeypatch.setattr(clay, "engine_included", lambda: True)
    assert not any(i.where == "render.renderer" for i in validate(load_project(root)))


def test_cards_projects_never_mention_clay(project_dir, no_engine):
    assert not any(i.where == "render.renderer" for i in validate(load_project(project_dir)))


@pytest.mark.parametrize(("value", "expected"), [(None, "GPU"), ("GPU", "GPU"), ("cpu", "CPU"), (" Cpu ", "CPU")])
def test_clay_device_override(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("SASTUDIO_CLAY_DEVICE", raising=False)
    else:
        monkeypatch.setenv("SASTUDIO_CLAY_DEVICE", value)
    assert clay.clay_device() == expected


def test_clay_device_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("SASTUDIO_CLAY_DEVICE", "tpu")
    with pytest.raises(ConfigError, match="GPU or CPU"):
        clay.clay_device()


def test_doctor_hides_blender_checks_without_the_engine(no_engine):
    names = [c.name for c in doctor.run_checks()]
    assert "Clay renderer" in names
    assert "Rhubarb Lip Sync" not in names and "Blender (clay renderer)" not in names
    assert all(c.status != "fail" for c in doctor.run_checks() if c.name == "Clay renderer")


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell script as a stand-in for nvidia-smi")
def test_doctor_finds_the_wsl_nvidia_tool_off_path(tmp_path, monkeypatch):
    fake = tmp_path / "nvidia-smi"
    fake.write_text("#!/bin/sh\necho 'Example GPU, 6144 MiB, 1.0'\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor, "WSL_NVIDIA_SMI", fake)
    monkeypatch.setattr(doctor, "WSL_GPU_DEVICE", tmp_path / "missing-dxg")
    assert doctor.gpu_check().detail == "Example GPU, 6144 MiB, 1.0"


def test_doctor_gpu_fallbacks(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor, "WSL_NVIDIA_SMI", tmp_path / "missing-smi")
    dxg = tmp_path / "dxg"
    monkeypatch.setattr(doctor, "WSL_GPU_DEVICE", dxg)
    assert doctor.gpu_check().detail.startswith("no GPU detected")
    dxg.write_bytes(b"")
    assert "/dev/dxg" in doctor.gpu_check().detail
    assert doctor.gpu_check().status == "info"


def test_clean_removes_work_but_keeps_films_and_voice_cache(project_dir, capsys):
    work = project_dir / ".studio" / "work" / "en-IN"
    cache = project_dir / ".studio" / "cache" / "voices"
    film = project_dir / "build" / "en-IN" / "film.mp4"
    for p in (work / "x.mp4", cache / "offline" / "a.wav", film):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    assert main(["clean", str(project_dir)]) == 0
    assert not (project_dir / ".studio" / "work").exists()
    assert film.exists() and (cache / "offline" / "a.wav").exists()
    out = capsys.readouterr().out
    assert "Kept" in out and "voice cache" in out


@pytest.mark.skipif(not (REPO / "docs" / "media" / "characters").is_dir(), reason="docs are not part of this install")
def test_documented_portraits_are_the_template_portraits():
    docs = REPO / "docs" / "media" / "characters"
    tpl = REPO / "src" / "sastudio" / "templates" / "starter" / "assets" / "characters"
    names = sorted(p.name for p in tpl.glob("*.png"))
    assert names == ["aarav.png", "leo.png", "mira.png", "nadia.png", "rook.png"]
    for name in names:
        assert (docs / name).read_bytes() == (tpl / name).read_bytes(), f"{name} differs; copy it to both places"


def test_engine_file_list_matches_the_package_layout():
    # Every listed engine file sits under the engine package, so restoring them re-enables clay.
    assert all(not os.path.isabs(rel) and ".." not in rel for rel in clay.ENGINE_FILES)
    assert {rel.split("/")[0] for rel in clay.ENGINE_FILES} == {"clay", "sculpt"}


def test_hindi_output_survives_a_legacy_console_encoding(tmp_path, monkeypatch):
    # Windows uses a legacy code page (cp1252) for piped output, which cannot encode Devanagari.
    import io

    from sastudio import cli

    dest = tmp_path / "short"
    assert main(["init", str(dest), "--template", "short"]) == 0
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(cli.sys, "stdout", legacy)
    assert main(["script", str(dest), "--lang", "hi-IN", "--scenes", "report_early"]) == 0
    legacy.flush()
    assert "कबीर".encode() not in raw.getvalue()  # the short template's Leo is still Leo
    assert "लियो".encode() in raw.getvalue()


@pytest.mark.parametrize(("err", "fix"), [
    (OSError(13, "Permission denied", "build/en-IN"), "allowed to write"),
    (OSError(28, "No space left on device", "build/en-IN/film.mp4"), "free some disk space"),
])
def test_filesystem_errors_are_explained_not_dumped(project_dir, monkeypatch, capsys, err, fix):
    import errno as _errno

    err.errno = {13: _errno.EACCES, 28: _errno.ENOSPC}[err.errno]

    def boom(*_a, **_k):
        raise err

    monkeypatch.setattr(build_mod, "build", boom)
    assert main(["render", str(project_dir)]) == 1
    out = capsys.readouterr().err
    assert "Traceback" not in out and fix in out


def test_corrupt_image_is_a_validation_error(project_dir):
    (project_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really a png" * 20)
    f = project_dir / "studio.yaml"
    f.write_text(f.read_text("utf-8").replace('  name: "Test Org"\n', '  name: "Test Org"\n  logo: logo.png\n'),
                 encoding="utf-8")
    issues = validate(load_project(project_dir))
    assert any(i.where == "organization.logo" and "not a readable image" in i.message for i in issues)


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="needs FFmpeg")
@pytest.mark.parametrize("size", [(1600, 90), (90, 900), (300, 300)], ids=["very-wide", "very-tall", "square"])
def test_logos_of_any_shape_render(tmp_path, size):
    from PIL import Image

    root = write_project(tmp_path / "p")
    Image.new("RGBA", size, (30, 78, 95, 0)).save(root / "logo.png")  # fully transparent edges are fine too
    f = root / "studio.yaml"
    f.write_text(f.read_text("utf-8").replace('  name: "Test Org"\n', '  name: "Test Org"\n  logo: logo.png\n'),
                 encoding="utf-8")
    res = build_mod.build(load_project(root), scene_ids=["one"], preset="draft", log=lambda _m: None)
    assert res.video.exists() and res.rendered == ["one"]


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="needs FFmpeg")
def test_damaged_stored_scene_is_rendered_again(project_dir):
    project = load_project(project_dir)
    first = build_mod.build(project, scene_ids=["one"], preset="draft", log=lambda _m: None)
    assert first.rendered == ["one"]
    stored = next((project_dir / ".studio" / "work" / "en-IN" / "scenes").glob("one.draft.mp4"))
    stored.write_bytes(stored.read_bytes()[:2000])  # truncated, but its key file still matches
    messages = []
    again = build_mod.build(load_project(project_dir), scene_ids=["one"], preset="draft", log=messages.append)
    assert again.rendered == ["one"] and again.reused == []
    assert any("damaged" in m for m in messages)
    unchanged = build_mod.build(load_project(project_dir), scene_ids=["one"], preset="draft", log=lambda _m: None)
    assert unchanged.reused == ["one"]


def test_network_failures_become_retryable_provider_errors(monkeypatch):
    import urllib.error

    from sastudio.errors import ProviderError
    from sastudio.voices import base

    def offline(*_a, **_k):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(base.urllib.request, "urlopen", offline)
    with pytest.raises(ProviderError, match="Network error") as e:
        base.urllib_transport("POST", "https://api.example.com/tts", {}, b"{}", 5)
    assert e.value.retryable

    def slow(*_a, **_k):
        raise TimeoutError

    monkeypatch.setattr(base.urllib.request, "urlopen", slow)
    with pytest.raises(ProviderError, match="timed out") as e:
        base.urllib_transport("POST", "https://api.example.com/tts", {}, b"{}", 5)
    assert e.value.retryable and e.value.code == "timeout"
    with pytest.raises(ProviderError, match="non-HTTPS"):
        base.urllib_transport("POST", "http://api.example.com/tts", {}, b"{}", 5)
