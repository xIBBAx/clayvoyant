# Changelog

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
- Frame-exact audio, loudness levelling, SRT/WebVTT subtitles, transcripts, manifests checked
  with ffprobe, and scene-level incremental re-rendering.
- Templates: starter (12 scenes, English), short (3 scenes, English and Hindi), education; a worked
  example in `examples/northgate` (3 scenes: a new brand, a renamed character, English and Hindi).
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
