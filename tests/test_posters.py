"""Posters: one printed page per scene and language, and a PDF of them all."""

import re

import pytest
from PIL import Image

from sastudio import posters
from sastudio.cli import main
from sastudio.project import load_project


@pytest.fixture(scope="module")
def india(tmp_path_factory):
    root = tmp_path_factory.mktemp("p") / "film"
    assert main(["init", str(root), "--template", "india"]) == 0
    return root


def test_every_scene_with_a_lesson_gets_a_page_in_every_language(india, capsys):
    assert main(["posters", str(india)]) == 0
    assert "[en-IN] 5 poster(s)" in capsys.readouterr().out
    for lang in ("en-IN", "hi-IN"):
        folder = india / "build" / lang / "posters"
        pngs = sorted(folder.glob("*.png"))
        assert [p.name for p in pngs][0] == f"01_the_call.{lang}.png" and len(pngs) == 5
        with Image.open(pngs[0]) as im:
            assert im.size == posters.SIZES["a4"]
            assert round(im.info["dpi"][0]) == 300
        pdf = (folder / f"posters.{lang}.pdf").read_bytes()
        assert pdf.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page\b", pdf)) == 5


def test_letter_size_and_a_folder_of_your_own(india, tmp_path):
    assert main(["posters", str(india), "--lang", "hi-IN", "--size", "letter", "--out", str(tmp_path)]) == 0
    with Image.open(tmp_path / "hi-IN" / "01_the_call.hi-IN.png") as im:
        assert im.size == posters.SIZES["letter"]


def test_a_scene_with_nothing_to_say_on_a_wall_gets_no_page(india):
    project = load_project(india)
    scene = project.scenes[0]
    scene.headline, scene.takeaway = "", ""
    assert posters.page(project, scene, "en-IN") is None


def test_a_language_the_project_does_not_have_is_refused(india):
    from sastudio.errors import ConfigError

    with pytest.raises(ConfigError, match="no ta-IN text"):
        posters.make(load_project(india), "ta-IN")
