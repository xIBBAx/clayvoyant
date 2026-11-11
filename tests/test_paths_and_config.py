import os
import sys

import pytest

from sastudio.errors import ConfigError, UnsafePathError
from sastudio.project import load_project, validate
from sastudio.safepath import ensure_output_dir, resolve_inside, safe_name

from .conftest import write_project


# ------------------------------------------------------------------ paths
@pytest.mark.parametrize("raw", ["/etc/passwd", "C:\\Windows\\win.ini", "C:/x.png", "\\\\server\\share\\x",
                                 "//server/share", "~/x.png", "../x.png", "assets/../../x.png", "a\\..\\..\\x"])
def test_unsafe_paths_rejected(tmp_path, raw):
    with pytest.raises(UnsafePathError):
        resolve_inside(tmp_path, raw)


def test_relative_paths_with_spaces_and_backslashes(tmp_path):
    (tmp_path / "my assets").mkdir()
    (tmp_path / "my assets" / "logo file.png").write_bytes(b"x")
    p1 = resolve_inside(tmp_path, "my assets/logo file.png", must_exist=True)
    p2 = resolve_inside(tmp_path, "my assets\\logo file.png", must_exist=True)
    assert p1 == p2


def test_nul_and_empty_rejected(tmp_path):
    for raw in ["", "   ", "a\x00b"]:
        with pytest.raises(UnsafePathError):
            resolve_inside(tmp_path, raw)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin rights on Windows")
def test_symlink_escape_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"x")
    proj = tmp_path / "proj"
    proj.mkdir()
    os.symlink(outside, proj / "link")
    with pytest.raises(UnsafePathError):
        resolve_inside(proj, "link/secret.png")


def test_output_dir_protected(tmp_path):
    (tmp_path / "keep").mkdir()
    with pytest.raises(UnsafePathError):
        ensure_output_dir(tmp_path, "keep/out", protected=[tmp_path / "keep"])


def test_safe_name():
    assert safe_name("CON") == "_CON"
    assert safe_name("../../etc/passwd").strip("_") == "etc_passwd"
    assert safe_name("Security Awareness — Film") == "Security_Awareness_Film"
    assert safe_name("जल्दी report") == "जल्दी_report"
    assert safe_name("") == "untitled"
    assert len(safe_name("x" * 500)) <= 120


# ------------------------------------------------------------------ project loading
def test_minimal_project_loads(project_dir):
    p = load_project(project_dir)
    assert [s.id for s in p.scenes] == ["one", "two"]
    assert not [i for i in p.issues if i.level == "error"]


def test_missing_project(tmp_path):
    with pytest.raises(ConfigError):
        load_project(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ConfigError):
        load_project(tmp_path / "empty")


def test_yaml_aliases_rejected(tmp_path):
    root = write_project(tmp_path / "p", extra="\nx_anchor: &a [1, 2]\n")
    with pytest.raises(ConfigError):
        load_project(root)


def test_unknown_setting_rejected(tmp_path):
    root = write_project(tmp_path / "p", extra="\nsurprise: true\n")
    with pytest.raises(ConfigError) as e:
        load_project(root)
    assert "Unknown setting" in e.value.message


def test_oversized_file_rejected(tmp_path):
    root = write_project(tmp_path / "p")
    with open(root / "studio.yaml", "a") as fh:
        fh.write("# " + "x" * 1_100_000 + "\n")
    with pytest.raises(ConfigError):
        load_project(root)


def test_wrong_schema_version(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("schema_version: 1", "schema_version: 99")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_project(root)
    assert "understands up to" in e.value.message


def test_scene_file_traversal_rejected(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8")
    t = t.replace("scenes:\n", "scenes:\n  - file: ../evil.yaml\n", 1)
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    (tmp_path / "evil.yaml").write_text("id: evil\ntitle: x\nlines: [{id: e1, card: {text: x}}]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_project(root)


def test_absolute_logo_is_an_error(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace('  name: "Test Org"', '  name: "Test Org"\n  logo: /etc/hosts')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    assert any("absolute" in i.message for i in p.issues if i.level == "error")


def test_logo_wrong_extension(tmp_path):
    root = write_project(tmp_path / "p")
    (root / "logo.svg").write_text("<svg/>", encoding="utf-8")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace('  name: "Test Org"', '  name: "Test Org"\n  logo: logo.svg')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    assert any(".png" in i.message for i in p.issues if i.level == "error")


def test_disabled_dependency_is_an_error(project_dir):
    p = load_project(project_dir)
    p.scenes[0].enabled = False
    issues = validate(p)
    assert any("turned off" in i.message for i in issues if i.level == "error")
    assert not any(i.level == "error" for i in validate(p, only=["one"]))


def test_dependency_order(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("    requires: [one]\n", "")
    t = t.replace('  - id: one\n    title: "Scene One"\n', '  - id: one\n    title: "Scene One"\n    requires: [two]\n')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    assert any("comes after" in i.message for i in p.issues)


def test_unknown_speaker_and_token(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("who: dev, say", "who: zed, say").replace("Thanks, {dev}", "Thanks, {nobody}")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    msgs = " ".join(i.message for i in p.issues if i.level == "error")
    assert "Speaker 'zed'" in msgs and "nobody" in msgs


def test_missing_translation_error_then_fallback(tmp_path):
    root = write_project(tmp_path / "p", languages="[en-IN, hi-IN]")
    p = load_project(root)
    assert any("No hi-IN text" in i.message and i.level == "error" for i in p.issues)
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("  languages: [en-IN, hi-IN]", "  languages: [en-IN, hi-IN]\n  missing_translation: fallback")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    assert not [i for i in p.issues if i.level == "error"]
    assert any("is used" in i.message for i in p.issues if i.level == "warning")


def test_duplicate_ids_and_names(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("id: l4,", "id: l1,").replace("    name: Dev\n", "    name: Ana\n")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    assert any("used twice" in i.message for i in p.issues if i.level == "error")
    assert any("share the display name" in i.message for i in p.issues if i.level == "warning")


def test_extremely_long_values_rejected(tmp_path):
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace('name: "Test Org"', 'name: "' + "O" * 500 + '"')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_project(root)


def test_unsupported_language_code_rejected(tmp_path):
    root = write_project(tmp_path / "p", languages="[english]")
    with pytest.raises(ConfigError):
        load_project(root)


def test_two_projects_do_not_share_state(tmp_path):
    a = load_project(write_project(tmp_path / "a"))
    root_b = write_project(tmp_path / "b")
    t = (root_b / "studio.yaml").read_text(encoding="utf-8").replace('name: "Test Org"', 'name: "Other Org"')
    (root_b / "studio.yaml").write_text(t, encoding="utf-8")
    b = load_project(root_b)
    assert a.org["name"] == "Test Org" and b.org["name"] == "Other Org"
    assert a.root != b.root


# --------------------------------------------------------------------------- placeholder reporting contacts
@pytest.mark.parametrize("host,placeholder", [
    ("example.com", True), ("EXAMPLE.org.", True), ("mail.example.net", True), ("quillmere.example", True),
    ("x.test", True), ("a.invalid", True), ("localhost", True),
    ("notexample.com", False), ("example.com.au", False), ("examples.com", False), ("test.com", False),
    ("company.in", False),
])
def test_placeholder_hosts(host, placeholder):
    from sastudio.project import is_placeholder_host

    assert is_placeholder_host(host) is placeholder


def _use_real_contacts(root):
    p = root / "studio.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("security@example.com", "security@acme-corp.co.in")
                 .replace("https://example.com/report", "https://report.acme-corp.co.in/"), encoding="utf-8")


def test_placeholder_contacts_found_in_org_and_translations(tmp_path):
    from sastudio.project import placeholder_contacts

    root = write_project(tmp_path / "p")
    assert placeholder_contacts(load_project(root)) == [
        "organization.security_email = security@example.com",
        "organization.reporting_url = https://example.com/report",
    ]
    _use_real_contacts(root)
    assert placeholder_contacts(load_project(root)) == []
    p = root / "studio.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "  security_email: \"security@acme-corp.co.in\"",
        "  security_email: \"security@acme-corp.co.in\"\n  translations:\n    hi-IN:\n      security_email: \"hindi@example.org\""),
        encoding="utf-8")
    assert placeholder_contacts(load_project(root)) == ["organization.translations.hi-IN.security_email = hindi@example.org"]


def test_final_render_refuses_placeholder_contacts(tmp_path):
    from sastudio.build import build

    root = write_project(tmp_path / "p")
    with pytest.raises(ConfigError) as e:
        build(load_project(root), preset="final", log=lambda m: None)
    assert "placeholder" in e.value.message and "security@example.com" in e.value.message
    assert "--allow-placeholder-contacts" in e.value.hint
    assert not (root / "build").exists()  # refused before anything was rendered


def test_validate_notes_placeholder_contacts_without_failing_strict(tmp_path, capsys):
    from sastudio.cli import main

    root = write_project(tmp_path / "p")
    assert main(["validate", str(root), "--strict"]) == 0
    out = capsys.readouterr().out
    assert "[note] organization.security_email = security@example.com" in out and "0 warning(s)" in out
    _use_real_contacts(root)
    assert main(["validate", str(root), "--strict"]) == 0
    assert "[note]" not in capsys.readouterr().out


def test_a_mistake_inside_a_scene_is_named_exactly(tmp_path):
    """Scenes may be written inline or as a file reference, so the schema has two shapes; its first complaint was
    "is not valid under any of the given schemas". The message now names the setting and what is wrong with it."""
    from sastudio.errors import ConfigError
    from sastudio.project import load_project

    from .conftest import write_project

    root = write_project(tmp_path / "p")
    p = root / "studio.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("  - id: one\n", "  - id: one\n    direction:\n      reactions: maybe\n", 1),
                 encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_project(root)
    assert "scenes[0].direction.reactions: 'maybe' is not of type 'boolean'" in e.value.message
    assert "any of the given schemas" not in e.value.message
