"""The `india` template, its two languages, and text in the scripts of India."""

import pytest

from sastudio import direction as D
from sastudio.cli import main
from sastudio.project import load_project
from sastudio.render import style

SCRIPTS = {"নমস্কার": 0x0980, "ਨਮਸਕਾਰ": 0x0A00, "નમસ્કાર": 0x0A80, "ନମସ୍କାର": 0x0B00, "வணக்கம்": 0x0B80,
           "నమస్కారం": 0x0C00, "ನಮಸ್ಕಾರ": 0x0C80, "നമസ്കാരം": 0x0D00}


@pytest.fixture(scope="module")
def india(tmp_path_factory):
    root = tmp_path_factory.mktemp("i") / "film"
    assert main(["init", str(root), "--template", "india", "--org", "Sunrise Senior Citizens Forum",
                 "--email", "help@sunrise-forum.org"]) == 0
    return root


def test_the_template_brings_its_own_scenes_and_nothing_else(india):
    assert sorted(p.name for p in (india / "scenes").iterdir()) == [
        "01_the_call.yaml", "02_pin_is_for_paying.yaml", "03_six_numbers.yaml", "04_the_light_bill.yaml",
        "05_the_first_number.yaml"]
    assert not (india / "assets").exists()          # no starter artwork: every character is described, not drawn


def test_it_validates_in_both_languages_and_plans_cleanly(india, capsys):
    assert main(["validate", str(india), "--strict"]) == 0
    assert "0 error(s), 0 warning(s) in 5 scene(s), 6 character(s), languages en-IN, hi-IN" in capsys.readouterr().out
    project = load_project(india)
    assert [p for p in D.validate(project) if p.level == "error"] == []
    assert len(D.plan(project)) == 5


def test_every_scene_names_its_source(india):
    for f in sorted((india / "scenes").glob("*.yaml")):
        note = f.read_text("utf-8").split("policy_note:", 1)[1].split("direction:", 1)[0]
        assert "Source:" in note and ("I4C" in note or "RBI" in note or "Telecommunications" in note), f.name


def test_the_organisation_given_reaches_the_hindi_film_too(india):
    project = load_project(india)
    assert project.display("{org.name}", "hi-IN") == "Sunrise Senior Citizens Forum"


def test_a_logo_can_be_added_to_a_template_that_has_none(tmp_path):
    from PIL import Image

    logo = tmp_path / "logo.png"
    Image.new("RGB", (64, 64), "#2F7F7A").save(logo)
    root = tmp_path / "film"
    assert main(["init", str(root), "--template", "india", "--logo", str(logo)]) == 0
    assert (root / "assets" / "logo.png").is_file()
    assert "  logo: assets/logo.png\n" in (root / "studio.yaml").read_text("utf-8")


@pytest.mark.parametrize("word,block", SCRIPTS.items())
def test_each_indian_script_is_set_in_a_font_that_has_it(word, block):
    assert style.script(word) == block
    f = style.font_for(word + " cybercrime.gov.in", 40, "semibold")
    assert f.path.endswith(style.INDIC[block])
    # a letter the font lacks is drawn as the same empty box as any other missing letter; these are not
    missing = f.getmask("\U000F0000").getbbox()
    assert all(f.getmask(ch).getbbox() != missing for ch in word if not ch.isspace())


def test_latin_and_hindi_keep_their_fonts():
    assert style.font_for("Hello", 30).path.endswith(style.LATIN)
    assert "Mukta" in style.font_for("नमस्ते", 30).path


def test_the_closing_card_names_the_real_portal_not_a_placeholder_address(india):
    from sastudio.build import bookends

    project = load_project(india)
    _, outro = bookends(project, "hi-IN")
    assert outro.beats[0].extra["contact"] == "help@sunrise-forum.org"     # a real address given with --email stays
    project.org["security_email"] = "help@example.com"
    _, outro = bookends(project, "en-IN")
    assert (outro.beats[0].extra["contact"], outro.beats[0].extra["url"]) == ("cybercrime.gov.in", "")
