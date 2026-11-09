# Scenes

A film is a list of scenes. Each scene is one short story with one lesson: a title, some
dialogue, and an optional key-point card at the end. Scenes live in `scenes/*.yaml` and are listed,
in order, in `studio.yaml`:

```yaml
scenes:
  - file: scenes/01_first_day.yaml
  - file: scenes/02_too_good_email.yaml
```

A scene can also be written inline in that list instead of in its own file.

```bash
sastudio scenes my-film                              # on/off, id, spoken lines, title, dependencies
sastudio script my-film --scenes too_good_email      # what will be shown, and what each voice will say
sastudio validate my-film                            # check everything before rendering
sastudio render my-film --scenes too_good_email      # render just this scene
```

## A scene file

```yaml
id: too_good_email                  # stable id: lower case letters, digits, underscores
title: The Too-Good Email
title_translations: { hi-IN: "बहुत अच्छा email" }
topic: phishing                     # shown on the scene's title card
summary: Leo gets an email that is very keen to give him a prize.   # for you; not shown
headline: Pause before you click    # shown at the top while the scene plays
headline_translations: { hi-IN: "Click से पहले रुकिए" }
setting: { backdrop: office, time_of_day: day }    # descriptive; add image: for a backdrop picture
policy_note: "Sample wording. Tell people exactly how to report a suspicious email in your organisation."
lines:
  - id: te_01
    who: leo
    say: "{aarav}! I've won a tablet. All I have to do is confirm my login in the next ten minutes."
    translations: { hi-IN: "{aarav}! मैंने tablet जीता है। बस अगले दस मिनट में login confirm करना है।" }
  - id: te_07
    who: mira
    say: "Three warning signs in one email: a reward you didn't expect, a countdown, and a link that goes somewhere else."
takeaway: "Unexpected rewards, countdowns and odd links are warning signs. Report the email to {org.security_team}."
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable id. Other scenes and `--scenes` use it. Never shown. |
| `title`, `title_translations` | yes | Scene title (title card, chapter label). |
| `lines` | yes | Dialogue and cards, in order (below). |
| `topic` | no | One short word or phrase, shown on the title card. Change how it reads per language in `project.labels.topics`. |
| `headline`, `headline_translations` | no | One-line lesson shown at the top during the scene. |
| `takeaway`, `takeaway_translations` | no | A "Key point" card after the dialogue. |
| `summary` | no | A note for authors. Not shown. |
| `enabled` | no | `false` leaves the scene out of every build. |
| `requires` | no | Scenes this one builds on (below). |
| `setting.image` | no | A backdrop picture inside the project folder (PNG, JPG, WebP). |
| `setting.backdrop`, `setting.time_of_day` | no | Descriptive labels for authors. The cards renderer does not draw them. |
| `policy_note` | no | A reminder that the wording is a sample and must match your real procedure. Not shown. |
| `max_seconds` | no | The build stops with an error if the scene runs longer, so a re-voiced line can't silently overrun a time slot. |

## Lines

Every line has a project-wide unique `id`. Cached audio is stored per line, so keep ids stable
when you edit text.

**Spoken line**

```yaml
- id: re_10
  who: mira                          # a character id
  say: "Especially then. Write to {org.security_email}."
  translations: { hi-IN: "तब तो और भी। {org.security_email} पर लिखिए।" }
  spoken: { en-IN: "Especially then. Write to security at quillmere dot example." }   # optional exact speech text
  pause_after: 0.6                   # seconds of silence after the line (default: speech.gap_seconds)
  to: leo                            # optional: who is addressed (checked by validate)
```

`emotion` is accepted and stored, but no provider receives it in 0.1. To change delivery, use the
provider's own voice settings ([VOICE_PROVIDERS.md](VOICE_PROVIDERS.md)).

**Card** (text on screen, no voice)

```yaml
- id: pw_07
  card: { text: "New sign-in request. Approve?", seconds: 2.5, translations: { hi-IN: "नया sign-in request. Approve करें?" } }
```

## Names, pronouns and your organisation: tokens

Dialogue never contains a character's name or your organisation's details as plain text. It
contains a token, which is resolved when the film is built. That is what makes renaming safe.

| Token | Becomes |
|---|---|
| `{leo}` | the character's display name ("Leo", or "Kabir" after a rename) |
| `{leo.full_name}`, `{leo.formal}` | any form you defined in the character's `forms` |
| `{leo.they}` `{leo.them}` `{leo.their}` `{leo.theirs}` `{leo.themself}` | pronouns from `pronouns:`; `{leo.They}` capitalises |
| `{leo.gender?feminine=गई|masculine=गया|other=गए}` | choose text by the character's `gender`, for gendered grammar |
| `{org.name}` `{org.short_name}` `{org.security_email}` `{org.reporting_url}` `{org.security_team}` `{org.it_team}` `{org.training_title}` | organisation fields |
| `{org.people}`, `{org.laptop}`, ... | any word you defined in `organization.terms` |
| `{{` and `}}` | literal braces |

Each token is resolved twice: once for what people read (subtitles, cards, transcript) and once
for what the voice says (spoken names, pronunciation hints, an email address read out as words).

`sastudio validate` reports unknown tokens in every language, and lines that type a character's
name as plain text instead of using its token.

## Translations

List languages in `project.languages`. Each one becomes a separate film. For every language other
than `project.language`, a line needs `translations: { <lang>: ... }`, and titles, headlines and
takeaways need their `*_translations`. A missing translation is an error, unless
`project.missing_translation: fallback` is set, in which case the main language is used for that
line.

Translations must be checked by a fluent speaker before use. Gendered languages may need the
`{id.gender?...}` form or a per-language `spoken` override.

## Dependencies between scenes

```yaml
id: report_early
requires: [too_good_email]          # this scene refers back to the tablet email
```

`validate` and `render` stop with an error when a required scene is unknown, turned off, left out
by `--scenes`, or placed later in the film. Fix it by turning the required scene back on, turning
this one off, or rewriting this scene so it stands alone and removing the `requires` entry.

## Shorter films and modules

- Turn scenes off with `enabled: false`, or remove them from the `scenes:` list.
- `sastudio init my-short --template short` starts from 3 scenes in English and Hindi.
- `sastudio init my-course --template education` is the full set with one finance scene off.
- `--scenes a,b,c` renders a module from any subset, without the intro and closing cards.

## Writing good sample content

The starter scenes are general awareness material, not policy. Before you use them:

- Replace every procedure with your organisation's real one: how to report, who to call, which
  tool to use. `policy_note` marks the lines that most need this.
- Do not invent deadlines, pass marks, legal duties or certification claims.
- Keep each scene to one lesson, with the lesson said out loud by a character and repeated on the
  key-point card.

The 12 starter scenes cover: introduction, phishing, passwords and MFA, phone impersonation,
payment fraud, clear desk and tailgating, removable media, remote work, data handling, AI tools,
incident reporting, and a closing scene.
