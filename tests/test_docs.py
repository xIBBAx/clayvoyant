"""Every relative link and image in the documentation points at something that exists."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = sorted([*REPO.glob("*.md"), *(REPO / "docs").rglob("*.md"), *(REPO / "examples").rglob("*.md"),
               *(REPO / ".github").rglob("*.md")])
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)|<img[^>]*\bsrc=\"([^\"]+)\"")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    s = re.sub(r"`", "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def _anchors(md: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", md.read_text("utf-8"), flags=re.S)
    return {_slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)}


def _links(md: Path):
    text = re.sub(r"```.*?```", "", md.read_text("utf-8"), flags=re.S)
    for m in LINK.finditer(text):
        target = m.group(1) or m.group(2)
        if re.match(r"^(https?:|mailto:)", target):
            continue
        yield target


@pytest.mark.skipif(not (REPO / "docs").is_dir(), reason="docs are not part of this install")
@pytest.mark.parametrize("md", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(md):
    broken = []
    for target in _links(md):
        path, _, anchor = target.partition("#")
        dest = (md.parent / path).resolve() if path else md
        if not dest.exists():
            broken.append(target)
        elif anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
            broken.append(target)
    assert not broken, f"{md.relative_to(REPO)} has broken links: {broken}"


@pytest.mark.skipif(not (REPO / "docs").is_dir(), reason="docs are not part of this install")
def test_every_readme_image_has_alt_text():
    text = (REPO / "README.md").read_text("utf-8")
    for tag in re.findall(r"<img[^>]*>", text):
        alt = re.search(r'\balt="([^"]*)"', tag)
        assert alt and len(alt.group(1)) > 15, f"image without a useful alt text: {tag[:80]}"
    for alt, _src in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text):
        assert alt.strip(), "markdown image without alt text"


@pytest.mark.skipif(not (REPO / "docs").is_dir(), reason="docs are not part of this install")
def test_docs_mention_only_commands_that_exist():
    from sastudio.cli import parser

    sub = next(a for a in parser()._actions if a.dest == "cmd")
    commands = set(sub.choices)
    for md in DOCS:
        text = md.read_text("utf-8")
        code = "\n".join(re.findall(r"```[a-z]*\n(.*?)```", text, re.S))
        found = re.findall(r"`sastudio ([a-z]+)", text) + re.findall(r"^\s*(?:\$ )?sastudio ([a-z]+)", code, re.M)
        for cmd in found:
            assert cmd in commands, f"{md.relative_to(REPO)} mentions `sastudio {cmd}`, which does not exist"
