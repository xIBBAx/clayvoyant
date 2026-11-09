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
| **Add a character** | add to `characters:`, give them a portrait and lines | Their lines | Their scenes |
| **Remove a character** | delete them and their lines | | `validate` lists every line that still uses them |
| **Appearance, outfit colours, new 3D characters** | needs the clay renderer, which is **not included in this release** | | |

Ids never change when names do. That is what keeps renames safe. The worked example in
[examples/northgate](../examples/northgate/) renames `leo` to Kabir in English and Hindi without
touching a scene file.

A new character needs a portrait. Any PNG with a transparent background works: an illustration,
a photo cut-out you have the rights to, or a render from your own 3D tool. Keep the proportions of
the bundled portraits (a full standing figure about 3 times taller than wide) so the layout
matches. Without a portrait, the cards renderer draws a plain silhouette in one colour with the
character's initials.

## About the five portraits

The portraits are renders of five clay-style characters, sculpted procedurally from the
parameter files in `src/sastudio/engine/characters/` (face proportions, hair, glasses, garment,
colours). The sculpting and puppet engine that made them is **not included in release 0.1**, so in
this release the characters exist as these images and those parameter files. They are
deliberately simple: full-length figures with mitten-like hands, made to read clearly at small
sizes beside dialogue, not as detailed character art.

When a release includes the clay renderer, the parameter files are what it builds the characters
from, and `look.preset` and `look.colors` select and recolour them. In 0.1 those two fields are
accepted and ignored by the cards renderer.

## Likeness and rights

All five were designed for this project and are not based on real people. If you add
characters, do not use a real person's likeness without their written consent, and record the
licence of every image you add in [ASSET_LICENSES.md](../ASSET_LICENSES.md).
