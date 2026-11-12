# For coding assistants

This file is for an AI coding assistant working in this repository, or asked to make a film with
it. People should start with the [README](README.md).

## What this is

Clayvoyant turns a folder of YAML (a cast, scenes, lines) into a finished film: voices, clay
stop-motion or drawn characters, cameras, subtitles. The Python package is `sastudio`; the
commands `clayvoyant` and `sastudio` are the same program.

## Set up and check

```bash
pip install -e . pytest ruff          # or: uv sync
pytest -m "not blender"               # about two minutes; never needs a key, a network or Blender
ruff check src tests tools
```

Clay films also need `pip install -e ".[clay,voices]"`, Blender 4.2 or newer and
`sastudio voices install kokoro`. `sastudio doctor` says what is missing.

## Making a film for someone

1. `sastudio init my-film --template starter|short|education|india --org "Their name" --email they@their.org`
2. `sastudio brief my-film "what the film is about"` prints everything a writer needs: the cast,
   the places, every gesture, feeling and camera the engine knows, and the exact file format to
   answer in. Write the scenes from that brief; do not invent fields.
3. `sastudio validate my-film --strict` until it reports 0 errors and 0 warnings. Its messages say
   which line and how to fix it.
4. `sastudio direct my-film` shows the shot plan before anything is filmed.
5. `sastudio render my-film --preset draft` (drawn characters, CPU only, minutes) or
   `sastudio film my-film --preset draft` (clay; needs Blender; the 82-second sample takes
   about 55 minutes at `preview` on a GTX 1660 Ti). Add `--lang` for each language.
6. `sastudio share my-film --each` (phone clips) and `sastudio posters my-film` if they are wanted.

Look at frames before saying a film is finished: `ffmpeg -ss 12 -i FILM.mp4 -frames:v 1 frame.png`.

## Rules that are easy to break

- **Nothing paid runs by itself.** Never add `--live`, and never set a character budget, unless
  the person asked for a paid voice and named a limit. Kokoro, recorded and offline voices are free.
- **Advice in a film must be true.** Safety advice (helpline numbers, what a bank will never ask)
  comes from a public advisory, linked in the scene's `policy_note` or the docs. Do not write a
  number, a portal or a rule from memory.
- **No real people, no real organisations' material, no assets without a recorded licence**
  ([CONTRIBUTING.md](.github/CONTRIBUTING.md), [ASSET_LICENSES.md](docs/ASSET_LICENSES.md)). Sets and props
  are built by code.
- **Dialogue names are tokens** (`{leo}`, `{org.name}`), never plain text, so a rename changes
  every line.
- **Hindi lines are written in Devanagari**, including borrowed English words (कॉल, ओटीपी): that is
  what the voice reads. Roman-letter Hindi on screen is `hi-Latn`, spelled by the film
  ([docs/INDIA.md](docs/INDIA.md)).

## Changing the code

- The map of every module is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read it before
  searching.
- Films are cached by what would change the picture or the sound. If you change what something
  looks or sounds like, bump the constant that keys its cache, or old results will be reused:
  `stopmotion.ENGINE_VERSION` (filmed shots), `render/clay.CLAY_VERSION` (sculpted characters),
  `render/figures.FIGURES_VERSION` (drawn characters), `voices/base.ADAPTER_VERSION` (audio).
  If the picture does not change, do not bump them: a bump makes everyone film again.
- `src/sastudio/engine/` runs inside Blender's Python, not the project's. It cannot import the
  rest of the package, and Blender reads those files again for every shot, so do not edit them
  while a film is rendering from the same checkout.
- The project format is `src/sastudio/schema/project.schema.json`. A new field needs the schema,
  the loader in `project.py`, a test, and a line in the matching guide under `docs/`.
- Tests are named for what a person would notice (`test_nobody_is_framed_before_they_walk_in`).
  Tests that need Blender carry `@pytest.mark.blender` and are skipped where it is absent.
- Keep comments and docs plain: what it does and why, in the words a film-maker would use.
- One focused pull request per change, with what you looked at by hand in its description. Films
  (`*.mp4`) are release files and are not committed, apart from the small samples under
  `docs/media/`.
