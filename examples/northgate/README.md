# Example: Northgate Logistics

A complete, three-scene project that customises the starter material for one organisation
(The Too-Good Email, One Password, Everywhere and Report Early, in English and Hindi). Northgate
Logistics is invented, and its addresses use the reserved `.example` domain, so they can never
reach a real company.

Every change from the starter template is marked `CHANGED` in [studio.yaml](studio.yaml):

| Change | Where |
|---|---|
| Organisation name, short name, team names | `organization` |
| Security reporting email and reporting form | `organization.security_email`, `organization.reporting_url` |
| Logo and brand colours | `organization.logo` (drawn by `tools/make_example_assets.py`), `organization.palette` |
| The organisation's own words ("the depot", "site pass") | `organization.terms` |
| A character renamed: `leo` is now **Kabir**, in English and Hindi | `characters[leo].name`, `forms`, `spoken` |
| A pronunciation hint for one provider | `characters[leo].pronunciation.elevenlabs` |
| A different voice speed for the Hindi film | `characters[leo].voice.languages.hi-IN` |
| A character removed (Rook is not in these scenes) | `characters` |
| A line of dialogue changed to mention the reporting form | `scenes/11_report_early.yaml`, line `re_10` |
| Two languages, with Hindi topic names on the title cards | `project.languages`, `project.labels.topics` |
| How a word is spoken ("Northgate" as "North gate") | `speech.lexicon` |
| Output: fast draft preset, speaker names in the `.srt` file | `render` |

## Run it

From the repository root, copy the example so your renders stay out of the repository:

```bash
cp -r examples/northgate ~/northgate-film          # Windows: xcopy /E /I examples\northgate %USERPROFILE%\northgate-film
sastudio validate ~/northgate-film
sastudio script ~/northgate-film --lang hi-IN --scenes report_early
sastudio render ~/northgate-film                    # English, 960x540
sastudio render ~/northgate-film --lang hi-IN       # Hindi
```

Each language takes well under a minute on the machine described in
[REQUIREMENTS.md](../../docs/REQUIREMENTS.md). The voices are the free offline placeholder; to use
Sarvam or ElevenLabs, follow the comment on Kabir's `voice:` and
[VOICE_PROVIDERS.md](../../docs/VOICE_PROVIDERS.md).

The Hindi lines come from the starter's `short` template. As with any translation, have a fluent
speaker review them before you use the film.
