# Roadmap

What exists today, and what could come next, ranked by how much it would help someone making a
training film. Nothing below the first table is promised or scheduled.

## In 0.1

| Area | Status |
|---|---|
| Project format with schema validation, stable ids and migrations | done (format version 1) |
| Organisation branding, terms, reporting address, intro and closing cards | done |
| Character names, pronouns, gendered grammar, per-language names and spoken forms | done |
| Scenes: enable/disable, dependencies, translations, key-point cards, time limits | done |
| Voices: offline, Sarvam, ElevenLabs, with cache, budgets, ledger and pronunciation export | done; paid providers tested against recorded responses only |
| Cards renderer, three presets, incremental rendering, SRT/WebVTT/transcript/manifest | done |
| Clay renderer (animated 3D puppets) | not included in this release |

## Next, by value to users

1. **A live check for each voice provider.** An opt-in test that sends one short line with a tiny
   budget, so users can confirm their key and voice before a full run.
2. **Translations of the remaining starter scenes** into Hindi (two are translated today) and other
   Indian languages, each reviewed by a fluent speaker.
3. **Pre-render preview.** A fast text-and-timing report (or contact sheet) of every scene, to check
   names, wording and timing before a full render.
4. **Cost estimate in one command,** combining character counts, your own price table and render
   time measured on your machine.
5. **More scene templates** for topics the starter does not cover, written to the same rules:
   generic, no invented policy, every procedure marked for the organisation to replace.
6. **Accessibility exports:** audio description track, and a check for subtitle reading speed per
   language.
7. **The clay renderer,** if and when it can be released.
8. **Optional assessment material** (a short question bank per scene), clearly marked as practice,
   never as a pass mark.
9. **A simple graphical editor** for `studio.yaml`, only if it can stay small and keyboard-accessible.

Suggestions and contributions are welcome; see [CONTRIBUTING.md](../CONTRIBUTING.md).
