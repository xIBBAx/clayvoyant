import json
import os

import pytest

from sastudio.cli import main
from sastudio.project import load_project
from sastudio.subtitles import Cue, check, chunk, cues_for_line, to_srt, to_vtt, wrap

from .conftest import HAS_FFMPEG, write_project


# ------------------------------------------------------------------ subtitles
def test_wrap_and_chunk_limits():
    text = "If something feels off, stop and check, then tell the security team at security at example dot com right away."
    for c in chunk(text):
        lines = wrap(c)
        assert len(lines) <= 2 and all(len(x) <= 42 for x in lines)
    assert wrap("short") == ["short"]


def test_cues_cover_the_line():
    cues = cues_for_line("One sentence here. Another sentence follows it closely and is long enough to split.", 1.0, 6.0,
                         speaker="Ana", line_id="l1")
    assert cues[0].start == 1.0 and abs(cues[-1].end - 6.0) < 1e-6
    assert all(a.end <= b.start + 1e-6 for a, b in zip(cues, cues[1:]))


def test_srt_vtt_format_and_markup_escape():
    cues = [Cue(0.0, 1.5, "Hello <b>world</b>", "Ana", "l1"), Cue(3661.25, 3662.0, "Second", "Dev", "l2")]
    srt = to_srt(cues)
    assert "1\n00:00:00,000 --> 00:00:01,500\nHello ‹b›world‹/b›" in srt
    assert "01:01:01,250 --> 01:01:02,000" in srt
    vtt = to_vtt(cues, language="en-IN")
    assert vtt.startswith("WEBVTT") and "<v Ana>Hello" in vtt and "00:00:00.000 --> 00:00:01.500" in vtt


def test_subtitle_checks_flag_overlap_and_speed():
    warns = check([Cue(0, 1, "x" * 40, "A", "a"), Cue(0.5, 2, "ok", "B", "b")])
    assert any("overlap" in w for w in warns) and any("per second" in w for w in warns)


# ------------------------------------------------------------------ CLI
def test_cli_validate_exit_codes(project_dir, capsys):
    assert main(["validate", str(project_dir)]) == 0
    t = (project_dir / "studio.yaml").read_text(encoding="utf-8").replace("who: dev, say", "who: zed, say")
    (project_dir / "studio.yaml").write_text(t, encoding="utf-8")
    assert main(["validate", str(project_dir)]) == 2


def test_cli_credentials_never_prints_values(project_dir, capsys, monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk-very-secret-value")
    assert main(["credentials", str(project_dir)]) == 0
    out = capsys.readouterr().out
    assert "sk-very-secret-value" not in out and "set (20 characters)" in out


def test_cli_init_refuses_non_empty(tmp_path, capsys):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "file").write_text("keep", encoding="utf-8")
    assert main(["init", str(tmp_path / "x")]) != 0
    assert (tmp_path / "x" / "file").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("template", ["starter", "short", "education"])
def test_templates_validate_cleanly(tmp_path, template, capsys):
    dest = tmp_path / template
    assert main(["init", str(dest), "--template", template]) == 0
    assert main(["validate", str(dest), "--strict"]) == 0


def test_lexicon_export(tmp_path):
    dest = tmp_path / "s"
    main(["init", str(dest), "--template", "short"])
    for fmt in ("elevenlabs-rules", "elevenlabs-pls", "sarvam-dict"):
        out = tmp_path / f"lex.{fmt}"
        assert main(["voices", "lexicon", str(dest), "--format", fmt, "--out", str(out)]) == 0
        assert out.stat().st_size > 20
    d = json.loads((tmp_path / "lex.sarvam-dict").read_text(encoding="utf-8"))
    assert d["pronunciations"]["hi-IN"]["Aarav"] == "आरव"


# ------------------------------------------------------------------ end-to-end build
@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_build_end_to_end(project_dir):
    from sastudio.build import build, probe_summary

    p = load_project(project_dir)
    res = build(p, preset="draft", jobs=2, log=lambda m: None)
    probe = probe_summary(res.video)
    man = json.loads(res.manifest.read_text(encoding="utf-8"))
    total = sum(s["frames"] for s in man["scenes"])
    assert probe["video_frames"] == total and probe["fps"] == "24/1"
    assert abs(probe["audio_seconds"] - total / 24) < 0.1
    assert probe["audio_rate"] == 48000 and probe["color"][0] == "bt709"
    assert res.srt.read_text(encoding="utf-8").count("-->") >= 3 and res.vtt.read_text(encoding="utf-8").startswith("WEBVTT")
    assert str(project_dir) not in res.manifest.read_text(encoding="utf-8")  # no local paths leak into the manifest
    # second build: nothing re-rendered
    res2 = build(load_project(project_dir), preset="draft", jobs=2, log=lambda m: None)
    assert res2.rendered == [] and len(res2.reused) == len(man["scenes"])
    # rename a character: only scenes that show the name re-render
    t = (project_dir / "studio.yaml").read_text(encoding="utf-8").replace("    name: Dev\n", "    name: Aarav\n")
    (project_dir / "studio.yaml").write_text(t, encoding="utf-8")
    res3 = build(load_project(project_dir), preset="draft", jobs=2, log=lambda m: None)
    assert "one" in res3.rendered and "Aarav" in res3.srt.read_text(encoding="utf-8")


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_build_single_scene_and_dependency_guard(project_dir):
    from sastudio.build import build
    from sastudio.errors import ConfigError

    p = load_project(project_dir)
    res = build(p, scene_ids=["one"], preset="draft", log=lambda m: None)
    assert res.video.exists()
    with pytest.raises(ConfigError):
        build(load_project(project_dir), scene_ids=["two"], preset="draft", log=lambda m: None)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_paid_lines_without_audio_need_explicit_fallback(tmp_path):
    from sastudio.build import build
    from sastudio.errors import RenderError

    root = write_project(tmp_path / "p", dev_provider="sarvam", dev_extra=', model: "bulbul:v3", speaker: shubh')
    with pytest.raises(RenderError):
        build(load_project(root), preset="draft", log=lambda m: None)
    res = build(load_project(root), preset="draft", fallback="offline", log=lambda m: None)
    man = json.loads(res.manifest.read_text(encoding="utf-8"))
    assert man["voices"]["placeholder_lines"] == ["l2"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_output_outside_project_refused(tmp_path):
    from sastudio.build import build
    from sastudio.errors import ConfigError

    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("  output: build", "  output: ../outside")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    with pytest.raises(ConfigError):
        build(load_project(root), preset="draft", log=lambda m: None)
    assert not (tmp_path / "outside").exists()


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("SASTUDIO_LIVE_TESTS") != "1", reason="paid API tests are opt-in")
def test_live_placeholder():
    """Opt-in hook for real-provider tests (SASTUDIO_LIVE_TESTS=1). No live test is implemented yet."""
