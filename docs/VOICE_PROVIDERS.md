# Voice providers

Each character has a voice. A voice comes from one of five providers:

| Provider | Cost | Account | What it sounds like | Tested how |
|---|---|---|---|---|
| `kokoro` | free | none | a natural neural voice that runs on your computer: British and American English, Hindi | synthesised and rendered into films on the reference laptop; request building and failures in every test run |
| `recorded` | free | none | your own recordings, one file per line | end to end, every test run |
| `offline` | free | none | espeak-ng's robotic voice if installed, otherwise silence timed like speech | end to end, every test run |
| `sarvam` | paid per character (your account) | [Sarvam AI](https://docs.sarvam.ai/) | natural Indian-language voices (Bulbul models) | request and error handling against recorded responses; **no live call has been made for this release** |
| `elevenlabs` | paid per character (your account) | [ElevenLabs](https://elevenlabs.io/docs/) | natural multilingual voices | request and error handling against recorded responses; **no live call has been made for this release** |

`--voices kokoro` (or `recorded`, or `offline`) on `sastudio film` and `sastudio render` uses one
free provider for the whole cast in that render, whatever the project says.

The offline provider proves that the pipeline works. It says nothing about whether Sarvam or
ElevenLabs will work with your account; check that with a tiny live run (below) before you
commit to a full film.

To get a key, see [API_SETUP.md](API_SETUP.md).

## Choosing a voice

```yaml
characters:
  - id: mira
    name: Mira
    voice: { provider: sarvam, model: "bulbul:v3", speaker: "priya" }

  - id: leo
    name: Leo
    voice:
      provider: elevenlabs
      model: eleven_multilingual_v2
      voice_id: "<copy it from your ElevenLabs voice library>"
      settings: { stability: 0.5, similarity_boost: 0.75, speed: 1.0 }
      languages:                              # optional: a different voice for one language
        hi-IN: { provider: sarvam, model: "bulbul:v3", speaker: "rahul" }
```

A per-language entry must name its `provider`. Settings are merged with the main voice's settings.

Provider-wide options go in `voices.providers`:

```yaml
voices:
  providers:
    offline: { engine: auto }                 # auto | espeak | silence
    sarvam: { model: "bulbul:v3", sample_rate: 24000 }
    elevenlabs: { output_format: wav_24000 }
```

`sastudio characters my-film` lists every character's voice per language. `sastudio validate`
checks each voice against the provider's catalogue before anything is sent.

## Kokoro

A free neural voice with no account, no key and no network once installed.

```bash
pip install "clayvoyant[voices]"     # the kokoro-onnx package
sastudio voices install kokoro                      # the model, once: about 350 MB, checked by SHA-256
```

```yaml
    voice: { provider: kokoro }                                   # a voice is chosen for the character and kept
    voice: { provider: kokoro, speaker: bf_emma }                 # or name one
    voice: { provider: kokoro, speaker: hf_alpha, settings: { speed: 0.95 } }
```

| Language | Voices this adapter is set up with |
|---|---|
| `en-GB`, `en-IN`, `en` | `bf_emma`, `bf_isabella`, `bf_alice`, `bf_lily`, `bm_george`, `bm_fable`, `bm_daniel`, `bm_lewis` |
| `en-US` | `af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `am_michael`, `am_fenrir`, `am_puck`, `am_eric` |
| `hi-IN`, `hi` | `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi` |

With no `speaker`, each character gets a voice of its own that matches its `gender` and stays the
same from render to render.

What to know before relying on it:

- **There is no Indian-English accent.** Lines in `en-IN` are read by a British voice (or an
  American one if you name it). For Indian English use Sarvam, or record the lines.
- **Hindi** has four voices; the model's authors grade them below the English ones. Mixed
  Hindi-English lines are spoken. Listen before you publish; this project has checked that the
  output is speech and is timed correctly, not how natural a native speaker finds it.
- It reports when each sound is spoken, which the clay renderer uses for lip sync.
- On the reference laptop a line takes about half its own length to generate, on the CPU, in
  about 600 MB of memory.
- No voice cloning. The voices are the model's own.

Licences: Kokoro-82M's weights are Apache-2.0; the `kokoro-onnx` package is MIT; its text front
end (`phonemizer`, `espeak-ng`) is GPL-3.0. None of them is part of this package: `pip` installs
them beside it, and the model is downloaded to `~/.cache/sastudio/kokoro` (or `SASTUDIO_KOKORO_DIR`).

## Recorded

Your own voice, or your colleagues', with their agreement. Give a character
`voice: { provider: recorded }` and save one file per line:

```text
my-film/recordings/en-IN/te_01.wav        # .wav .flac .mp3 .m4a .ogg; the line ids are in the scene files
```

`sastudio voices plan my-film` lists every line with the words to say. A line with no recording
stops the render by name; nothing is skipped. Replace a file and only that line's shots are
filmed again. The folder can be changed with `voices.providers.recorded.folder`.

## Offline

- `engine: auto` uses espeak-ng when it is installed and silence otherwise. `espeak` requires it;
  `silence` never uses it.
- Settings: `rate` (words per minute, default 160), `pitch` (0-99, default 50), `voice` (an
  espeak-ng voice name; by default chosen from the line's language).
- Every report and manifest labels these lines as placeholders.

## Sarvam

Catalogue checked 2026-11-09 and stored in `src/sastudio/data/sarvam.json`.

| Model | Characters per request | Speakers | Settings |
|---|---|---|---|
| `bulbul:v2` | 1,500 | 7 | `pace` 0.3-3.0, `pitch` -0.75-0.75, `loudness` 0.3-3.0 |
| `bulbul:v3` (default) | 2,500 | 37 | `pace` 0.5-2.0, `temperature` 0.01-1.0 |
| `bulbul:v4-flash` | 2,500 | 222 | `pace` 0.5-2.0, `temperature` 0.01-1.0 |

- Languages: `bn-IN`, `en-IN`, `gu-IN`, `hi-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `od-IN`, `pa-IN`,
  `ta-IN`, `te-IN`.
- Speakers belong to one model and are case-sensitive; `validate` tells you which model a speaker
  belongs to. Not every speaker sounds natural in every language: listen before you choose.
- Other settings: `enable_preprocessing`, `dict_id` (a pronunciation dictionary you created in
  Sarvam). Provider option `sample_rate`: 8000, 16000, 22050, 24000, 32000, 44100 or 48000.
- Hindi written in Roman letters works but Sarvam recommends Devanagari; `sastudio script` points
  out such lines.
- If Sarvam adds speakers before this file is updated, set
  `voices.providers.sarvam.allow_unlisted: true`.

## ElevenLabs

Catalogue checked 2026-11-09 and stored in `src/sastudio/data/elevenlabs.json`.

| Model | Characters per request | Hindi | Notes |
|---|---|---|---|
| `eleven_v4` | 10,000 | yes | |
| `eleven_v4_turbo` | | yes | |
| `eleven_v3` | 5,000 | yes | |
| `eleven_v3_conversational` | | yes | |
| `eleven_multilingual_v2` (default) | 10,000 | yes | does not take a language code |
| `eleven_flash_v2_5` | 40,000 | yes | |
| `eleven_flash_v2` | 30,000 | no | English only; the only model here that takes IPA/CMU phoneme tags |
| `eleven_turbo_v2_5`, `eleven_turbo_v2` | | | deprecated by ElevenLabs; `validate` suggests the Flash replacement |

- `voice_id` is required. It is letters and digits, copied from your voice library.
- Settings: `stability`, `similarity_boost`, `style` (0-1), `speed` (0.7-1.2),
  `use_speaker_boost`, plus `seed` and `apply_text_normalization`.
- Provider options: `output_format` (default `wav_24000`; MP3 and PCM formats are also accepted),
  `pronunciation_dictionaries: [{ id: ..., version_id: ... }]` (at most 3).
- If a voice is removed from your account, the request fails with an error naming the voice. It is
  never replaced by a different voice behind your back.

## How names and words are spoken

What people read and what voices say are kept apart. Subtitles always show the display name.

```yaml
characters:
  - id: leo
    name: Kabir                                 # shown everywhere
    spoken: { hi-IN: "कबीर" }                    # what voices say (default, or per language)
    pronunciation:
      elevenlabs: { alias: "Kuh-beer" }         # or ipa: / cmu: (phoneme tags: eleven_flash_v2 only)
      sarvam: { text: "कबीर" }
      offline: { text: "Kabeer" }
speech:
  lexicon:                                      # whole-word replacements in spoken text only
    Quillmere: { default: "Quill meer" }
    Wi-Fi: { default: "why fy" }
  email_words: { default: { at: "at", dot: "dot" } }
```

Built in, and changeable through `speech.lexicon`: MFA, 2FA, OTP, VPN, USB, IT, PIN, URL, SMS and
QR are spelled out letter by letter. Email addresses and web addresses are read as words
("security at example dot com"). A lexicon entry never changes a character's name.

`sastudio script my-film` prints each line as shown and, where different, exactly what each
provider will be sent. Read it before you pay for anything.

To use the same pronunciations inside your provider account:

```bash
sastudio voices lexicon my-film --format elevenlabs-rules --out rules.json
sastudio voices lexicon my-film --format elevenlabs-pls   --out lexicon.pls
sastudio voices lexicon my-film --format sarvam-dict      --out sarvam.json
```

Numbers and dates are passed through as written; providers read them in their own way. Write
them out in words where it matters.

## Generating speech

```bash
sastudio voices plan my-film
sastudio voices generate my-film                              # free offline lines only; nothing paid
sastudio voices generate my-film --live --max-characters 2000 # paid, capped at 2,000 characters
sastudio render my-film
```

Nothing is billed unless **both** of these are true:

1. you pass `--live`, and
2. a character budget above zero is set (`--max-characters`, or `voices.budget.max_characters`,
   which is `0` in every template).

| Safeguard | How it works |
|---|---|
| Budget | Characters are counted before each request. A request that would cross the budget is not sent. `--max-requests` caps the number of requests. |
| Retries | Only for errors the provider marks as temporary (rate limits, server errors), with backoff, up to `voices.budget.max_retries`. A bad key or empty balance stops the run at once. |
| Timeouts | `voices.budget.timeout_seconds`. A request that timed out may still have been billed, so its characters count against the budget. |
| Rate limit | `voices.budget.requests_per_minute`. |
| No duplicates | Identical lines are requested once. A finished line is never requested again. |
| Resume | Re-running after a failure continues with the lines that are still missing. |
| One run at a time | A lock file in `.studio/` stops two runs on the same project. |
| Ledger | Every request is appended to `.studio/ledger.jsonl`: time, line, language, provider, cache key, characters, status, HTTP status, error code and the provider's request id. Never your API key. |

### Rendering before paid lines exist

`render` never requests paid speech. If a line's voice is Sarvam or ElevenLabs and its audio has
not been generated yet, the build stops with exit code 7 and lists the lines:

```text
error: 4 line(s) have no generated audio yet: fd_01 (sarvam), fd_03 (sarvam), ...
  Fix: Run `sastudio voices generate --live --max-characters N` (paid), or render a preview with
  `--voice-fallback offline` (free placeholder voices, clearly labelled).
```

This happens as soon as you switch one character to a paid provider, even for a quick draft. To
keep working for free, add the flag to any render command:

```bash
sastudio render my-film --preset draft --voice-fallback offline
```

Only the missing lines use the placeholder; lines you have already generated use the real voice.
Each placeholder line shows a "Preview voice" badge on screen, and the manifest lists them under
`voices.placeholder_lines`, so a placeholder can't reach a finished film unnoticed.

### Estimating cost

The project ships no prices, because they change. Copy current prices from your provider's
pricing page:

```yaml
voices:
  prices:
    sarvam:
      "bulbul:v3": { per_1000_characters: 0.0, currency: INR, checked: "YYYY-MM-DD" }
```

`sastudio voices plan` then shows an estimate per provider and model, with the date you checked.
Without a price table it shows character counts only.

### Trying a provider safely

1. Give one character the paid voice; leave the rest offline.
2. `sastudio voices plan my-film --scenes first_day` and check the character count.
3. `sastudio voices generate my-film --scenes first_day --live --max-characters 300`.
4. Listen to the files under `.studio/cache/voices/<provider>/`, then render that scene.

## Cache

Generated audio is stored in `.studio/cache/voices/<provider>/` under a hash of everything that
changes the sound: the exact text sent, provider, model, voice or speaker, language, settings,
pronunciation hints and output format. The key never includes your API key.

- Changing a logo, a colour or a subtitle setting re-voices nothing.
- Renaming a character re-voices only the lines that say the name.
- Changing a voice's model or settings re-voices that voice's lines.

The cache is local, ignored by git and kept by `sastudio clean`. Do not publish it: it contains
your dialogue.

## Who owns the audio

Speech you generate is governed by your provider's terms, not by this project. See
[ASSET_LICENSES.md](ASSET_LICENSES.md#speech-you-generate). Never clone a real person's voice
without their written consent.
