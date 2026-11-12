# Changelog

## 0.3.0 (2026-11-12)

### Solid contact

- **Nothing passes through anything.** Feet come down on the real surface under the whole sole (floor,
  rug, a table's base); a seated body rests on the seat and its thighs on the cushion; hands laid on a
  table rest on its top, with the forearms clear of its edge; feet and shins are moved out of chair
  bases and table feet; a gesturing hand is nudged out of a mug or a machine. Every correction is
  measured on the posed geometry and kept for that seat, table or spot.
- Chairs are shallower than a thigh is long, so knees clear the front edge.
- People walk around furniture: each walk is routed on a top-down map of the set (a body's width kept clear of
  every table, chair and counter), and an entrance starts early enough for the longer way round.
- Chairs move: pulled back for somebody about to sit, drawn in as they sit, pushed back as they stand. People come
  to a chair from its side and stand up a little behind where they sat.
- Walks keep a body's width from everything solid where there is room, and never less than the body itself.
- A carried mug is held in a cupped hand and a phone being read lies along the palm; neither passes through the hand.
- `tools/check_contacts.py PROJECT` reports any character triangle inside the set or another
  character, frame by frame, and fails if there is one. The sample film: 0 in 116 sampled drawings.
- The sample film is filmed again with all of it ([watch](https://cdn.jsdelivr.net/gh/xIBBAx/clayvoyant@8cb3c0a/docs/media/the-fast-one.mp4)).

### For India

- **`sastudio init --template india`**: five scenes, six characters, English and Hindi. "Digital arrest" on a
  video call, a UPI collect request that wants a PIN, a caller who needs an OTP, an electricity-bill message with an
  app to install, a customer-care number from the top of a search. Every scene names the I4C, RBI or DoT advisory its
  advice follows. A template that brings its own scenes no longer receives the starter's.
- **Nineteen Thirty** (`examples/nineteen-thirty`): the digital-arrest scene as a film of its own, in both languages.
- **Lip sync reads nine Indian scripts.** Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada and Malayalam
  are read through the Devanagari table they share a layout with, so recorded or Sarvam lines in those languages
  move the mouth. A vowel sign or virama no longer splits a word (it closed the mouth mid-word in Hindi too).
- **Subtitles and cards in those scripts** use bundled Noto Sans fonts (SIL OFL), which also carry Latin.
- [Films for India](docs/INDIA.md): the template, its sources with links, the languages, a checklist.

### Characters, sets and planning

- Nobody is framed before they walk in: shots before an entrance line leave that person out (an over-the-shoulder
  past someone not yet in the room showed an empty spot).
- `home_desk` has a `sofa_side` mark, to stand and talk to whoever is on the sofa.
- The knit vest's ID card and lanyard are an extra (`extras: [lanyard]`), not part of every vest.
- The clay kurta ends straight above the tops of the legs; it used to curve between them like a bodysuit, with the
  thighs showing through its front.
- A `shirt` outfit is drawn in `outfit.color` by the drawn styles too, as the clay sculptor makes it.

### Writing

- **`sastudio brief PROJECT "idea"`** prints a writing brief for a person or any chat assistant: the cast, the
  places and their marks, the acting vocabulary, the format with a complete example, and the rules the validator
  applies, all read from the validator's own tables. [Writing with an assistant](docs/WRITING_WITH_AN_ASSISTANT.md).
- [Why Clayvoyant exists](docs/WHY.md): who it is for, what it costs, how it compares.

### Clay films

- **`sastudio film`** makes the whole film in clay stop motion with one command: voices, sculpted
  characters, sets, cameras, light, lip sync, subtitles. `sastudio motion` is a silent preview of
  one scene or shot.
- **The clay engine is part of the package** (`src/sastudio/engine`): characters sculpted from
  signed-distance forms and marching cubes, an anatomical arm and hand rig with fingers, a
  21-control face, clay, cloth and skin materials.
- **Any described character is sculpted.** `look.design` now drives the clay figure as well as the
  drawn ones, with `body` (build, height), `face` sliders, `acting` (energy, looseness, posture,
  pace) and `clay` overrides. New garments (shirt, sweater, hoodie, kurta, zip jacket, knit vest),
  hair (short, long, ponytail, headscarf, bald), beards, moustaches and a bindi.
- **Acting**: walking on planted feet, sitting, more than forty gestures, twenty-one feelings,
  listener reactions, eyes that lead the head, speech in the body, mugs and phones in the hand,
  typing with hands on the desk, walking to a mark (`go:`), entrances through a door that opens,
  business under way as a scene opens.
- **Eight sets built by code**: office, reception, meeting room, home, cafe, corridor, street,
  classroom; morning, day, evening and night; your palette and name on the walls.
- **Scenes open on a filmed shot** with the title over it: establishing push-in, door reveal,
  follow an object, match cut, fade from black.
- **Shots are cached by what can affect them** and resume at the first missing drawing.
- **The camera can be placed by hand**: a shot takes an exact `position` and `aim`; otherwise it is
  framed from where the people really are and follows a subject who walks, stands or sits.
- **Guests**: imported glTF, FBX and OBJ characters act in clay scenes; they are grounded by their
  real geometry and stored animation is removed. Characters export to GLB, FBX, OBJ and `.blend`.
- **Cutting inside a line.** A shot can cover a `part` of one line, and the cut lands on the
  nearest drawing where the speaker's mouth is at rest. Left alone, the planner cuts to the
  listener part way through long lines (`direction.reactions: false` turns it off), the listener's
  answer opens a size wider, and a short sharp line gets an extreme close-up. `reaction` and
  `extreme_close_up` were declared before but could never be chosen.
- **Props that move on a track**: `direction.props` opens and closes laptops, slides, turns, hides and
  shows things on the set at a moment of a line.
- **Dressing that moves**: `direction.dressing: [steam, birds]` puts vapour over the hot drinks and
  birds across the sky outside, built by code, each on its own clock.
- **An insert on a prop is filmed** (`camera: insert, who: [laptop]`) with the line heard over it.
  Before, such a line was skipped without a word and fell back to the drawn style.
- **People turn to the person they talk to.** Standing marks pinned everyone's body to the lens, so
  in the sample Tara stood square to the camera while talking to Bashir behind her; now a standing
  person turns towards whoever matters (seats still face their table).
- **Framing**: a shot no longer shows the back of the speaker's head (an over-the-shoulder from
  behind a listener who stands upstage becomes a two-shot or a medium), and everyone a shot is on
  stays inside the frame however near the lens they sit.
- `examples/the-fast-one`: an original two-scene short made entirely by these commands.

### Reliability

- A hung Blender is stopped: the time limit and a stall watchdog (no new drawing for 20 minutes)
  are enforced while reading its output. Before, a Blender that hung without writing blocked forever.
- A shot whose Blender crashes or hangs is started once more from its first missing drawing; an
  error in the engine's own code is not retried.
- Blank drawings (one flat colour, or unreadable) are thrown away and drawn again; a shot that stays
  blank fails with a message.
- No Blender outlives sastudio: Ctrl+C and `kill` stop it, and on Linux even `kill -9` does.
- `sastudio clean <project> --shots` lists filmed shots that nothing uses any more, with sizes, and
  deletes them only with `--yes`. A shot renumbered by an edit is found by its content and reused.
- `sastudio motion --out` accepts a folder.
- Tests: any internet connection from the test process fails the test; tests that need FFmpeg or
  Blender skip with a reason when it is missing (one used to fail); a real two-drawing clay render
  runs when Blender is present.

### Voices

- **`kokoro`**: a free neural voice that runs on your computer (British and American English,
  Hindi), with phoneme timings used for lip sync. `sastudio voices install kokoro`.
- **`recorded`**: your own recordings, one file per line.
- `--voices kokoro|recorded|offline` uses one free provider for a whole render.

### Changed

- New optional extras: `clay` (numpy, scipy, scikit-image) and `voices` (kokoro-onnx).
- The mark is now sculpted by the engine: a thumbprint in clay whose whorl is an eye.


- `sastudio init` takes your organisation's details: `--org`, `--short-name`, `--email`,
  `--report-url`, `--style` and `--logo` (any image, saved as PNG). Every option is checked before
  anything is created, values are written safely (quotes, Hindi and other scripts), and the
  template's explanatory comments stay. A plain `init` now says which reporting contacts are
  still placeholders.
- `.gitignore` keeps local editor and AI-agent settings (`.claude/`, `.cursor/`, `.codex/` and
  others) out of the repository.

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
