"""`sastudio init` with the organisation's details, so a first film needs no YAML editing."""

import pytest
from PIL import Image

from sastudio.cli import main
from sastudio.project import load_project, placeholder_contacts


def test_init_sets_organisation_style_and_logo(tmp_path, capsys):
    logo = tmp_path / "logo.jpg"
    Image.new("RGB", (300, 120), "#2255AA").save(logo)
    dest = tmp_path / "film"
    assert main(["init", str(dest), "--org", 'Sunrise "Seva" Trust, Pune', "--email", "security@sunrise.org.in",
                 "--report-url", "https://sunrise.org.in/report", "--style", "cutout", "--logo", str(logo)]) == 0
    p = load_project(dest)
    assert p.org["name"] == 'Sunrise "Seva" Trust, Pune'
    assert p.org["short_name"] == "Sunrise"
    assert p.org["security_email"] == "security@sunrise.org.in"
    assert p.render_cfg["character_style"] == "v3"
    assert placeholder_contacts(p) == []  # a final render is allowed straight away
    with Image.open(dest / "assets" / "logo.png") as im:
        assert im.format == "PNG" and im.size == (300, 120)
    text = (dest / "studio.yaml").read_text(encoding="utf-8")
    assert "# where people report incidents" in text  # the template's comments stay
    assert main(["validate", str(dest), "--strict"]) == 0
    assert "Still a placeholder" not in capsys.readouterr().out


def test_init_keeps_non_latin_names(tmp_path):
    dest = tmp_path / "film"
    assert main(["init", str(dest), "--org", "सूर्योदय सेवा ट्रस्ट", "--short-name", "सूर्योदय",
                 "--email", "suraksha@sunrise.org.in"]) == 0
    p = load_project(dest)
    assert p.org["name"] == "सूर्योदय सेवा ट्रस्ट" and p.org["short_name"] == "सूर्योदय"


def test_plain_init_points_out_placeholders(tmp_path, capsys):
    assert main(["init", str(tmp_path / "film")]) == 0
    out = capsys.readouterr().out
    assert "Still a placeholder: organization.security_email = security@example.com" in out


@pytest.mark.parametrize("args", [
    ["--email", "not-an-email"],
    ["--report-url", "http://insecure.example/report"],
    ["--style", "v9"],
    ["--org", "line one\nline two"],
    ["--org", "{braces}"],
    ["--logo", "missing.png"],
])
def test_init_rejects_bad_options_before_creating_anything(tmp_path, args):
    dest = tmp_path / "film"
    assert main(["init", str(dest), *args]) != 0
    assert not dest.exists()


def test_init_rejects_a_file_that_is_not_an_image(tmp_path):
    bad = tmp_path / "logo.png"
    bad.write_bytes(b"not an image")
    assert main(["init", str(tmp_path / "film"), "--logo", str(bad)]) != 0
    assert not (tmp_path / "film").exists()


@pytest.mark.parametrize("template", ["starter", "short", "education"])
def test_every_template_accepts_the_options(tmp_path, template):
    dest = tmp_path / template
    assert main(["init", str(dest), "--template", template, "--org", "Acme Ltd", "--email", "sec@acme.co.in",
                 "--style", "v1"]) == 0
    p = load_project(dest)
    assert p.org["name"] == "Acme Ltd" and p.render_cfg["character_style"] == "v1"
