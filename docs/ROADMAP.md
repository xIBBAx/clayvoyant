# Roadmap

What exists today, and what could come next, ranked by how much it would help the people who make
and watch these films: teachers, small teams and nonprofits without an animation budget, learners
on slow connections, and viewers who rely on captions, screen readers or larger text. Nothing below
the first table is promised or scheduled. Each item says how we would know it worked.

## In 0.1

| Area | Status |
|---|---|
| Project format with schema validation, stable ids and migrations | done (format version 1) |
| Organisation branding, terms, reporting address, intro and closing cards | done |
| Character names, pronouns, gendered grammar, per-language names and spoken forms | done |
| Scenes: enable/disable, dependencies, translations, key-point cards, time limits | done |
| Voices: offline, Sarvam, ElevenLabs, with cache, budgets, ledger and pronunciation export | done; paid providers tested against recorded responses only |
| Cards renderer, three presets, incremental rendering, SRT/WebVTT/transcript/manifest | done |
| Byte-for-byte reproducible renders on one toolchain | measured: the same project, version and FFmpeg build give the same file hash |
| Character styles: v1 sketch, v2 flat, v3 cut-out (drawn), v4 clay (portraits) | done in 0.2; characters can be described in text |
| Character animation | 0.2: in the drawn styles the speaker talks and blinks; no body animation |
| Clay films (sculpted characters, sets, cameras, acting, lip sync) | released: `sastudio film` ([CLAY_MOTION.md](CLAY_MOTION.md)) |

What the 0.1 films are, measured on the reference film: 94 % of the running time is still frames
(illustrated cards with hard cuts), and the offline placeholder voice is silent.

## 0.2 — make the film safer to ship and easier to reach

**1. Catch a placeholder reporting address before it reaches a film.** *(Implemented for the next
version; see the changelog.)* Every template ships
`security@example.com`, and today `validate --strict` reports nothing about it, so a first film can
tell a whole organisation to report incidents to an address that does not exist. A finished video
cannot be patched. `validate` should warn when the reporting email or URL uses a reserved example
domain (RFC 2606 / 6761), and a `final` render should refuse it unless the project says it is a
demo. *Done when:* a fresh `init` → `render --preset final` stops with a clear message; the
examples still render with an explicit demo flag; tests cover email, URL and every template.

**2. An accessible lesson export, made from the same timeline.** The films are cards, so nearly
all of their content is text and a few portraits. A proposed lesson export would write one
self-contained HTML page per film with real text instead of burned-in pixels: readable by
screen readers, zoomable to 200 % without loss (WCAG 2.2 1.4.4), keyboard-navigable scene by
scene, honouring reduced-motion settings, printable as a handout, and small enough to share over a
poor connection or a messaging app. No tracking and no scripts from elsewhere. *Done when:* the
starter exports to one folder, works offline, has zero automated accessibility violations (axe)
in CI, and its size is measured and published against the MP4.

**3. Reviewed guidance, not sample guidance.** Scenes already mark the lines an organisation must
replace with `policy_note`. Today nothing stops a `final` film from shipping those sample
procedures unchanged. An optional `review:` list in `studio.yaml` would record that each marked
line was checked (by role or initials, with a date and a hash of the resolved text, so editing the
line invalidates the review). A `final` render with unreviewed lines would show a visible "sample
guidance" badge on them and list them in the manifest. *Done when:* changing a reviewed line
re-flags it; the manifest lists review status per line; no personal data is required.

**4. Facilitator mode for shared screens.** Many sessions happen in a room around one projector,
not on individual laptops. An optional `discuss:` question per scene would add a pause card after
the scene and a printable facilitator guide (key points, questions, your real procedure), with no
quiz scores and no learner data. *Done when:* the starter ships questions for every scene and the
guide prints on A4/Letter.

**5. A live check for each voice provider.** An opt-in command that sends one short line with a
tiny budget, so users can confirm their key and voice before a full run. *Done when:* it refuses to
run without `--live` and a budget, and its cost appears in the ledger.

## Found while preparing 0.2

**A. Free voices worth hearing.** Without a paid account a film is silent, or robotic with
espeak-ng: every reference film is digital silence. An optional offline neural voice provider
(for example Piper) would make the free path watchable. Each voice model has its own licence and
some are non-commercial, so only voices whose licence allows redistribution and commercial use
would be listed, and Indian-language quality must be checked by fluent listeners first. *Done
when:* a fresh project renders an audible English film offline, with each voice's licence shown
by `doctor`.

**B. Posters from the same project.** Many trainings happen without a screen. The key-point cards
the renderer already draws could be exported as A4 or Letter posters (PNG and PDF) for notice
boards, in every language of the project. *Done when:* the starter prints twelve posters that pass
the same contrast checks as the film.

**C. Vertical clips for messaging apps.** Small organisations often share video through messaging
apps on phones. One short 9:16 clip per scene, with large subtitles, would fit how such films are
actually passed around. *Done when:* each starter scene exports as a vertical clip under 16 MB.

**D. Speaker close-ups.** In the full-frame layout the talking face is small. Occasional close-up
framing of the speaker, in the drawn styles, would make the speech readable on phones.

## 0.3 — languages and verification

**6. Translations and pronunciation review.** Translate the remaining starter scenes into Hindi
and other Indian languages, each reviewed by a fluent speaker and marked as reviewed in the
project, plus a report that lines up each line's source text, translation, spoken form and
subtitle so a reviewer can check all four at once. Machine translation may help draft; it is never
marked reviewed by itself.

**7. Provenance you can check.** The manifest already holds checksums. Recording the hashes of every
input (project files, portraits, fonts, package version, FFmpeg build) would let an organisation
prove which reviewed script a film came from, and a proposed verify command could re-render and
compare.
This matters for security training in particular: a tampered copy with a different "report to"
address is an attack worth detecting. *Done when:* a re-render on the recorded toolchain matches
the recorded hash, and any edited input is named in the mismatch report.

**8. Change impact before rendering.** Show which lines need new speech, which scenes re-render,
how many paid characters that is and an estimate from your own price table, before anything runs.

**9. More scene templates** for topics the starter does not cover, written to the same rules:
generic, no invented policy, every procedure marked for the organisation to replace, each with a
stated learning objective.

## Towards richer animation

The project's timeline is already independent of the renderer: every line has a speaker, exact
frame range, display and spoken text, and (when a voice provides it) timing. Richer motion builds
on that contract rather than on any particular engine.

1. **Motion on cards.** *(Started in 0.2: drawn characters talk and blink.)* Next: speaker close-ups
   (the face is small in the full-frame layout), listeners' reactions, simple gestures, text
   reveals, and a reduced-motion preset.
2. **Layered 2D characters.** *(0.2 draws its own from a text description.)* Next: a documented
   portrait format split into layers (body, head, eyes, a mouth set), supplied by the user as PNGs, with mouth shapes driven by a lip-sync tool or
   the voice provider's timings. Anyone can draw a character for it; no 3D software needed.
3. **A renderer plug-in interface (0.4).** A small, versioned contract (timeline in, frames out)
   with contract tests, so independently written 2D or 3D back ends can ship as separate packages.
4. **Clay films: more of everything.** The clay renderer is released ([CLAY_MOTION.md](CLAY_MOTION.md)).
   Next for it: sound effects, ambience and music beds placed by the direction (footsteps are already
   timed by the engine); more props to hold and use; more sets and a way to describe your own in
   YAML; background people; weather; short sleeves, skirts and more garments; fingers on imported
   models; rendering on a remote machine; a visual editor for blocking and cameras.

## Not planned

Learner tracking, phishing-simulation sending, collecting anyone's credentials or personal data,
and anything presented as a compliance certificate.

Suggestions and contributions are welcome; see [CONTRIBUTING.md](../CONTRIBUTING.md).
