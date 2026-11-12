"""Hindi in Roman letters (hi-Latn): the spelling itself, and a film that shows it while the voices stay Hindi."""

import json
from importlib import resources

import pytest

from sastudio.cli import main
from sastudio.project import errors, load_project, validate
from sastudio.text import romanize as R
from sastudio.voices.engine import build_plan


@pytest.mark.parametrize("word, roman", [
    ("करना", "karna"), ("समझना", "samajhna"), ("जानवर", "jaanvar"), ("लगभग", "lagbhag"),      # the unspoken vowel
    ("सत्य", "satya"), ("मित्र", "mitra"), ("दोस्त", "dost"), ("शब्द", "shabd"),                # after a cluster
    ("रखिए", "rakhiye"), ("गए", "gaye"), ("गई", "gayi"), ("बताओ", "batao"), ("जाएगा", "jayega"),  # vowels that meet
    ("में", "mein"), ("हैं", "hain"), ("नहीं", "nahin"), ("हूँ", "hoon"), ("यहाँ", "yahan"),        # nasal endings
    ("अंदर", "andar"), ("संभव", "sambhav"),                                                    # n before most, m before lips
    ("ज़रूर", "zaroor"), ("फ़र्क़", "farq"), ("बड़ा", "bada"), ("पढ़ना", "padhna"),                 # dotted letters
    ("अच्छा", "achha"), ("बच्चा", "bachcha"), ("गिरफ़्तार", "giraftaar"), ("आप", "aap"), ("का", "ka"),
])
def test_everyday_spelling(word, roman):
    assert R._spell(word) == roman


def test_dotted_letters_are_the_same_typed_either_way():
    assert R._spell("ज़रूर") == R._spell("ज़रूर") == "zaroor"       # ज + dot, and the single character


def test_borrowed_words_come_back_as_english_and_the_rest_is_left_alone():
    assert R.hindi("वीडियो कॉल पर कोई गिरफ़्तारी नहीं।") == "Video call par koi giraftaari nahin."
    assert R.hindi("{gopal}, 1930 पर कॉल करें। फिर cybercrime.gov.in खोलें!") == \
        "{gopal}, 1930 par call karein. Phir cybercrime.gov.in kholein!"
    assert R.hindi("१२ बजे") == "12 baje"
    assert R.hindi("Already in English.") == "Already in English."
    assert R.romanize("नमस्ते", "hi-IN") == "नमस्ते" and R.romanize("नमस्ते", "hi-Latn") == "Namaste"


def test_the_spelling_list_is_devanagari_to_plain_roman():
    data = json.loads(resources.files("sastudio").joinpath("data", "romanize_hi.json").read_text("utf-8"))
    for group in data["words"].values():
        for word, roman in group.items():
            assert all("ऀ" <= ch <= "ॿ" or ch == "-" for ch in word), word
            assert roman.isascii() and roman.strip() == roman, roman


@pytest.fixture()
def film(tmp_path):
    root = tmp_path / "film"
    assert main(["init", str(root), "--template", "india"]) == 0
    return root


def test_a_roman_film_shows_roman_and_speaks_hindi(film):
    p = load_project(film)
    assert "hi-Latn" in p.languages and errors(validate(p)) == []
    line = p.scenes[0].lines[2]
    shown = p.display(line.template_for("hi-Latn", p.language, p.fallback), "hi-Latn")
    assert shown.isascii() and shown.startswith("Papa?")
    # the voice reads the Devanagari line, and it is the very recording the hi-IN film uses
    roman, hindi = build_plan(p, ["hi-Latn"]), build_plan(p, ["hi-IN"])
    assert [it.key for it in roman.items] == [it.key for it in hindi.items]
    assert not roman.items[0].req.text.isascii()
    assert len(build_plan(p, ["hi-IN", "hi-Latn"]).items) == len(hindi.items)      # generated once, not twice
    # names, titles and labels follow
    assert p.title_for("hi-Latn").isascii()
    assert p.display(p.scenes[0].field_for("takeaway", "hi-Latn", p.language), "hi-Latn").isascii()


def test_a_line_can_carry_its_own_roman_text(film):
    scene = film / "scenes" / "01_the_call.yaml"
    text = scene.read_text("utf-8")
    assert "पापा? किसको" in text
    scene.write_text(text.replace('translations: { hi-IN: "पापा? किसको', 'translations: { hi-Latn: "Papa! Ruko.", hi-IN: "पापा? किसको', 1), "utf-8")
    p = load_project(film)
    line = next(ln for ln in p.scenes[0].lines if "hi-Latn" in ln.translations)
    assert p.display(line.template_for("hi-Latn", p.language, p.fallback), "hi-Latn") == "Papa! Ruko."


def test_roman_letters_are_only_claimed_for_languages_that_have_them(film):
    yml = film / "studio.yaml"
    text = yml.read_text("utf-8")
    yml.write_text(text.replace("hi-Latn]", "hi-Latn, ta-Latn]", 1), "utf-8")
    assert any("ta-Latn" in i.message for i in errors(validate(load_project(film))))
    yml.write_text(text.replace("language: en-IN", "language: hi-Latn", 1), "utf-8")
    assert any("cannot be the language the lines are written in" in i.message for i in errors(validate(load_project(film))))
