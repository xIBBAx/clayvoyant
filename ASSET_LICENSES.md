# Licences

Everything in this repository is listed here with the terms it is shared under. If you add an
asset, add a row (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Code

All source code (`src/`, `tests/`, `tools/`, `examples/`, `.github/`) is under the
[MIT License](LICENSE), Copyright (c) 2026 Ibrahim Sultan.

The clay renderer's Blender engine is not included in this release, and nothing from it is in this
repository.

## Media made for this project

Made by Ibrahim Sultan for this project, and shared under the same MIT License as the code. The
"How it was made" column says which tool produced each file.

| What | Where | How it was made |
|---|---|---|
| Five clay character designs (Mira, Leo, Aarav, Nadia, Rook) | `src/sastudio/engine/characters/*.json` | Parameter files describing each character |
| Character portraits | `src/sastudio/templates/starter/assets/characters/*.png`, `docs/media/characters/*.png` (except the cast board), `examples/northgate/assets/characters/*.png` (copies) | Rendered from those parameter files with the author's Blender clay pipeline. This repository contains the resulting images and the parameter files, not the renderer. |
| Cast board | `docs/media/characters/cast-1600x900.png` | Composed from the portraits by `tools/make_readme_media.py` |
| Example organisation logo (a placeholder to replace) | `src/sastudio/templates/starter/assets/logo.png` | Drawn with Pillow |
| Project logo | `docs/media/brand/` | Drawn with code by `tools/make_brand.py` (SVG and PNG) |
| Fictional Northgate Logistics logo (example only) | `examples/northgate/assets/logo.png` | Drawn with code by `tools/make_example_assets.py` |
| Example project | `examples/northgate/` | Written for this project; its scenes are copies of starter scenes with one line changed |
| Sample scripts (12 scenes, English, partly Hindi) | `src/sastudio/templates/starter/scenes/` | Written for this project |
| Covers and thumbnail | `docs/media/film/cover-*.png`, `docs/media/film/thumbnail-1280x720.png` | Composed from the logo and portraits by `tools/make_readme_media.py` |
| Film stills and loop | `docs/media/film/stills/*.png`, `docs/media/film/loop.gif` | Frames of the reference films, extracted by `tools/make_reference_media.py` (see `docs/media/film/VERIFY.md`) |
| Terminal captures | `docs/media/screenshots/*.png` | Real command output, drawn by `tools/make_screenshots.py` |
| Reference films (release downloads, not in the repository) | GitHub release assets | Rendered with this project from the starter template, the trailer scenes and the example; the projects are recreated by `tools/make_reference_media.py` |

**Films you make are yours.** You don't need to credit this project or its author in a video
you render. The MIT notice applies to copies of the software, not to your films.

The sample scripts are general awareness material, not policy. Review them against your own
organisation's rules before you use them.

## Fonts (bundled)

Both are under the [SIL Open Font License 1.1](https://openfontlicense.org). The licence text
is next to each font. You may use them in your films and redistribute them with their licence,
but not sell the font files on their own.

| Font | Files | Copyright | Source |
|---|---|---|---|
| Atkinson Hyperlegible Next | `src/sastudio/data/fonts/AtkinsonHyperlegibleNext[wght].ttf` | 2020-2024 The Atkinson Hyperlegible Next Project Authors | `google/fonts` commit `5bb28733cec313b63fbd415b574b5ae35c8aa8b8`, unmodified, SHA-256 `5a455d1c…31745` |
| Mukta (Regular, Bold) | `src/sastudio/data/fonts/Mukta-*.ttf` | 2014 Girish Dalvi, Ek Type | same commit, unmodified, SHA-256 `2958e4af…9688` (Regular), `7d22891c…0a12` (Bold) |

## Tools you install yourself (not included)

| Tool | Used for | Licence |
|---|---|---|
| FFmpeg | encoding, audio | LGPL 2.1+ or GPL 2+, depending on the build |
| espeak-ng (optional) | free placeholder voice | GPL 3+ |
| Python packages: PyYAML, jsonschema, Pillow | reading projects, validation, drawing | MIT, MIT, MIT-CMU |

The terminal captures were drawn with the DejaVu Sans Mono font installed on the maintainer's
system; the font is not included here, only images of text set in it.

## Speech you generate

Audio from Sarvam or ElevenLabs is created with your own account and is governed by that
provider's terms, not by this repository. As documented by the providers (checked November
2026, check again before you publish):

- **Sarvam:** audio generated with credits (including free credits) carries Sarvam's
  Production License; see Sarvam's commercial-licensing page and EULA.
- **ElevenLabs:** paid plans include a commercial licence; the free plan does not, and requires
  crediting ElevenLabs. Voices from the ElevenLabs Voice Library can carry extra terms set by
  the voice's owner.

Never clone a real person's voice without their written consent.

## What is not here

This repository contains no music, sound effects, stock footage, third-party 3D models,
company logos or voice recordings. Add your own only if their licence allows it.
