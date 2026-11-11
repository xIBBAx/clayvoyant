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

## Guests

A character can be a model somebody already has (`sastudio model import`). A guest is fitted to
the height of the cast, grounded by measuring its real, skinned geometry, stripped of any
animation stored in the file, and then stands, walks, turns, looks, talks, blinks and gestures as
far as its bones and shape keys allow. It does not sit and has no fingers to pose. The licence you
state for the model is recorded in the project.

## Measured

On an Intel Core i7-10750H with a GeForce GTX 1660 Ti (6 GB), Blender 5.2.2 under WSL2 with CUDA:

| | |
|---|---|
| Sculpting one character | about 25 s (two worker processes) |
| A drawing at 960x540, 6 samples, three people in an office | 2.0 s |
| A drawing at 960x540, over-the-shoulder with depth of field | 2.6 s |
| Of which posing the puppets | about 0.1 s |
| Kokoro voice | 0.55 x the length of the line, about 600 MB of memory |

Nearly all of a drawing's time is Cycles refitting the puppets' geometry, not sampling: more
samples cost little, more people in frame cost more. Environment variables:
`SASTUDIO_BLENDER` (which Blender), `SASTUDIO_CLAY_DEVICE` (`GPU` or `CPU`).

## Not built yet

Sound effects, ambience and music beds; props beyond the mug and the phone; crowds; weather;
rendering on a remote machine; a visual editor. See [ROADMAP.md](ROADMAP.md).
