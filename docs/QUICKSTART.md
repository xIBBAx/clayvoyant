# Quickstart: your first film in ten minutes

This uses only free, local tools. No API key, no GPU.

```bash
sastudio init my-film --org "Your Organisation" --email security@your-org.in
sastudio validate my-film                 # check it
sastudio render my-film --preset draft    # render it: about a minute
```

`init` puts your organisation's name and reporting address into the copy of the starter project.
Add `--style v3` for drawn cut-out characters that talk and blink, `--logo logo.png` for your
logo and `--report-url https://...` for a reporting form. Without them you get example values,
which `init` points out, and a final render refuses to put an example address in a film.

The film, subtitles and transcript are in `my-film/build/en-IN/`:

- `Security_Awareness_in_Twelve_Stories.en-IN.mp4`
- `....srt` and `....vtt` subtitles, `....transcript.txt`
- `manifest.json`: what was built, how long it is, loudness, checksums

The starter project uses offline voices: a robotic espeak-ng voice if you installed it,
otherwise silence timed like speech. It renders the whole pipeline end to end so you can check
everything before paying for real voices.

## Make it yours

Open `my-film/studio.yaml` and change:

```yaml
organization:
  name: "Quillmere Logistics"            # your organisation
  security_email: "security@quillmere.example"
  security_team: "the Quillmere security team"
  logo: assets/logo.png                  # replace the file with your logo
```

Then:

```bash
sastudio validate my-film
sastudio script my-film --scenes too_good_email   # read what will be shown and spoken
sastudio render my-film --preset draft
```

Only the scenes you changed are rendered again.

## Pick a character style

```bash
sastudio characters my-film --sheet cast.png   # your cast in all four styles, side by side
```

Then add one line under `render:` in `my-film/studio.yaml` and render again:

```yaml
render:
  character_style: v3    # v1 sketch, v2 flat, v3 cutout (these three talk and blink), v4 clay (default)
```

## Next steps

- Rename characters, change voices and languages: [CONFIGURATION.md](CONFIGURATION.md)
- Styles and describing your own characters: [CHARACTERS.md](CHARACTERS.md)
- Real voices: [VOICE_PROVIDERS.md](VOICE_PROVIDERS.md) and [API_SETUP.md](API_SETUP.md)
- Write scenes: [SCENES.md](SCENES.md)
- Presets, single scenes, subtitles and output files: [RENDERING.md](RENDERING.md)
- A complete three-scene worked example (new brand, a renamed character, English and Hindi): [examples/quillmere](../examples/quillmere/)
- Something went wrong: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Shorter or bilingual film: `sastudio init my-short --template short` (3 scenes, English + Hindi)
