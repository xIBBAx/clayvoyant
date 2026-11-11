# Direction: cameras, light, acting and transitions

Every scene can be directed in its YAML. `sastudio direct` plans and checks that direction and
prints the shot list; `sastudio film` films it in clay ([CLAY_MOTION.md](CLAY_MOTION.md));
`sastudio motion` films one scene or shot without voices, to look at the direction quickly. The
cards films made by `sastudio render` do not use cameras, light or gestures. Projects without any
direction are directed automatically.

## You don't have to write anything

Every scene is directed automatically. Read the plan, with the reason for each choice:

```bash
sastudio direct my-film --scenes helpful_caller
```

```text
helpful_caller: office set, office light (4500 K), enters by cut
   1. medium            40 mm  static     9.6 s  on rook       lines hc_01  (straight into the conversation)
   2. wide              28 mm  static     5.4 s  on rook, leo… lines hc_02,hc_03  (leo joins the conversation: seen in context)
   ...
   8. close_up          65 mm  push_in    6.9 s  on mira       lines hc_09  (the scene's last word: closer)
```

The automatic plan follows ordinary film grammar: every scene opens on a filmed shot of its place
with the title over it; the first line in a new place shows everyone in it, and a return to a known
place opens differently each time; someone joining a conversation is seen in
context; a question is seen past the listener's shoulder and its answer closer; the last word of a
scene gets a slow push in; the same framing is never cut to itself (a jump cut); held shots are
cut after about 12 seconds; and each character keeps their side of the screen.

## Change one thing

On a line:

```yaml
  - id: hc_07
    who: rook
    say: "Ah. Bad line. Breaking up. Never mind."
    camera: extreme_close_up       # any camera below
    act: [phone_to_ear]             # gestures, up to four
    emotion: embarrassed            # how the speaker feels (the list is below)
    to: leo                         # who they are talking to: their eyeline
    go: standing_right              # a mark they walk to as the line begins (they sit if it is a seat)
    reactions: { leo: surprised }   # how listeners take it
```

On a scene:

```yaml
id: helpful_caller
direction:
  set: office                       # where it happens
  lighting: suspense                # how it is lit
  open_with: close_up               # how the scene begins
  transition_in: cut                # how we arrive from the previous scene
  object: phone                     # for follow_object: the thing the scene opens on
  extras: [nadia]                   # in the scene without a line
  blocking: { leo: desk, aarav: standing_right }   # where people are (a seat mark: they are sitting)
  business: { leo: typing }         # what someone is busy with as the scene opens
```

Anyone without a place in `blocking` is given a standing spot, and keeps their side of the screen.

## Full control

List the shots yourself. Lines you don't put in a shot are still directed automatically.

```yaml
direction:
  shots:
    - { lines: [hc_01], camera: close_up, who: rook, move: push_in, lens_mm: 85, fstop: 2.0 }
    - { lines: [hc_02, hc_03], camera: two_shot, who: [leo, aarav], focus: leo }
    - { lines: [hc_05], camera: over_shoulder, who: [aarav, leo], height: low, seconds: 11 }
    - { lines: [hc_08], camera: insert, who: phone }
```

To put the camera exactly where you want it, give a shot a `position` and an `aim` in set units
(`[x, y, z]`; x is screen right, y is away from the camera, z is up; a person is about 3.4 tall and
the acting area is around `[0, 0.5, 0]`):

```yaml
    - { lines: [hc_06], camera: medium, who: rook, position: [3.5, -4.0, 1.2], aim: [0.2, 0.6, 2.9] }
```

`who` is the character (or, for an `insert`, the prop) the shot shows; `focus` must be one of
them; `seconds` must be long enough for the dialogue; `lens_mm` (12-200), `fstop` (1.2-22) and
`height` (`eye`, `low`, `high`) override the camera's defaults. An `insert` on a prop is filmed:
the prop fills the frame and the line is heard over it.

### Cutting inside a line

An editor rarely holds one face for a whole long line. Give a line two shots, each with the `part`
of the line it covers, and the film cuts between them while the line plays on:

```yaml
    - { lines: [hc_04], camera: close_up, who: rook, part: [0, 0.6] }
    - { lines: [hc_04], camera: reaction, who: leo, part: [0.6, 1] }      # Leo hears the rest of it
```

The pieces of a line must run from 0 to 1 without gaps. The cut does not land on the exact
fraction: it moves to the nearest drawing, between 35 and 80 % of the line, where the speaker's
mouth is at rest (a pause, or lips closed on m, b or p), so it never chops a word.

You get this without writing it, too. When a line runs longer than about 3.4 seconds and its own
shot shows only the speaker, the automatic plan cuts to the listener 55-65 % of the way through,
and the next line by that listener opens a size wider. `sastudio direct` shows each cut as
`lines hc_04 0%-60%` and `60%-100%`. Turn it off for a scene with `direction: { reactions: false }`.
A short, sharp line (six words or fewer, ending in `!` or spoken surprised) gets an
`extreme_close_up`.

## What you can name

| Camera | Lens | Shows | Characters |
|---|---|---|---|
| `establishing` | 24 mm | the whole set | 0-6 |
| `wide` | 28 mm | full figures | 1-6 |
| `medium` | 40 mm | waist up | 1 |
| `two_shot` | 35 mm | two figures, waist up | 2 |
| `over_shoulder` | 50 mm | the speaker past the listener's shoulder (a two-shot, or a medium when a two-shot of the pair is next to it, if the listener stands behind the speaker) | 2 |
| `close_up` | 65 mm | head and shoulders | 1 |
| `extreme_close_up` | 100 mm | eyes and mouth | 1 |
| `reaction` | 65 mm | a listener's face while someone else speaks | 1 |
| `insert` | 85 mm | a prop: a phone screen, a laptop, a badge | a prop |

| Move | What it does |
|---|---|
| `static` | the camera holds still |
| `push_in` | a slow move closer, for a line that matters |
| `pull_out` | a slow move back, to end a moment |
| `pan` | the camera turns to follow someone |
| `tilt` | the camera tilts up or down |
| `track` | the camera travels alongside someone walking |
| `orbit` | a small arc around the subject |

| Lighting | Key light | Fill | Rim | Exposure | Shadows | Lamps lit |
|---|---|---|---|---|---|---|
| `warm_interior` | 3200 K | 0.45 | 0.30 | +0.0 | soft | yes |
| `soft_studio` | 5000 K | 0.70 | 0.20 | +0.2 | soft | no |
| `daylight` | 5600 K | 0.50 | 0.25 | +0.1 | medium | no |
| `office` | 4500 K | 0.60 | 0.15 | +0.0 | soft | no |
| `night_practical` | 2700 K | 0.15 | 0.50 | -0.7 | medium | yes |
| `dramatic` | 4300 K | 0.10 | 0.60 | -0.2 | hard | no |
| `suspense` | 3800 K | 0.20 | 0.45 | -0.4 | hard | yes |

Each lighting preset differs in colour temperature, contrast and shadow, so they look different
from one another.

| Gesture | Uses | Kind | Needs |
|---|---|---|---|
| `nod` | head | once |  |
| `shake_head` | head | once |  |
| `tilt_head` | head | once |  |
| `shrug` | left arm, right arm, shoulders | once |  |
| `point` | right arm | once |  |
| `wave` | right arm | once |  |
| `open_palms` | left arm, right arm | once |  |
| `thumbs_up` | right arm | once |  |
| `hand_on_chin` | right arm | hold |  |
| `arms_folded` | left arm, right arm | hold |  |
| `phone_to_ear` | right arm | hold | phone |
| `typing` | left arm, right arm | loop | laptop |
| `hold_mug` | right arm | hold | mug |
| `sip` | right arm | once | mug |
| `check_phone` | head, right arm | hold | phone |
| `lean_in` | torso | once |  |
| `turn_to` | head, torso | once |  |
| `sit_down` | legs, torso | once | a seat |
| `stand_up` | legs, torso | once | a seat |
| `walk_in` | legs, torso | once |  |
| `walk_out` | legs, torso | once |  |

Two gestures in one line may not use the same body part; a gesture that needs a prop or a seat
needs a set that has one. `sit_down` walks to the nearest free seat; `walk_in` enters through the
set's door (or from the side, where there is none) and arrives as the line begins; `typing` puts
the hands on the table of whoever is sitting at one; a mug or a phone appears in the hand that
holds it. A speaker with no gesture of their own talks with their hands, changing on the thought.

Emotions: `neutral`, `happy`, `worried`, `surprised`, `suspicious`, `confident`, `embarrassed`,
`relieved`, and the finer shades `grin`, `shock`, `sad`, `smug`, `deadpan`, `think`, `annoyed`,
`recognise`, `concern`, `hesitate`, `warm`, `wince`, `tender`. An emotion lasts until that
character is given another.

| Set | Marks (seats in italics) | Props | Door |
|---|---|---|---|
| `office` | *desk*, *desk_2*, standing_left, standing_right, window, door | laptop, laptop_2, phone, mug, badge, printer, plant, poster | yes |
| `reception` | counter, visitor, standing_left, standing_right, door | badge, badge_reader, phone, visitor_book, plant, poster, monitor | yes |
| `meeting_room` | *head_of_table*, *left_seat*, *right_seat*, screen, door | laptop, phone, mug, screen, poster | yes |
| `home_desk` | *desk*, *sofa*, window | laptop, phone, mug, plant, router | no |
| `cafe` | *table_left*, *table_right*, *table_left_2*, *table_right_2*, counter, door | laptop, phone, mug, wifi_sign | yes |
| `corridor` | left, centre, right, door | badge, phone, poster, badge_reader | yes |
| `street` | pavement_left, pavement_right, *bench*, bus_stop, shop_door, far_left, far_right | phone, car, bus_stop | no |
| `classroom` | teacher, board, *teacher_desk*, *front_desk_left*, *front_desk_right*, standing_left, standing_right, door | board, laptop, map, phone | yes |
| `studio` | centre | | no |

A scene's `setting.time_of_day` (`morning`, `day`, `evening`, `night`) sets the sky, the sun and
the lamps of any set.

| Transition | How the scene opens |
|---|---|
| `cut` | on the whole place, the camera drifting in (the default) |
| `match_cut` | close on the first speaker's face, easing back |
| `follow_object` | close on a named thing of the set, then back to show the room (needs `object`) |
| `door_reveal` | on the set's door as it opens (the set needs a door) |
| `fade_from_black` | up from black; only to open the film, or after a jump in time (`time_jump: true`) |

The opening shot carries the scene's title and lasts as long as a title card would. There are no
decorative wipes or spins: a scene arrives by a cut onto something that is happening.

## When something can't be filmed

Nothing is silently ignored. `sastudio validate` and `sastudio direct` stop with the reason and,
when there is one, the closest valid name:

```text
[error] helpful_caller.direction.lighting: Unknown lighting 'warm_interor'.
    Did you mean warm_interior? Choose from: daylight, dramatic, night_practical, office, soft_studio, suspense, warm_interior.
[error] helpful_caller.hc_07.act: 'phone_to_ear' and 'typing' both need the right arm.
    Give them to different lines.
[error] helpful_caller.direction.shots[2].seconds: The dialogue in this shot needs about 10.0 s, longer than 6 s.
    Lengthen the shot or split the lines.
```
