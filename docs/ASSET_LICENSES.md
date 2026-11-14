# Licences

Everything in this repository is listed here with the terms it is shared under. If you add an
asset, add a row (see [CONTRIBUTING.md](../.github/CONTRIBUTING.md)).

## Code

All source code (`src/`, `tests/`, `tools/`, `examples/`, `.github/`) is under the
[MIT License](../LICENSE), Copyright (c) 2026 Ibrahim Sultan.

The clay engine (`src/sastudio/engine/`: the sculptor, the puppet and its rigs, acting, sets and the
film runner) is part of that source and under the same licence. Its core (the sculptor, the clay
material, the puppet, the hand and face rigs) is the author's own earlier production code from a
private film he made, published here by him and adapted for general use; several of those modules
are carried over largely unchanged. Acting, sets, props, the film runner and the Python side were
written for this repository. Every set, prop and character it
makes is built by code: no third-party models, textures, photographs or sounds are bundled or loaded.
`docs/media/brand/mark-clay-*.png` is sculpted and rendered by `tools/make_clay_mark.py`.

## Media made for this project

Made by Ibrahim Sultan for this project, and shared under the same MIT License as the code. The
"How it was made" column says which tool produced each file.

| What | Where | How it was made |
|---|---|---|
| Five clay character designs (Mira, Leo, Aarav, Nadia, Rook) | `src/sastudio/engine/characters/*.json` | Parameter files describing each character |
| Character portraits | `src/sastudio/templates/starter/assets/characters/*.png`, `docs/media/characters/*.png` (except the cast board), `examples/quillmere/assets/characters/*.png` (copies) | Rendered from those parameter files by the clay engine in `src/sastudio/engine` (`sastudio clay portraits`). |
| Cast board | `docs/media/characters/cast-1600x900.png` | Composed from the portraits by `tools/make_readme_media.py` |
| Drawn character styles (v1 sketch, v2 flat, v3 cut-out) | `src/sastudio/render/figures.py` | Code written for this project that draws every figure from a short text description at render time; no image files, no third-party art, nothing downloaded |
| Styles gallery | `docs/media/characters/styles.png` | The starter cast drawn by `sastudio characters --sheet`, via `tools/make_readme_media.py` |
| Example organisation logo (a placeholder to replace) | `src/sastudio/templates/starter/assets/logo.png` | Drawn with Pillow |
| Project mark in clay | `docs/media/brand/mark-clay-*.png` | Sculpted and rendered by `tools/make_clay_mark.py` with the clay engine |
| Project logo (flat) | `docs/media/brand/*.svg`, `logo-for-*.png`, `mark-512.png` | Drawn with code (`tools/make_brand.py`; the SVG marks follow the clay mark) |
| Clay engine: sculptor, puppet, rigs, acting, sets, props, light | `src/sastudio/engine/` | The author's own code: the sculpting and rigging core comes from his earlier production work, the rest was written for this repository (see [Code](#code)); every form is generated, nothing is loaded from a model, texture or photograph |
| Sample film "The Fast One" (project, characters, script) | `examples/the-fast-one/` | Written for this project; all people and places are invented |
| The sample film itself, with its subtitles | `docs/media/the-fast-one.mp4`, `docs/media/the-fast-one.en-GB.vtt` (also attached to releases) | Made by `sastudio film examples/the-fast-one --preset preview` from this repository; the voices are Kokoro's |
| The film's poster, the before-and-after pairs and the watch page | `docs/media/film/the-fast-one-poster.jpg`, `docs/media/proof/*.jpg`, `docs/index.html` | Frames rendered by this repository's code (earlier builds for the "before" halves); the page is written for this project |
| Frames and loop of the sample film; the eight sets; the character line-up | `docs/media/film/the-fast-one*.{jpg,gif}`, `docs/media/film/sets.jpg`, `docs/media/characters/clay-lineup.jpg`, `docs/media/characters/clay-proof.jpg` | Rendered by `sastudio film` and the engine from this repository (`tools/make_showcase_media.py`); the voices in the film are Kokoro's |
| Nineteen Thirty, the film and the sheet | `docs/media/nineteen-thirty.en-IN.mp4`, its `.vtt` subtitles, `docs/media/film/nineteen-thirty-sheet.jpg` (the films are also attached to releases) | Made by `sastudio film examples/nineteen-thirty --preset preview --lang en-IN` from this repository; the voices are Kokoro's |
| The India previews | `docs/media/india/*.jpg` | Frames and posters of the `india` template as `sastudio init --template india` makes it, rendered by `sastudio render`, `sastudio share` and `sastudio posters` from this repository; the voices are Kokoro's |
| Sound effects: footsteps, seats, chairs, doors, a laptop's lid, typing, a phone ringing or buzzing, a message, a knock | `src/sastudio/sound/foley.py` | Made by this code while a film is mixed (modal synthesis: a contact force through the resonances of what is struck, and friction for scrapes); no recordings |
| Rooms and their air: reverberation and room tone for every set | `src/sastudio/sound/ambience.py` | Made by this code: each room's reverberation from its real size (Sabine), each place's air from shaped noise the length of the scene; no recordings |
| Sample film "Held Door" (project, characters, script) | `examples/held-door/` | Written for this project; all people and places are invented |
| Its theme music, a placeholder | `examples/held-door/assets/music/theme.ogg` | Made by `tools/make_example_music.py` (numpy and FFmpeg) |
| Fictional Quillmere Logistics logo (example only) | `examples/quillmere/assets/logo.png` | Drawn with code by `tools/make_example_assets.py` |
| Example project | `examples/quillmere/` | Written for this project; its scenes are copies of starter scenes with one line changed |
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

All are under the [SIL Open Font License 1.1](https://openfontlicense.org). The licence text
is next to each font. You may use them in your films and redistribute them with their licence,
but not sell the font files on their own.

| Font | Files | Copyright | Source |
|---|---|---|---|
| Atkinson Hyperlegible Next | `src/sastudio/data/fonts/AtkinsonHyperlegibleNext[wght].ttf` | 2020-2024 The Atkinson Hyperlegible Next Project Authors | `google/fonts` commit `5bb28733cec313b63fbd415b574b5ae35c8aa8b8`, unmodified, SHA-256 `5a455d1c…31745` |
| Mukta (Regular, Bold) | `src/sastudio/data/fonts/Mukta-*.ttf` | 2014 Girish Dalvi, Ek Type | same commit, unmodified, SHA-256 `2958e4af…9688` (Regular), `7d22891c…0a12` (Bold) |
| Noto Sans Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu, Kannada, Malayalam (variable) | `src/sastudio/data/fonts/NotoSans*[wdth,wght].ttf`, licence `OFL-NotoSans-Indic.txt` | 2022 (Bengali 2025) The Noto Project Authors | `google/fonts` main, 12 November 2026, unmodified; versions Bengali 3.011, Gurmukhi 2.004, Gujarati 2.106, Oriya 2.007, Tamil 2.004, Telugu 2.005, Kannada 2.006, Malayalam 2.104; SHA-256 `dcd42978…3a05a` (Bengali), `1e6f728f…dc5f2` (Gurmukhi), `9901d855…ac428` (Gujarati), `91034227…3ba82` (Oriya), `aa3a9b32…7cf88` (Tamil), `e618af7b…7334d` (Telugu), `cca4f3b3…97ec9` (Kannada), `312e0e7c…6fb56` (Malayalam) |

## Tools you install yourself (not included)

| Tool | Used for | Licence |
|---|---|---|
| FFmpeg | encoding, audio | LGPL 2.1+ or GPL 2+, depending on the build |
| espeak-ng (optional) | free placeholder voice | GPL 3+ |
| Python packages: PyYAML, jsonschema, Pillow | reading projects, validation, drawing | MIT, MIT, MIT-CMU |
| Blender (clay films) | filming the clay scenes with Cycles | GPL 2+; run as a separate program, never linked or bundled |
| numpy, scipy, scikit-image (`clay` extra) | sculpting | BSD-3-Clause |
| kokoro-onnx, onnxruntime (`voices` extra) | the free neural voice | MIT |
| Kokoro-82M model weights (downloaded by `sastudio voices install kokoro`) | the free neural voice | Apache-2.0 |
| phonemizer, espeak-ng (installed by kokoro-onnx) | turning text into sounds for Kokoro | GPL 3+ |

The terminal captures were drawn with the DejaVu Sans Mono font installed on the maintainer's
system; the font is not included here, only images of text set in it.

## Sound packs you install yourself (not included)

`sastudio sounds install kenney` downloads two packs of real recordings, once, when you ask for it
(never while a film is made), checks each archive against a SHA-256 pinned in
`src/sastudio/sound/packs.py`, and keeps only the files the engine uses, with the pack's own licence
and a manifest of every file (where it came from, who made it, its licence, when it was fetched, its
checksum) in `~/.cache/sastudio/sounds/kenney`.

| Pack | Made by | Licence |
|---|---|---|
| Impact Sounds 1.0, RPG Audio | Kenney Vleugels, [kenney.nl](https://kenney.nl) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (credit is not required; it is given here) |

Recordings you bring yourself (`sound.library`, `sound.music`) are yours to license.

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

This repository contains no recorded music or sound effects (every effect and the example theme
are made by code), no stock footage, third-party 3D models, company logos or voice recordings. Add
your own only if their licence allows it.
