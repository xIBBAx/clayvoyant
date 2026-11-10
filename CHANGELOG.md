# Changelog

## 0.2.0 (2026-11-10)

### Characters in four styles

- **v1 sketch, v2 flat, v3 cut-out** are new drawn styles, made by this tool from scratch at render
  time (`src/sastudio/render/figures.py`; no image files, nothing downloaded). **v4 clay** is the
  bundled clay portraits and stays the default, so existing projects render exactly as before.
- In the drawn styles **the speaker talks and blinks**: the mouth follows the voice's loudness, or
  the letters of the subtitle when the voice is the silent placeholder (Devanagari vowels
  included), animated on twos. Bodies stay still and cards still cut.
- **Describe a character in text** with `look.design`: skin, hair (10 styles including a
  headscarf), outfit (blazer, suit, jacket, shirt, sweater, kurta), shoes, and extras such as
  glasses, beard, bindi or earrings. No drawing skills or image files needed.
- `render.character_style` sets the style for the film; `look.style` overrides it per character.
- `sastudio characters my-film --sheet cast.png` draws the cast in every style before you render.
- Figures are drawn once per design and kept in `.studio/work/figures`; drawing is deterministic.
- `examples/quillmere` now renders in the cut-out style, with Kabir described in a kurta.

### Safer finished films

- `render --preset final` refuses a film whose reporting email or URL is still a placeholder on a
  reserved example domain (`example.com`, `.example`, `.test`, ...), because a shared film cannot be
  corrected. `validate` shows them as notes (not warnings, so `--strict` is unchanged) and draft and
  preview renders record them in the manifest. `--allow-placeholder-contacts` allows a demo film.

### Releases

- The release workflow now only tests and builds the packages; the maintainer creates each release
  under their own name from those files (CONTRIBUTING.md, "Releasing").

## 0.1.0 (2026-11-09)

First public version. Install it from this repository; it is not on PyPI yet (see below).

### What it makes

Captioned training films built from cards: a still portrait of whoever is speaking, every line in
large on-screen text, key-point cards, title and closing cards, and hard cuts between them. The
characters are not animated in this version. Each film comes with SRT and WebVTT subtitles, a
plain-text transcript and a manifest with SHA-256 checksums.

### Included

- Project format version 1: organisation, characters, scenes, voices, speech rules and render
  settings in `studio.yaml`, checked against a JSON schema plus semantic checks (speakers,
  tokens in every language, scene dependencies, paths, voices).
- Dialogue templates with stable character ids, display vs spoken names, pronouns, gendered
  grammar choices, language-specific name forms and per-language organisation fields.
- On-screen labels the renderer adds itself ("Key point", the closing prompt, scene topics) can be
  set per language in `project.labels`; English and Hindi are built in.
- Voice providers: Sarvam (bulbul:v2, v3, v4-flash), ElevenLabs (v2/v3/v4 and Flash models),
  and a free offline provider (espeak-ng or timed silence). Content-addressed cache, budget
  limits, retries with backoff, an append-only ledger, and no paid request without `--live`.
  The Sarvam and ElevenLabs adapters are tested against recorded responses; no live request was
  made for this release.
- `--voice-fallback offline` renders lines that have no generated audio yet with a labelled
  placeholder, so a project that uses a paid voice can still be previewed for free.
- Pronunciation export for ElevenLabs (rules JSON, PLS) and Sarvam (dictionary JSON).
- Cards renderer for any computer (no GPU), with five clay-style character portraits designed for
  this project.
- Films are tagged BT.709 with FFmpeg 6 through 9 (FFmpeg 9 takes colour tags from frames, not
  encoder options; found by the Windows CI run).
- Frame-exact audio, loudness levelling, SRT/WebVTT subtitles, transcripts, manifests checked
  with ffprobe, and scene-level incremental re-rendering.
- Templates: starter (12 scenes, English), short (3 scenes, English and Hindi), education; a worked
  example in `examples/quillmere` (3 scenes: a new brand, a renamed character, English and Hindi).
- `sastudio doctor` finds NVIDIA GPUs under WSL2, where `nvidia-smi` is not on PATH.
- Robustness: `validate` opens every image so a damaged logo or portrait fails early; stored scene
  videos are checked before reuse and damaged ones are rendered again; permission and disk-full errors
  are explained instead of shown as tracebacks; output stays UTF-8 on Windows consoles and pipes.
- Documentation for installation, configuration, scenes, characters, voices, API keys,
  rendering, architecture, troubleshooting and a glossary.
- `tools/make_reference_media.py` rebuilds every reference film, the README stills and
  `docs/media/film/VERIFY.md` from this repository alone.
- CI on Ubuntu and Windows (Python 3.11-3.13) including a render from the built wheel, secret
  scanning, a dependency audit, Dependabot for GitHub Actions and the uv lock file, and a
  tag-driven draft-release workflow.

### Reference media

The release page has the 12-scene starter film (1920x1080, about 14 minutes), a trailer and the
worked example in English and Hindi, with subtitles and checksums. Their voices are the offline
placeholder, which is silent: the dialogue is in the on-screen text and subtitles.

### Not included

- The clay renderer's Blender engine. `--renderer clay`, `render.renderer: clay` and
  `sastudio clay` stop with a clear message. The character portraits ship as images.
- Publication on PyPI. The publishing workflow exists but is manual and has not been run.
- Live-tested Sarvam or ElevenLabs integration, a graphical editor, macOS testing.

### Security

- Requires Pillow 13.0 or newer: Pillow 12.3 has published vulnerabilities in image decoding,
  and project images are untrusted input.
