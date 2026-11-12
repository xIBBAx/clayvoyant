# Clay films

`sastudio film <project>` makes the whole film in clay stop motion: voices, sculpted characters,
sets, cameras, light, lip sync, subtitles. This page explains what happens between the text you
write and the frames you get, and where each part lives.

```bash
pip install -e ".[clay,voices]"          # sculpting and the free voice
sastudio voices install kokoro           # once
sastudio direct my-film                  # read the shot list before filming
sastudio motion my-film --scene first_day --shot 2    # a silent look at one shot
sastudio film my-film --preset draft     # the film
```

Blender 4.2 or newer must be on `PATH`, or named in `SASTUDIO_BLENDER`. On WSL2 either the Linux
build or the Windows `blender.exe` works; paths are converted for the Windows one.

## 1. Sculpting

A character is not assembled from parts. Its head, its clothes, its hands and its hair are each one
continuous form described by signed-distance functions (`engine/sculpt/sdfkit.py`): ellipsoids,
cones and coils of clay blended into each other, then carved (the parting of the lips, the eye
openings), then turned into a mesh by marching cubes. Colour is painted onto that mesh in washes,
the way a puppet painter does it, and creases are darkened by measuring the sculpt itself.

- `engine/sculpt/heads.py`: the skull on real facial proportions, a carved mouth, eyes with
  separate lids, brows, teeth and tongue, skin that is never one colour, beards and moustaches.
- `engine/sculpt/bodies.py`: eight garments (blazer, suit jacket, zip jacket, shirt, sweater,
  hoodie, kurta, knit vest), each with a real hem, plus shoes and the hand.
- `engine/sculpt/hair.py`: ten styles, each one mass that hugs the skull and is combed by a tool.
- `engine/sculpt/build.py`: builds a character's files (`.npz`) from one JSON of numbers.

Nobody writes those numbers. `sastudio/claydesign.py` turns the `look.design` in your project
(skin, hair, outfit, build, height, face sliders) into them, varies every face a little by
character id, and lets `look.clay` set any of them outright ([CHARACTERS.md](CHARACTERS.md)).
Sculpting takes about 25 seconds per character and is cached until the look changes.

<p align="center">
  <img src="media/characters/clay-proof.jpg" width="100%" alt="Three stills of sculpted characters from the sample film. A full figure: Bashir, bearded and in glasses, arms folded. A face: Tara grinning with her hand at her chin, teeth showing, eyes bright. A hand: Odile's open palm in close-up, four fingers and a thumb, against the knit of her sweater.">
</p>

## 2. The puppet

Inside Blender, `engine/clay/puppet.py` puts the sculpt on a rig that is solved with plain
matrices every frame:

- a spine that bends, twists and squashes the torso mesh itself;
- sleeves and trouser legs swept along the bones each frame, bunching where they bend;
- an anatomical arm and hand (`handrig.py`): the elbow swings with where the hand is going, the
  forearm rolls and the wrist bends inside human limits, four fingers and a thumb curl through
  fifteen bones, so a palm can only turn the way a palm turns;
- a face of 21 controls (`faceops.py`) that move one continuous head mesh: jaw, lips, smiles and
  frowns per side, brows, squints, how wide the eyes open;
- clay, cloth, skin and eye materials (`claymat.py`): thumb-print whorls, fine grain, colour that is
  never flat.

## 3. Acting

`engine/clay/acting.py` is the performance. Everything in it is a pure function of the frame
number, which is what makes shots cacheable and resumable.

- **Walking.** Feet plant ahead of the hips and stay planted; the pelvis rises over the standing
  foot and sinks between steps; heel strikes, toe leaves; arms swing against the legs; a walk
  starts with a half step and ends with a settling one.
- **Sitting.** The pelvis lowers to the seat, the feet come forward and stay on the floor.
- **Hands.** More than forty gestures, each a place for the hand, a finger shape and a wrist. Hands travel in
  arcs, arrive a beat apart, settle past their mark, and never snap when a new gesture interrupts.
- **Speech in the body.** The stressed sounds of a line nod the head, lift the brows and beat the
  hands. A speaker changes gesture on the thought, not on a timer.
- **Eyes.** Eyes lead, the head follows, the body last. Blinks, small saccades, a blink on every
  big turn. Listeners look at the speaker and nod.
- **Feelings.** Twenty-one faces, blended from one to the next, that stay under the words.
- **Things.** A mug or a phone is carried in the palm; a hand that carries does not swing.

Lip sync uses the nine mouth shapes of the Rhubarb alphabet. When the voice provider reports the
time of each sound (Kokoro does), the mouth follows them; otherwise `sastudio/lipsync.py` reads
the shapes from the spelling and lays them over the parts of the audio where someone is speaking.

## 4. Places and light

`engine/clay/setkit.py` is a kit of clay forms, furniture, props and lamps; `sets.py` builds eight
places from it. Nothing is loaded from a model, photograph or texture file. A set wears the
organisation's palette and name, and declares its *marks*: where people can stand or sit, which
seats have a table, where the door is.

Light comes from the lighting mood you choose (key, fill, rim, exposure), from the set's own lamps,
and from the time of day: by day the sun reaches a room through a window nobody sees, whose frame
throws real pane shadows across the floor and the far wall. Rooms have a ceiling the camera sees
and the light does not.

## 5. Filming

`sastudio/stopmotion` writes a *job* for each shot (set, light, cast, every line with its mouth
cues, every acting key, one camera) and `engine/clay/film.py` films it:

- The camera is placed from where the people really are: a close-up from the side a face is turned
  to, an over-the-shoulder from behind the listener, a wide from standing height. A subject who
  walks is followed. Depth of field focuses on the subject every frame.
- Two checks run on every placement. People are played towards the open front of the set, so when
  the listener stands upstage of the speaker an over-the-shoulder would see the back of the
  speaker's head: that shot is filmed as a two-shot from the front instead, and the log says so.
  And everyone a shot is on is projected through the real lens; if perspective pushes someone near
  the camera past the edge of the frame, the camera steps back until they fit.
- Every scene opens on a filmed shot of its place, with the title over it, entered by its
  transition (see [DIRECTION.md](DIRECTION.md)).
- Frames are drawn on twos: twelve drawings a second, each held for two frames.
- Each shot is stored under a hash of everything that can affect it. Changing a later line does
  not re-film an earlier shot. A shot that was interrupted resumes at its first missing drawing.
- Blender only runs the scripts shipped in this package. A job holds numbers, names from fixed
  lists and file paths chosen by `sastudio`; nothing in a project file is ever executed.

The filmed frames then go through the same compositor as every other film here: subtitles, name
tags the first time someone speaks, cards, the intro and outro, frame-exact audio, loudness
normalisation, the manifest with checksums ([RENDERING.md](RENDERING.md)).

## Nothing passes through anything

Every character is solid, and so is every piece of the set. Nothing is placed by an assumed height:

- Before the cast exists, the set's own geometry (floors, rugs, furniture, props; not the door that
  swings) is built into a ray-cast tree. Each foot comes down on the highest point under six samples
  across its sole: the floor, a rug, the base of a table. The body stands on what is under it.
- After everyone is posed for a drawing, the film measures what touches what: a seated body's lowest
  point and its thighs against the seat, a hand laid on a table and its forearm against the top, each
  foot and shin against chair bases and table feet, a gesturing hand against the props around it.
  Whatever is inside is moved out in small measured steps (a body up off the seat, hands up off the
  table, a foot sideways out of a chair's base, a hand clear of a mug) and posed again. What is
  learnt is kept for that seat, that table or that spot, so the next drawings start right.
- Chairs are shallower than a thigh is long, so a sitter's knees clear the front edge and the shins
  hang in front of the legs.

`python tools/check_contacts.py PROJECT` checks a filmed project: Blender poses every shot exactly as
the film does and intersects every triangle of every character with the set and with each other.
Touching is allowed; any intersection is listed with its frame, and the command fails.

## Guests

A character can be a model somebody already has (`sastudio model import`). A guest is fitted to
the height of the cast, grounded by measuring its real, skinned geometry, stripped of any
animation stored in the file, and then stands, walks, turns, looks, talks, blinks and gestures as
far as its bones and shape keys allow. It does not sit and has no fingers to pose. The licence you
state for the model is recorded in the project.

## Measured

On 2026-11-11, on an Intel Core i7-10750H (12 threads) with a GeForce GTX 1660 Ti (6 GB), Blender
5.2.2 under WSL2 with CUDA:

| | |
|---|---|
| Sculpting the sample's three characters from nothing | 46 s in all, 0.9 GB at most |
| A drawing at `draft` (960x540, 6 samples) | 2.2 to 2.6 s (247 drawings, four shots) |
| A drawing at `preview` (1280x720, 12 samples) | 4.2 to 5.0 s, 4.7 s on average (666 drawings, 17 shots, two runs) |
| The whole sample film at `preview`, every shot filmed from nothing | 54 min 57 s and 55 min 11 s in two runs, 1.97 GB at most |
| Kokoro voice | 26 s for the sample's 47 s of speech, model loading included; 0.6 GB |
| Posing the puppets, per drawing | not re-measured (an earlier note said about 0.1 s) |

Going from `draft` to `preview` (1.8 times the pixels, twice the samples) roughly doubles the time a
drawing takes; more people in frame cost more. Environment variables: `SASTUDIO_BLENDER` (which
Blender), `SASTUDIO_CLAY_DEVICE` (`GPU` or `CPU`), `SASTUDIO_CLAY_STALL_MINUTES` (how long Blender
may draw nothing before it is stopped, default 20) and `SASTUDIO_CLAY_RETRIES` (default 1).

## Not built yet

Sound effects and ambience (a music bed of your own does work: `render.music`, ducked under the
dialogue); props beyond the mug and the phone; crowds; weather; rendering on a remote machine; a
visual editor. See [ROADMAP.md](ROADMAP.md).
