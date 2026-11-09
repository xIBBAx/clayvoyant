import pytest

from sastudio.errors import TemplateError
from sastudio.project import load_project
from sastudio.text import template as tpl
from sastudio.text.speech import SpeechRules, normalize_literal, speak_email, speak_url
from sastudio.voices.common import spoken_text


def ctx(**chars):
    rules = SpeechRules()
    return tpl.TextContext(
        characters=chars,
        org=tpl.OrgText(fields={"name": "Acme", "security_email": "security@example.com",
                                "security_team": "the security team"},
                        spoken={"name": {"default": "Ack-me"}}, emails={"security_email"},
                        localized={"hi-IN": {"security_team": "सिक्योरिटी टीम"}}),
        speak_email=lambda a, lang: speak_email(a, lang, rules),
        speak_url=lambda u, lang: speak_url(u, lang, rules),
    )


def C(cid, name, **kw):
    return tpl.CharacterText(cid, name, **kw)


def test_rename_changes_every_reference_and_nothing_else():
    c = ctx(dev=C("dev", "Aarav"))
    r = tpl.resolve("{dev}, unplug the device, {dev}.", c, "en-IN")
    assert r.display == "Aarav, unplug the device, Aarav."  # 'device' untouched


def test_unicode_multiword_and_punctuated_names():
    for name in ["Anne-Marie O'Brien", "मीरा", "José Álvarez", "Dr. R. K. Iyer", "Zoë"]:
        r = tpl.resolve("Hi {x}!", ctx(x=C("x", name)), "en-IN")
        assert r.display == f"Hi {name}!"


def test_display_and_spoken_differ():
    c = ctx(x=C("x", "Aarav", spoken={"default": "Aa-ruv", "hi-IN": "आरव"}))
    assert tpl.resolve("{x}", c, "en-IN").spoken == "Aa-ruv"
    assert tpl.resolve("{x}", c, "hi-IN").spoken == "आरव"
    assert tpl.resolve("{x}", c, "hi-IN").display == "Aarav"


def test_language_specific_display_form():
    c = ctx(x=C("x", "Mira", forms={"hi-IN.name": "मीरा"}))
    assert tpl.resolve("{x}", c, "hi-IN").display == "मीरा"
    assert tpl.resolve("{x}", c, "en-IN").display == "Mira"


def test_pronouns_and_capitals():
    c = ctx(a=C("a", "Ana", pronouns="she"), b=C("b", "Bo", pronouns="they"))
    r = tpl.resolve("{a.They} said {a.their} code. {b.they} agreed with {b.them}.", c, "en-IN")
    assert r.display == "She said her code. they agreed with them."


def test_gender_select():
    t = "मैं {x.gender?feminine=गई|masculine=गया|other=गए}"
    assert tpl.resolve(t, ctx(x=C("x", "A", gender="feminine")), "hi-IN").display == "मैं गई"
    assert tpl.resolve(t, ctx(x=C("x", "A", gender="masculine")), "hi-IN").display == "मैं गया"
    assert tpl.resolve(t, ctx(x=C("x", "A", gender="other")), "hi-IN").display == "मैं गए"


def test_select_requires_other():
    with pytest.raises(TemplateError):
        tpl.resolve("{x.gender?feminine=a|masculine=b}", ctx(x=C("x", "A")), "en-IN")


@pytest.mark.parametrize("bad", ["{x", "x}", "{x{y}}", "{org}", "{ghost}", "{x.nope}", "{org.nope}", "{1x}"])
def test_bad_templates(bad):
    with pytest.raises(TemplateError):
        tpl.resolve(bad, ctx(x=C("x", "A")), "en-IN")


def test_escaped_braces():
    assert tpl.resolve("{{literal}} {x}", ctx(x=C("x", "A")), "en-IN").display == "{literal} A"


def test_org_fields_emails_and_localization():
    c = ctx()
    r = tpl.resolve("Write to {org.security_email}.", c, "en-IN")
    assert r.display == "Write to security@example.com."
    assert r.spoken == "Write to security at example dot com."
    assert tpl.resolve("{org.name}", c, "en-IN").spoken == "Ack-me"
    assert tpl.resolve("{org.security_team}", c, "hi-IN").display == "सिक्योरिटी टीम"
    assert tpl.resolve("{org.security_team}", c, "en-IN").display == "the security team"


def test_literal_name_lint_is_word_aware():
    names = {"dev": "Dev", "ana": "Ana"}
    assert tpl.find_literal_names("Check the device, banana.", names) == []
    assert tpl.find_literal_names("Dev, look. {ana} said so.", names) == [("dev", "Dev")]
    assert tpl.find_literal_names("मीरा आई", {"m": "मीरा"}) == [("m", "मीरा")]


def test_speech_normalisation():
    rules = SpeechRules()
    out = normalize_literal("Turn on MFA. Ask IT, it helps. Mail a.b@x-y.com or visit https://ex.com/a/b", "en-IN", rules)
    assert "M F A" in out and "I T" in out and "it helps" in out
    assert "a dot b at x dash y dot com" in out
    assert "ex dot com slash a slash b" in out


def test_names_never_touched_by_lexicon():
    rules = SpeechRules(lexicon={"IT": {"default": "I T"}})
    c = ctx(x=C("x", "IT"))
    r = tpl.resolve("{x} called IT.", c, "en-IN")
    assert spoken_text(r, "offline", rules) == "IT called I T."


def test_provider_pronunciation_hints():
    c = ctx(x=C("x", "Aarav", pronunciation={"sarvam": {"text": "आरव"}, "elevenlabs": {"alias": "Aa-ruv"}}))
    r = tpl.resolve("Hi {x}", c, "en-IN")
    assert spoken_text(r, "sarvam", SpeechRules()) == "Hi आरव"
    assert spoken_text(r, "elevenlabs", SpeechRules()) == "Hi Aa-ruv"
    assert spoken_text(r, "offline", SpeechRules()) == "Hi Aarav"


def test_rename_in_project_file_flows_everywhere(project_dir):
    t = (project_dir / "studio.yaml").read_text(encoding="utf-8").replace("    name: Dev\n", "    name: Aarav\n")
    (project_dir / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(project_dir)
    assert p.display("Hello {dev}, check the device.", "en-IN") == "Hello Aarav, check the device."
