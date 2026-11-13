# What the engine draws on

The clay engine is written here, in Python that runs inside Blender: the sculptor, the sets, the
acting, the physics of feet and seats, and the checks that a body never passes through anything.
Nothing in it is a trained model, and it ships no motion capture. Where it follows something that
somebody measured or published, this page says what, and where to find it in the code.

The papers below are mostly about learned motion models. The engine does not reproduce them. It
takes the measures they use to judge whether movement is physically believable, and holds its own
procedural movement to the same measures, often more strictly.

## Bodies that touch the world

- **Inside, floating, sliding.** Motion research judges physical plausibility by three numbers:
  how far a body sinks into the ground, how far it floats above it, and how far a foot in contact
  slides, with a 5 mm tolerance ([PhysDiff, Yuan et al., ICCV 2023](https://arxiv.org/abs/2212.02500)).
  A foot counts as skating when it skids more than 2.5 cm while in contact
  ([GMD, Karunratanakul et al., ICCV 2023](https://arxiv.org/abs/2305.12577)). `engine/clay/contacts.py`
  measures every drawing the same way, on the meshes as drawn: no sole of a standing body may be more
  than 5 mm above what is under it (`float`), and a standing foot may not move along what it stands on
  by more than 5 mm a frame (`skate`), far stricter than the 2.5 cm.
- **Contact and penetration.** [PROX (Hassan et al., ICCV 2019)](https://arxiv.org/abs/1908.06963)
  fits bodies to scanned rooms with two terms: parts of the body that touch the world (the feet, the
  backs of the thighs, the seat, the back, the hands) are drawn onto it, and no part may be inside it.
  The probe uses the same idea as a test, not a fit: a seated body's seat and thighs must rest on the
  seat, and every part is measured triangle against triangle against everything solid.
- **Feet that stay put.** A planted foot keeps its place and its direction until it lifts; a walk
  that turns a corner, stops or changes its mind carries on from where the feet are; a heel that
  rises pivots on the ball of the foot, and a heel strike on the heel (`engine/clay/acting.py`).
  These are exactly the slides the measures above catch.

## Sitting down

- Studies of people sitting, captured in motion
  ([SAMP, Hassan et al., ICCV 2021](https://arxiv.org/abs/2108.08284);
  [COUCH, Zhang et al., ECCV 2022](https://arxiv.org/abs/2205.00541)), show the order every sit follows:
  walk up, turn round, back onto the seat, lower. The engine stages the same order, but solves the
  body from geometry rather than learning it: each seat is measured where somebody sits on it, and
  `engine/clay/body.py` works out from that person's own legs where the thighs, knees and feet go.

## A set that keeps out of itself

- Generated rooms are judged by whether objects collide and whether small things rest on
  surfaces ([Holodeck, Yang et al., CVPR 2024](https://arxiv.org/abs/2312.09067);
  [PhyScene, Yang et al., CVPR 2024](https://arxiv.org/abs/2404.09465)). The set dressing
  (`film.settle_dressing`) puts every loose thing on the highest point under it and separates
  outlines that overlap by the smallest push, measured with the separating axis test for oriented
  boxes ([OBBTree, Gottschalk, Lin and Manocha, SIGGRAPH 1996](https://doi.org/10.1145/237170.237244)).

## Eyes

- **Blinking follows what a person is doing.** 150 people blinked 17 times a minute at rest, 26 in
  conversation and 4.5 while reading
  ([Bentivoglio et al. 1997, Movement Disorders 12](https://pubmed.ncbi.nlm.nih.gov/9399231/)).
  The engine uses those three rates, scaled by each character's habit; typing counts as reading.
- **Listeners blink as a line ends.** Addressees' blinks are timed to the ends of the speaker's units
  of talk, as feedback
  ([Hömke, Holler and Levinson 2017](https://doi.org/10.1080/08351813.2017.1262143)). A listener
  blinks just after most lines end.
- **Speakers look away as they begin.** Speakers tend to look away at the start of a turn, while
  they plan it, and back at the listener as they finish
  (Kendon 1967, Acta Psychologica 26: 22–63); agents that do
  it are seen as thinking
  ([Andrist, Mutlu and Gleicher 2013](https://doi.org/10.1007/978-3-642-40415-3_22)). Not everyone
  found the same pattern (Beattie 1978), so the engine does it on most lines, more often on long
  ones and for wandering eyes, and never on every line.
- A blink comes with every big turn of the head, as it does in people (Evinger et al. 1994,
  Experimental Brain Research 100).

## Laughing

- Laughter moves the head, the shoulders and the torso in rhythm with its bursts, not the face
  alone ([Ding et al., AAMAS 2014](https://ifmas.csc.liv.ac.uk/Proceedings/aamas2014/aamas/p773.pdf);
  Niewiadomski et al., ICMI 2014). The engine's laugh is a breath in, then bursts about four a second
  that move the breath, the shoulders, the head and the jaw together, and fade.

## Personality in movement

- A few named qualities can drive many movement parameters at once
  ([EMOTE, Chi et al., SIGGRAPH 2000](https://doi.org/10.1145/344779.352172);
  [PERFORM, Durupinar et al., ACM TOG 2016](https://www.cs.ucdavis.edu/~neff/papers/PERFORM_TOG.pdf)).
  A character's `manner` and `age` work the same way with the engine's own numbers
  (`claydesign.MANNERS`, `claydesign.AGES`): how steadily they look, how often they blink, how they
  gesture, react, sit down and turn. [CHARACTERS.md](CHARACTERS.md) lists them.

## How it is held to all this

`sastudio check` poses every drawing of every planned shot and measures it against all of the above
before anything is drawn, and filming refuses a shot that fails. The tests in
`tests/test_contacts_blender.py` hold the engine to the same numbers: a foot on the floor never moves
or turns, walking is never a hop, blinking keeps the measured order and rates, a speaker is always
back on the listener before a line ends.
