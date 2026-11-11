# Glossary

Words used in these docs, in plain language.

| Term | Meaning |
|---|---|
| **Project** | A folder with a `studio.yaml` file and `scenes/`. One project makes one film per language. |
| **Template** | A starting project you copy with `sastudio init`: `starter`, `short` or `education`. |
| **Scene** | One short story with one lesson. A film is a list of scenes. |
| **Line** | One thing a character says, or one card of text, inside a scene. |
| **Card** | Text shown full screen for a few seconds, with no voice. |
| **Key point** | The card at the end of a scene that repeats its lesson (the scene's `takeaway`). |
| **Headline** | The one-line lesson shown at the top of the screen while a scene plays. |
| **Id** | A stable name for a character, scene or line, used inside the project and never shown. Renaming changes the display name, not the id. |
| **Display name** | What viewers read in subtitles and labels. |
| **Spoken name** | What a voice says. It can differ from the display name, for example in Devanagari for Hindi voices. |
| **Token** | A placeholder in dialogue, such as `{leo}` or `{org.security_email}`, filled in when the film is built. |
| **Lexicon** | A list of words and how voices should say them (`speech.lexicon`). |
| **Provider** | A service or program that turns text into speech: `offline`, `sarvam` or `elevenlabs`. |
| **Placeholder voice** | Free offline speech (espeak-ng or timed silence) used to check a film before paying for real voices. |
| **TTS** | Text-to-speech. |
| **Live generation** | Sending lines to a paid provider. Needs `--live` and a character budget. |
| **Budget** | The most characters (and requests) a live run may send. |
| **Cache** | Stored results reused when nothing that affects them changed: generated speech, prepared lines, scene videos. |
| **Ledger** | `.studio/ledger.jsonl`: a record of every speech request, for checking what was sent and billed. |
| **Renderer** | The part that draws the pictures. `cards` draws captioned cards with talking figures; `clay` films sculpted characters in Blender (`sastudio film`). |
| **Preset** | A quality level: `draft` (960 x 540), `preview` (1280 x 720), `final` (1920 x 1080). |
| **Frame** | One still picture of the film. Films here run at 24 frames per second. |
| **Beat** | One timed piece of a scene: the title, a line, a card or the key point. |
| **Timeline** | A scene's beats laid out frame by frame, with the audio placed against them. |
| **Mux** | Combining the video and the audio into one file. |
| **CRF** | The x264 quality setting. Lower is better quality and a bigger file. |
| **LUFS** | A loudness measure. Films are levelled to -16 LUFS so they play at a comfortable volume. |
| **dBTP** | True-peak level. A ceiling of -1.5 dBTP prevents distortion after compression. |
| **SRT / WebVTT** | The two common subtitle file formats. Both are written for every film. |
| **Burned-in subtitles** | Subtitles drawn into the picture, so they show in every player but can't be turned off. |
| **Transcript** | A plain-text file of everything said, with speaker names. |
| **Manifest** | `manifest.json`: what was built, how long it is, its loudness and checksums. |
| **Incremental render** | Rendering only the scenes whose content changed. |
| **Checksum (SHA-256)** | A fingerprint of a file. If one byte changes, the checksum changes. |
| **Schema** | The rules a `studio.yaml` must follow. `schema_version: 1` is the current format. |
| **Policy note** | A reminder inside a scene that its procedure is a sample to be replaced by your real one. |
