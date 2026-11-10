# Configuration

A project is a folder:

```
my-film/
  studio.yaml          everything about the film
  scenes/*.yaml        one file per scene
  assets/              logo, character portraits, optional backdrops and music
  .env                 your API keys (optional, never committed)
  build/               rendered output
  .studio/             voice cache, ledger, work files
```

Check your changes at any time with `sastudio validate my-film`. Errors stop a render;
warnings don't.

## `project`

```yaml
schema_version: 1                 # required; the project format version
project:
  title: "Security Awareness in Twelve Stories"
  subtitle: "..."
  language: en-IN                 # the language scenes are written in
  languages: [en-IN, hi-IN]       # languages to build (each one is a separate film)
  missing_translation: error      # or `fallback` to use the main language where a line has no translation
  labels:                         # optional: words the renderer adds itself (English and Hindi built in)
    key_point: { default: "Key point", hi-IN: "मुख्य बात" }
    report_prompt: { default: "Seen something suspicious? Report it to" }
    topics: { phishing: { hi-IN: "फ़िशिंग" } }    # the topic shown on each scene's title card
  credits:
    show: true
    creator: "Your name"          # optional; nothing is required on screen
    extra: ["..."]
```

## `organization`

Everything about your organisation lives here, so nobody has to edit scenes or code.

```yaml
organization:
  name: "Example Organization"
  short_name: "Example"
  spoken_name: { default: "Example Organisation" }   # how voices say it (optional)
  security_email: "security@example.com"             # shown and spoken in reporting lines
  reporting_url: "https://example.com/report"         # optional, shown on the closing card
  security_team: "the security team"
  it_team: "the IT service desk"
  training_title: "Security Awareness 2026"
  logo: assets/logo.png                                # PNG, JPG or WebP; any proportions
  palette: { primary: "#1E4E5F", accent: "#E07A3F", background: "#F4EFE6", text: "#1C1C1E" }
  terms:                                               # your own words, used as {org.<name>}
    people: "colleagues"
    laptop: "work laptop"
    badge: "ID badge"
  announcement: "..."                                  # optional line on the title card
  translations:                                        # organisation fields in other languages
    hi-IN: { security_team: "security team", it_team: "IT team" }
```

`security_email` is your organisation's real reporting address. The examples use
`security@example.com`, a reserved example domain. Text on coloured cards and name labels is
checked for contrast (4.5:1) and switched to black or white when your colour is too light or
dark; check headline colours yourself.

## `characters`

```yaml
characters:
  - id: leo                        # stable id used in scenes; never shown
    name: Leo                      # display name: subtitles, labels, transcripts
    role: New starter
    pronouns: he                   # he | she | they  -> {leo.they} {leo.their} ...
    gender: masculine              # masculine | feminine | other -> grammar choices
    forms:                         # other ways to refer to them: {leo.full_name}
      full_name: "Leo Mensah"
      hi-IN.name: "लियो"           # display name in a specific language
    spoken: { default: "Leo", hi-IN: "लियो" }   # what voices say (optional)
    pronunciation:                 # provider-specific hints (optional)
      elevenlabs: { alias: "Lee-oh" }
      sarvam: { text: "लियो" }
    voice: { provider: offline }   # see VOICE_PROVIDERS.md
    look:
      portrait: assets/characters/leo.png   # the v4 clay style shows this: any PNG with transparency
      preset: leo                  # the bundled character this one starts from (looks, in every style)
      colors: { top: "#8C5A3C" }   # clay outfit colours; used only by the clay renderer (not in this release)
      style: v3                    # optional: this character's style (v1 sketch, v2 flat, v3 cutout, v4 clay)
      design:                      # optional: how the drawn styles (v1-v3) draw this character
        outfit: { style: kurta, color: "#3E6B5A" }
        extras: [glasses]
```

`style` overrides the film's `render.character_style` (default `v4`, the clay portraits). A
`design` lists only what differs from the preset; every field and choice is in
[CHARACTERS.md](CHARACTERS.md#describe-your-own-character).

Renaming a character is one edit to `name` (and `spoken` if it should sound different).
Every subtitle, label, transcript and spoken line that uses `{leo}` follows, and only lines
that actually say the name are re-voiced.

## `voices`, `speech`, `render`

See [VOICE_PROVIDERS.md](VOICE_PROVIDERS.md) for `voices` and `speech`, and
[RENDERING.md](RENDERING.md) for `render`. Scenes are described in [SCENES.md](SCENES.md).

A complete, commented example with every common change marked is in
[examples/quillmere/studio.yaml](../examples/quillmere/studio.yaml).

## Paths

Every path in a project is relative to the project folder. Absolute paths, `..` and links
that point outside the folder are refused, so a project you download from someone else
cannot read or overwrite your other files.
