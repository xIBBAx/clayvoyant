# Characters

## The cast

| | Id | Role | Look |
|---|---|---|---|
| <img src="media/characters/mira.png" width="90" alt="Mira, a clay figure with a dark bob and a teal blazer"> | `mira` | Security lead. Calm, dry, kind. | Dark bob, teal blazer |
| <img src="media/characters/leo.png" width="90" alt="Leo, a clay figure with side-swept hair and a terracotta jacket"> | `leo` | New starter. Enthusiastic, too trusting, learns fast. | Side-swept hair, terracotta jacket, white sneakers |
| <img src="media/characters/aarav.png" width="90" alt="Aarav, a clay figure with round glasses and a navy jacket"> | `aarav` | Finance. Careful, deadpan. | Short curls, round glasses, navy jacket |
| <img src="media/characters/nadia.png" width="90" alt="Nadia, a clay figure with a low bun and a plum jacket"> | `nadia` | Operations manager. Busy, brisk. | Low bun, plum jacket |
| <img src="media/characters/rook.png" width="90" alt="Rook, a clay figure in a charcoal suit with swept-back hair"> | `rook` | The impersonator. Charming, never who they say. | Swept-back hair, charcoal suit |

All five were designed for this project.

## What you can change, and how hard it is

| Change | How | Re-voices? | Re-renders |
|---|---|---|---|
| A character's **name** | `name:` in studio.yaml | Only lines that say the name | Scenes that show it |
| How the name is **said** | `spoken:` or `pronunciation:` | Lines that say it | Those scenes |
| **Pronouns / grammar** | `pronouns:`, `gender:` | Lines that use them | Those scenes |
| **Voice** | `voice:` | That character's lines | Their scenes |
| **Portrait** | `look.portrait:` any PNG with a transparent background | No | Scenes they appear in |
| **Add a character** | add to `characters:`, then describe them (`look.design`) or give them a portrait, and lines | Their lines | Their scenes |
| **Remove a character** | delete them and their lines | | `validate` lists every line that still uses them |
| **Style** of every character, or of one | `render.character_style:` or `look.style:` (v1-v4, below) | No | All scenes, or theirs |
| **Appearance** in the drawn styles: hair, skin, outfit, shoes, glasses... | `look.design:` (below) | No | Scenes they appear in |
| **New 3D clay characters** | needs the clay renderer, which is **not included in this release** | | |

Ids never change when names do. That is what keeps renames safe. The worked example in
[examples/quillmere](../examples/quillmere/) renames `leo` to Kabir in English and Hindi without
touching a scene file.

A new character needs either a design (below: no drawing skills, no files) or a portrait. Any PNG
with a transparent background works as a portrait: an illustration,
a photo cut-out you have the rights to, or a render from your own 3D tool. Keep the proportions of
the bundled portraits (a full standing figure about 3 times taller than wide) so the layout
matches. Without a portrait, the cards renderer draws a plain silhouette in one colour with the
character's initials.

## Four styles

<img src="media/characters/styles.png" width="100%" alt="The five characters in four styles, one row each: v1 sketch with graphite outlines and hatching on a light wash; v2 flat with clean flat colour and one shadow per shape; v3 cut-out with layered paper pieces, white cut edges and soft shadows; v4 clay, the 3D clay portraits.">

| Style | Name | Looks like | Moves |
|---|---|---|---|
| `v1` | `sketch` | graphite outlines over a light wash, hatched shadows: a storyboard page | the speaker talks and blinks |
| `v2` | `flat` | clean flat colour, one shadow per shape: an explainer video | the speaker talks and blinks |
| `v3` | `cutout` | layered paper with cut edges, cast shadows and grain: paper stop-motion | the speaker talks and blinks |
| `v4` | `clay` | the bundled 3D clay portraits (the default) | no: still portraits |

Choose one for the whole film, and override it for any character:

```yaml
render:
  character_style: v3          # or: sketch, flat, cutout, clay
characters:
  - id: rook
    look: { preset: rook, style: v1 }   # Rook alone in sketch style
```

See your cast in every style before you render: `sastudio characters my-film --sheet cast.png`
(add `--styles v1,v3` to choose).

The drawn styles (v1-v3) are drawn by this tool, from scratch, every time: there are no image files
to download or license. The speaking character's mouth follows the voice (its loudness, or the
letters of the subtitle when the voice is the silent placeholder) and their eyes blink, changing
12 times a second like stop-motion animation. Bodies do not move and the cards still cut from one
to the next. Drawing is deterministic: the same design always gives the same pixels, and each
figure is drawn once and kept in `.studio/work/figures`.

## Describe your own character

A design is a few words in `studio.yaml`; anything you leave out comes from the character's
`preset` (one of the five) or a neutral default.

```yaml
  - id: priya
    name: Priya
    role: Branch manager
    look:
      design:
        skin: "#A8704C"
        hair: { style: bun, color: "#16100E" }
        outfit: { style: kurta, color: "#8E2F4B", shirt: "#F3D9A4" }
        trousers: "#2C3440"
        shoes: { style: flat, color: "#3A2C24" }
        extras: [bindi, earrings]
```

| Field | Choices |
|---|---|
| `skin`, `eyes`, `lip`, `blush`, `trousers` | any colour as `#RRGGBB` |
| `hair.style` | `short`, `side_sweep`, `swept_back`, `curls`, `bob`, `bun`, `long`, `ponytail`, `headscarf`, `bald` (with `hair.color`; for `headscarf` it is the scarf's colour) |
| `outfit.style` | `blazer`, `suit`, `jacket`, `shirt`, `sweater`, `kurta` (with `outfit.color` and `outfit.shirt`) |
| `shoes.style` | `flat`, `sneaker`, `brogue`, `heel`, `boot` (with `shoes.color`) |
| `extras` | any of `glasses`, `necklace`, `lapel_pin`, `freckles`, `earrings`, `beard`, `moustache`, `bindi` |

A character with a design but no portrait is drawn in `v2` flat even when the film's style is clay.

## About the five clay portraits

The portraits are renders of five clay-style characters, sculpted procedurally from the
parameter files in `src/sastudio/engine/characters/` (face proportions, hair, glasses, garment,
colours). The sculpting and puppet engine that made them is **not included in this release**, so
in clay the characters exist as these images and those parameter files. They are
deliberately simple: full-length figures with mitten-like hands, made to read clearly at small
sizes beside dialogue, not as detailed character art.

When a release includes the clay renderer, the parameter files are what it builds the characters
from, and `look.preset` and `look.colors` select and recolour them. Today `look.preset` also picks
the bundled design for the drawn styles, and `look.colors` is accepted and ignored.

## Likeness and rights

All five were designed for this project and are not based on real people. If you add
characters, do not use a real person's likeness without their written consent, and record the
licence of every image you add in [ASSET_LICENSES.md](../ASSET_LICENSES.md).
