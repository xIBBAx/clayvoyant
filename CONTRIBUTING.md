# Contributing

Thank you for helping. Scene templates, translations, voice-provider adapters, fixes and
documentation are all welcome.

## Before you start

- Open an issue first for anything larger than a small fix, so we can agree on the approach.
- Be kind; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Set up

```bash
git clone https://github.com/xIBBAx/security-awareness-studio
cd security-awareness-studio
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e . pytest ruff
pytest
ruff check .
```

Or, with [uv](https://docs.astral.sh/uv/), which uses the exact versions in `uv.lock`:

```bash
uv sync
uv run pytest
uv run ruff check .
```

Tests never call a paid API and never need an API key.

## What you must not contribute

These rules protect everyone who uses the project. A pull request that breaks one is closed.

- **No secrets.** No API keys, tokens, passwords or `.env` files, not even "test" ones.
- **No organisation-confidential material.** Do not paste your employer's internal policies,
  email addresses, logos, screenshots, staff names or training content. Write generic sample
  content with `{org.*}` tokens instead (see [docs/SCENES.md](docs/SCENES.md)).
- **No content you don't have the right to share.** Every new image, font, sound, music or 3D
  asset needs a licence that allows redistribution, recorded in
  [ASSET_LICENSES.md](ASSET_LICENSES.md). If you are not sure, don't include it.
- **No likenesses of real people** without their written consent, and no cloned voices of real
  people.
- **No `.blend` files or code inside data.** Characters are JSON parameter files; scenes are YAML.
- **No invented policy.** Sample scenes must not state deadlines, pass marks, legal duties or
  certification claims as if they were real rules. Mark policy-like wording with `policy_note`.

## Adding things

- **A scene template:** add a YAML file under `src/sastudio/templates/starter/scenes/` using only
  existing character ids and `{org.*}` tokens; run `sastudio validate` on a new project.
- **A translation:** add `translations: { <lang>: ... }` to lines and `*_translations` to scene
  titles, headlines and takeaways. Native-speaker review is required for merge.
- **A character:** add a portrait (PNG with a transparent background) that you made or have the
  right to share, record its licence in [ASSET_LICENSES.md](ASSET_LICENSES.md), and describe it in
  [docs/CHARACTERS.md](docs/CHARACTERS.md). New clay appearance presets need the clay renderer,
  which is not included in 0.1.
- **A voice provider:** subclass `Provider` in `src/sastudio/voices/`, register it in
  `registry.py`, add it to the schema enum, and test it with a fake transport (see
  `tests/test_voices.py`). Never add live network calls to the default test run.

## Pull requests

- Keep each pull request focused, with tests for new behaviour.
- Describe what you checked by hand (for example, frames you looked at).
- CI must pass ([`.github/workflows/ci.yml`](.github/workflows/ci.yml): lint, tests, a package
  build and a render on Ubuntu and Windows). Maintainers review every change before it is merged;
  nothing is released automatically from a pull request.
- Images you add to docs must not show private dashboards, API consoles, real email addresses,
  terminal paths with your user name, or anything confidential, and must carry no metadata.

## Releasing (maintainer)

1. Update `__version__`, `CHANGELOG.md` and write `docs/releases/vX.Y.Z.md`; merge with CI green.
2. Tag the merged commit and push the tag: `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
   [`release.yml`](.github/workflows/release.yml) tests, checks the tag against the version, and
   builds the wheel, source archive and `SHA256SUMS` as the run's `dist` artifact. It never creates
   a release and has read-only permissions.
3. Create the release under your own name from those exact files:
   `gh run download <run-id> -n dist -D dist`, then
   `gh release create vX.Y.Z dist/* --verify-tag --notes-file docs/releases/vX.Y.Z.md`.
4. Rebuild the reference films with `tools/make_reference_media.py all WORK DEST` and attach them
   with `gh release upload vX.Y.Z DEST/*`; their checksums are in `MEDIA_SHA256SUMS`.
