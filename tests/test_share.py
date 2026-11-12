"""Phone films: a finished film laid out upright for a phone, with large captions, under a size limit."""

import subprocess

import pytest

from sastudio import share
from sastudio.audio.ffmpeg import ffmpeg_exe, ffprobe_exe
from sastudio.cli import main
from sastudio.project import load_project

SRT = """1
00:00:00,500 --> 00:00:01,800
नमस्ते, 1930 पर कॉल करें

2
00:00:02,100 --> 00:00:03,600
Report it on
cybercrime.gov.in
"""


def test_an_srt_is_read_cue_by_cue():
    cues = share.read_srt(SRT)
    assert cues == [(0.5, 1.8, "नमस्ते, 1930 पर कॉल करें"), (2.1, 3.6, "Report it on cybercrime.gov.in")]
    assert share.read_srt("") == []


def test_every_layer_keeps_the_film_visible_and_the_words_inside_the_frame(tmp_path):
    assert main(["init", str(tmp_path / "film"), "--template", "india"]) == 0
    project = load_project(tmp_path / "film")
    bare, said = share._layer(project, "hi-IN", None), share._layer(project, "hi-IN", "वीडियो कॉल पर कोई गिरफ़्तारी नहीं")
    assert bare.size == said.size == (share.W, share.H)
    film_band = (0, share.FILM_Y, share.W, share.FILM_Y + share.W * 9 // 16)
    assert bare.crop(film_band).getextrema()[3] == (0, 0) == said.crop(film_band).getextrema()[3]   # see-through
    assert said.crop((0, share.CAPTION_Y, share.W, share.H - 130)).getbbox() is not None


@pytest.mark.ffmpeg
def test_a_film_becomes_an_upright_phone_film_under_its_size_limit(tmp_path):
    assert main(["init", str(tmp_path / "film"), "--template", "india"]) == 0
    project = load_project(tmp_path / "film")
    film, srt, out = tmp_path / "in.mp4", tmp_path / "in.srt", tmp_path / "out.phone.mp4"
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(film)], check=True)
    srt.write_text(SRT, "utf-8")
    share.compose(project, "hi-IN", film, srt, out, max_mb=2)
    probe = subprocess.run([ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                            "-of", "compact", str(out)], capture_output=True, text=True, check=True).stdout
    assert "width=720|height=1280" in probe and "codec_type=audio" in probe
    assert abs(float(probe.split("duration=")[1]) - 4.0) < 0.15
    assert out.stat().st_size <= 2_000_000


def test_each_scene_can_be_its_own_clip(tmp_path, monkeypatch):
    from sastudio import share as share_mod

    assert main(["init", str(tmp_path / "film"), "--template", "india"]) == 0
    calls = []
    monkeypatch.setattr(share_mod, "share", lambda p, lang, mb, jobs, scene_ids=None: calls.append((lang, scene_ids)))
    assert main(["share", str(tmp_path / "film"), "--lang", "hi-IN", "--each"]) == 0
    assert calls == [("hi-IN", [s]) for s in ("the_call", "pin_is_for_paying", "six_numbers", "the_light_bill",
                                              "the_first_number")]
    calls.clear()
    assert main(["share", str(tmp_path / "film"), "--scenes", "six_numbers"]) == 0
    assert calls == [("en-IN", ["six_numbers"]), ("hi-IN", ["six_numbers"])]
