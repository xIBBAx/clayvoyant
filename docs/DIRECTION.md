# Direction: cameras, light, acting and transitions

**What works today.** Every scene can be directed in its YAML, and `sastudio direct` plans and
checks that direction and prints the shot list. The film itself is still rendered by the cards
renderer, which does not use cameras, light or gestures. The clay-motion renderer that will film
this plan is in development ([CLAY_MOTION.md](CLAY_MOTION.md)). Writing direction now is safe:
it is validated today and filmed later, and projects without direction keep working unchanged.

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

The automatic plan follows ordinary film grammar: a new place opens with an establishing shot and
a return to a known place opens differently each time; someone joining a conversation is seen in
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
    emotion: embarrassed            # neutral, happy, worried, surprised, suspicious, confident, embarrassed, relieved
    to: leo                         # who they are talking to: their eyeline
```

On a scene:

```yaml
id: helpful_caller
direction:
  set: office                       # where it happens
  lighting: suspense                # how it is lit
  open_with: close_up               # how the scene begins
  transition_in: cut                # how we arrive from the previous scene
  extras: [nadia]                   # in the scene without a line
  blocking: { leo: desk, aarav: standing_right }   # where people are
```

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

`who` is the character (or, for an `insert`, the prop) the shot shows; `focus` must be one of
them; `seconds` must be long enough for the dialogue; `lens_mm` (12-200), `fstop` (1.2-22) and
`height` (`eye`, `low`, `high`) override the camera's defaults.

## What you can name

| Camera | Lens | Shows | Characters |
|---|---|---|---|
| `establishing` | 24 mm | the whole set | 0-6 |
| `wide` | 28 mm | full figures | 1-6 |
| `medium` | 40 mm | waist up | 1 |
| `two_shot` | 35 mm | two figures, waist up | 2 |
| `over_shoulder` | 50 mm | the speaker past the listener's shoulder | 2 |
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
| `phone_to_ear` | left arm | hold | phone |
| `typing` | left arm, right arm | loop | laptop |
| `lean_in` | torso | once |  |
| `turn_to` | head, torso | once |  |
| `sit_down` | legs, torso | once | a seat |
| `stand_up` | legs, torso | once | a seat |
| `walk_in` | legs, torso | once |  |
| `walk_out` | legs, torso | once |  |

Two gestures in one line may not use the same body part; a gesture that needs a prop or a seat
needs a set that has one.

| Set | Marks | Props | Door |
|---|---|---|---|
| `office` | desk, desk_2, standing_left, standing_right, window, door | laptop, phone, mug, badge, printer, plant, poster | yes |
| `reception` | counter, visitor, standing_left, standing_right, door | badge, phone, visitor_book, plant, poster | yes |
| `meeting_room` | head_of_table, left_seat, right_seat, screen, door | laptop, phone, mug, screen, poster | yes |
| `home_desk` | desk, sofa, window | laptop, phone, mug, plant, router | no |
| `cafe` | table_left, table_right, counter, door | laptop, phone, mug, wifi_sign | yes |
| `corridor` | left, centre, right, door | badge, phone, poster, badge_reader | yes |

| Transition | When |
|---|---|
| `cut` | a clean cut (the default) |
| `match_cut` | a cut that matches a shape or movement across the two shots |
| `follow_object` | the camera follows a named object into the new scene (needs `object`) |
| `door_reveal` | a door opens onto the new scene (the set needs a door) |
| `fade_from_black` | only to open the film, or after a jump in time (`time_jump: true`) |

There are no decorative wipes or spins: a scene arrives by a cut unless something in the story
carries us there.

## When something can't be filmed

Nothing is silently ignored. `sastudio validate` and `sastudio direct` stop with the reason and,
when there is one, the closest valid name:

```text
[error] helpful_caller.direction.lighting: Unknown lighting 'warm_interor'.
    Did you mean warm_interior? Choose from: daylight, dramatic, night_practical, office, soft_studio, suspense, warm_interior.
[error] helpful_caller.hc_07.act: 'phone_to_ear' and 'typing' both need the left arm.
    Give them to different lines.
[error] helpful_caller.direction.shots[2].seconds: The dialogue in this shot needs about 10.0 s, longer than 6 s.
    Lengthen the shot or split the lines.
```
