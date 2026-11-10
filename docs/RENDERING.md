# Rendering

`sastudio render` turns a project into a finished film: a video, subtitles in two formats, a
transcript and a manifest. It needs Python and FFmpeg, and no GPU, no Blender and no account.

```bash
sastudio render my-film                                  # the whole film, with the project's settings
sastudio render my-film --preset draft                   # fast, small, for checking timing
sastudio render my-film --scenes too_good_email          # one scene (or a comma-separated list)
sastudio render my-film --lang hi-IN                     # one of project.languages
sastudio render my-film --voice-fallback offline         # placeholder voices for lines not generated yet
```

## Renderers

| Renderer | Status in 0.1 | What it draws |
|---|---|---|
| `cards` (the default) | **Included** | A clean 2D layout: your logo and colours, scene titles and headlines, each character's portrait with a name label, the speaker highlighted, subtitles, key-point cards, an intro card and a closing card with your reporting address. |
| `clay` | **Not included in this release** | Animated 3D clay puppets rendered in Blender. The `--renderer clay` option, `render.renderer: clay` and the `sastudio clay` commands remain, but stop with a clear message. |

The five character portraits that ship with the starter project are images, so the cards
renderer uses them on any computer. They were rendered with the clay engine, which is not part
of this release; you cannot re-render or re-sculpt them with 0.1. To use your own artwork, point
`look.portrait` at any PNG with a transparent background ([CHARACTERS.md](CHARACTERS.md)).

## Presets

Every preset is 24 frames per second, H.264 video (`yuv420p`, BT.709) with AAC stereo audio at
48 kHz.

| Preset | Size | Encoder setting | Use it for |
|---|---|---|---|
| `draft` | 960 x 540 | CRF 30, `veryfast` | checking timing and wording while you edit |
| `preview` | 1280 x 720 | CRF 23, `fast` | sharing a review copy |
| `final` | 1920 x 1080 | CRF 16, `slow` | the film you publish |

Set the default in `studio.yaml` (`render.preset`) and override it with `--preset`.

### Character styles

`render.character_style` picks how characters look: `v1` sketch, `v2` flat, `v3` cutout or `v4`
clay (the default). The drawn styles (v1-v3) animate the speaker's mouth and blinks on twos; see
[CHARACTERS.md](CHARACTERS.md#four-styles). Changing the style re-renders every scene once; the
figures are drawn once per design and kept in `.studio/work/figures`.

Measured on the machine in [REQUIREMENTS.md](REQUIREMENTS.md): drawing all six variants of one
character takes about 0.3 s (flat), 0.4 s (sketch) and 0.9 s (cut-out); a 75-second scene at
1280x720 renders in 14-20 s from a clean cache in a drawn style, against a few seconds in clay,
because the speaker's face changes 12 times a second instead of holding still.

### A final film needs your real reporting address

Every template ships the placeholder `security@example.com` and `https://example.com/report`, which
use domains reserved for examples (RFC 2606 and RFC 6761): nobody receives mail or reports there.
A film cannot be corrected once it is shared, so `--preset final` refuses to render while the
reporting email or URL (including any per-language `translations`) uses such a domain. `validate`
points them out as notes, and draft and preview renders list them in the manifest's warnings.
For a demonstration film, add `--allow-placeholder-contacts`.

## What a render produces

For a project titled "Security Awareness in Twelve Stories" built in `en-IN`, the output
folder (`render.output`, default `build/`) contains:

```
build/en-IN/
  Security_Awareness_in_Twelve_Stories.en-IN.mp4
  Security_Awareness_in_Twelve_Stories.en-IN.srt          subtitles (SubRip)
  Security_Awareness_in_Twelve_Stories.en-IN.vtt          subtitles (WebVTT)
  Security_Awareness_in_Twelve_Stories.en-IN.transcript.txt
  manifest.json
```

Rendering only some scenes adds their ids to the name
(`..._too_good_email.en-IN.mp4`) and leaves out the intro and closing cards, so a scene can be used
on its own.

`manifest.json` records the tool version, preset, every scene's frame count and length, which
scenes were rendered or reused, which lines used placeholder voices, the measured loudness, what
`ffprobe` found in the finished file, and a SHA-256 checksum of every output. It contains file
names, not folder paths.

After encoding, the build checks the film with `ffprobe`: the number of video frames must equal
the timeline, and the audio must last as long as the video. If either check fails, the build stops
with an error instead of leaving a broken file.

## Only what changed is rendered again

Each scene video is stored in `.studio/work/<language>/scenes/` with a key made from everything
that affects its pictures: the scene's timeline (text, timing, speakers), the look (logo, colours,
portraits, backdrop images, subtitle settings), the preset and the tool version. If the key
matches and the stored video still decodes to the expected number of frames, the scene is reused;
a damaged stored video is rendered again. Changing a logo re-renders every scene but re-voices
nothing; changing one line re-renders one scene.

Voices have their own cache (see [VOICE_PROVIDERS.md](VOICE_PROVIDERS.md#cache)).
`sastudio clean my-film` deletes the scene videos and work files in `.studio/work/`. It keeps the
finished films in the output folder and the voice cache, which may have cost money. Delete the
output folder yourself if you want it gone.

## Sound

- Each spoken line is converted to mono 48 kHz, trimmed, and levelled to about -18 LUFS with
  peaks at or below -2 dBFS, so voices from different providers sit at the same level.
- The finished mix is normalised to -16 LUFS integrated with a -1.5 dBTP true-peak ceiling, in
  two passes. The manifest records the measured result.
- Films made with silent placeholder voices are silent; the manifest says so instead of
  reporting a loudness.
- Optional background music: `render.music: assets/music.mp3` and `render.music_volume_db`
  (default -24). The project ships no music; use only music you are licensed to use.

## Subtitles

- `.srt` and `.vtt` files are always written, with cue times taken from the real audio of each line.
- Lines are wrapped to at most 42 characters and 2 lines per cue. Long lines become several cues.
- `render.burn_subtitles: true` also draws them into the picture (the starter templates do this).
  With `false` the film has no text over the action and players show the subtitle file instead.
- `render.subtitle_speaker_labels: true` puts the speaker's name before each cue in the `.srt`
  file ("MIRA: ..."). The `.vtt` file always names the speaker with WebVTT voice tags
  (`<v Mira>`), which players can show or hide. Burned-in subtitles never carry a label; the
  picture already shows who is speaking.
- The build warns when a cue is faster than 20 characters per second, wider than 42 characters,
  or overlaps the next one.

## Intro, closing card and backdrops

- `render.intro` (default on): title, subtitle, organisation name and `organization.announcement`.
- `render.outro` (default on): "Seen something suspicious? Report it to" with
  `organization.security_email`, `organization.reporting_url` and the optional credits from
  `project.credits`. The words the renderer adds itself ("Key point", the closing prompt, the topic
  on each scene's title card) have built-in English and Hindi versions and can be changed per
  language in `project.labels` ([CONFIGURATION.md](CONFIGURATION.md#project)).
- `setting.image` on a scene sets a backdrop picture (PNG, JPG or WebP inside the project). Without
  it, scenes use the organisation's background colour. `setting.backdrop` and
  `setting.time_of_day` are descriptive only; the cards renderer does not draw them.

## Speed and memory

Scenes render in parallel. `--jobs` sets how many at once (default: half your CPU threads, at most
6), and each scene's encoder gets an equal share of the threads. Memory, not CPU, is usually the
limit: lower `--jobs` if your computer starts swapping.

Measured on one machine (Intel Core i7-10750H, 12 threads, 7.7 GB available to WSL2, FFmpeg 6.1.1),
rendering the 12-scene starter film (14 min 23 s, silent placeholder voices). Examples, not promises:

| Job | Wall clock | Peak memory |
|---|---|---|
| Whole starter film, `preview` (1280 x 720), `--jobs 4` | 74 s | 237 MB |
| Whole starter film, `final` (1920 x 1080), `--jobs 3` | 2 min 22 s | 615 MB |
| Re-running the same render with nothing changed | every scene reused | |
| Three-scene example, `draft`, English / Hindi | 14 s / 21 s | 126 MB / 128 MB |

The cards renderer draws with Pillow and encodes with FFmpeg's x264 on the CPU. A GPU does not
speed it up.

## Clay renderer status

The clay renderer's orchestration code ships in `src/sastudio/render/clay.py`, but the Blender
engine it drives does not ship in 0.1. Its absence is detected, not crashed into: `sastudio
doctor` reports "Clay renderer: not included in this release", `sastudio validate` flags
`render.renderer: clay`, and `sastudio render --renderer clay` stops before any work starts. If a
later release includes the engine, `SASTUDIO_CLAY_DEVICE=CPU` will skip the GPU request; by
default the engine asks for a GPU and falls back to the CPU.

## Problems

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#rendering).
