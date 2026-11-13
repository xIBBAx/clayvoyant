# Sound

A film's sound is built the way its picture is: from what the scene says and does. The voices come
first. Under them, every footstep, seat, door, chair, laptop and keyboard the picture shows is heard
on the drawing where it happens, in a room the size of the set, over the air of that place, with your
music set under the voices. The mix is mastered to a loudness target and measured again in the
finished, encoded film.

Nothing has to be set. A clay film with no `sound:` section gets the sounds of what happens, the air
of each place and a mastered mix. One music file is enough for a scored film:

```yaml
render:
  music: music/theme.mp3          # as before; now matched in loudness and faded in and out
```

## Settings

```yaml
sound:
  effects: true                   # what the picture shows happening (clay films)
  ambience: true                  # the air of each place
  library: sounds                 # your own recordings (below), or an installed pack: kenney
  music:
    - file: music/theme.mp3
      scenes: [cafe, bench]       # leave out for the whole film
      start: 12                   # seconds into the track
      volume_db: -2               # against the default level
      fade_in: 2
      fade_out: 3
      loop: true
  levels: { effects_db: 0, ambience_db: 0, music_db: 0, duck_db: 11 }
  master: { loudness: -16, true_peak: -1.5, bitrate: 192 }
  credits: ["Theme by ..., CC BY 4.0"]
```

### A scene's sound

```yaml
direction:
  sound:
    ambience: cafe                # or off, or a sound file of your own
    music: off                    # no music under this scene
    mute: [footstep]              # leave a kind of sound out of this scene
    cues:                         # sounds no motion makes, at a moment of a line
      - { sound: phone_ring, line: s1, at: 0, offset: -2.5, seconds: 3, who: mei }
      - { sound: sounds/knock.wav, line: l2, at: 1.0 }
```

`at` is how far through the line (0 its first word, 1 its last), `offset` moves the sound in seconds.
`sastudio sounds list` names every sound and every place.

## Where the sounds come from

Sounds come from what happens, never from words. If someone says "close the door" and nobody does,
there is no door.

**From the scene's plan.** The engine reads, once per scene, everything in the scene's own plan that
makes a sound (`engine/clay/sounds.py`, `film.py` in its `events` mode). Nothing is posed or drawn
for it.

| Sound | When it is placed |
|---|---|
| `footstep` | a foot's lift returns to the floor (walks, turns on the spot, changes of mind alike), at the foot's place; what it lands on is the set object under it |
| `sit`, `stand` | a body reaches nine tenths of the way down onto its seat, or leaves it; soft seats breathe, hard ones knock and creak |
| `scrape` | a chair drawn in under somebody or pushed back as they stand, for as long as it moves, on the floor under it |
| `door_open`, `door_close` | the door's latch as it starts to swing, and its panel and latch as it shuts |
| `laptop_close`, `laptop_open` | a lid that `direction.props` moves, as it lands or lifts |
| `typing` | hands on a keyboard: the `typing` gesture while seated at a desk |

**From the direction.** A phone ringing or buzzing, a message arriving, a knock, a file of your own:
`direction.sound.cues`, at a moment of a line.

**Timing.** Clay is drawn on twos: each drawing is held for two frames. A sound starts on the first
drawing that shows its cause, never before the picture and never a drawing late
(`sound.events.snap_to_drawings`).

**Once per action.** Events are found per scene, on the scene's clock, not per shot, so a footstep
seen in two overlapping shots is heard once, and a sound carries on across a cut as the action does.
The same kind of sound from the same thing within 150 ms is one sound, and a cue the direction asks
for wins over the same sound found in the motion. Every event has a stable identity (a hash of what
it is and when), so a film always gets the same sounds.

**Off camera.** Somebody the camera does not show still makes their sounds; somebody outside the
room does not.

## How the sounds are made

**Recordings first.** For each event the first folder with a recording of its kind gives it: your own
`sound.library`, then an installed pack. Lay recordings out by kind (and surface):

```
sounds/footstep/wood/*.wav    sounds/footstep/carpet/*.wav    sounds/footstep/*.wav
sounds/door_close/*.wav       sounds/sit/*.wav                sounds/typing/*.wav
```

The choice among a kind's files follows the event's identity, a footstep never repeats the step
before it, and each recording is trimmed to its onset so it lands on its drawing.

**Made by code, otherwise** (`sound/foley.py`). Most everyday sounds are a short push into something
that rings: modal synthesis, a sum of damped sinusoids excited by a contact force whose length sets
the brightness (van den Doel, Kry and Pai,
[FoleyAutomatic](https://www.cs.ubc.ca/~kvdoel/publications/foleyautomatic.pdf), SIGGRAPH 2001;
Cook, *Real Sound Synthesis for Interactive Applications*, 2002). A heel on tile pushes for about
2 ms and rings high; a soft sole on carpet pushes for 15 ms and only thumps. A footstep is a heel
strike, then the ball of the foot 50 to 110 ms later, with the grit of the surface between them;
every floor has its own modes, stiffness and grit, and no two steps are alike. Creaks and scrapes are
friction: runs of tiny stick-slip impulses through the wood's or the legs' resonances. Ring tones and
notifications are synthetic by nature; the ring is an original four-note figure.

**Rooms** (`sound/ambience.py`). Every effect is played in its scene's room: early reflections from
the nearest surfaces, then a diffuse tail whose highs die sooner than its lows. Each set has its real
size and floor, so its reverberation time comes from Sabine's formula, RT60 = 0.161 V / A: about
0.5 s for the carpeted meeting room, 0.9 s for the tiled cafe, 1.6 s for the stone corridor, and none
outdoors but a slap back from the buildings.

**The air of a place.** Every place has its room tone, made the length of the scene from noise shaped
like the real thing, never looped: ventilation and the mains hum of an office; a quiet home; the
murmur of other tables and, now and then, a cup across a cafe; wind and distant traffic in a street.
A bed holds only what the set shows or implies. It never invents a crowd, weather or an event.

**Packs.** `sastudio sounds install kenney` downloads Kenney's
[Impact Sounds](https://kenney.nl/assets/impact-sounds) and
[RPG Audio](https://kenney.nl/assets/rpg-audio): real recordings of footsteps on wood, carpet and
concrete (used for paving, stone and tile too), doors opening and closing, and plates set down, all
CC0. The archives are checked against pinned checksums and their licence files; only the recordings
the engine uses are kept, with a manifest of each one's source, creator, licence, date and checksum.
Nothing is ever downloaded while a film is made. Use a pack with `sound: { library: kenney }`.

## The mix

Four buses (`sound/mix.py`), mixed sample by sample in numpy, so every sound lands exactly where it
should and nothing renormalises as sounds start and stop:

| Bus | Level |
|---|---|
| dialogue | as the build timed and levelled it (each line about -18 LUFS) |
| effects | an ordinary action peaks about 10 dB under the dialogue's peaks |
| ambience | a quiet home 30 LU under the dialogue, an office 27, a street 22, a cafe 20 |
| music | 11 LU under the dialogue while nobody speaks, and 11 dB lower again under speech |

Every level is set from a measurement: the dialogue's loudness (ITU-R BS.1770-4, `sound/meter.py`) is
the reference, every bed and every music file is measured and brought to its place, so a quiet track
and a loud one sit at the same level. Speech over music needs at least 10 LU between them to be easy
to follow, more for listeners with hearing loss (Torcoli et al.,
[JAES 67(12), 2019](https://doi.org/10.17743/jaes.2019.0052)); under speech the music here is 22 LU
down.

**Ducking without pumping.** The music's dip is an envelope computed from the dialogue: speech is
found in 10 ms blocks, gaps under 0.45 s count as speech (no rise between words), the dip starts
0.15 s before the first syllable, takes 0.12 s to go down and 0.6 s to come back. A compressor
listening to the voice cannot look ahead and pumps in the gaps; this cannot.

**Fades and crossfades** are equal power (sine and cosine), so two different sounds crossing keep
their combined level: at a change of place the old air carries on a moment past the cut while the
new one comes in. Music fades in and out at the ends of its scenes, crosses into the next cue, loops
with a crossfaded seam when it is shorter than its scenes, and leaves scenes marked `music: off`.

**`render.music`** still works: it is one cue under the whole film, now matched in loudness.
`render.music_volume_db` moves it from the new default by as many dB as before (-24, the old default,
is the new default level; -18 is 6 dB louder).

## Mastering

The default suits a short film watched online, mostly speech: **-16 LUFS** integrated and
**-1.5 dBTP** true peak in the encoded film. -16 is Apple's spoken-word target and inside AES TD1008's
range for speech and mixed content; streaming players turn louder films down to about -14, so
-16 plays at full level without being pushed. Lossy codecs raise peaks, more at lower bit rates
([EBU Tech 3343](https://tech.ebu.ch/docs/tech/tech3343.pdf),
[AES TD1008](https://aes.org/wp-content/uploads/2024/01/20210924_TD1008_v3.13.pdf)), so the ceiling is
set below EBU R 128's -1 and the master is limited a further 0.5 dB under it before encoding (0.3 dB
at 256 kb/s or more, 1 dB under 160 kb/s).

How (`sound/master.py`): one gain to the loudness (a linear change, as FFmpeg's two-pass `loudnorm`
makes in linear mode), then a look-ahead true-peak limiter for the few transients above the ceiling:
the gain starts down 5 ms before a peak, so it is never late, and recovers over 120 ms, so a single
transient does not pump. True peak is measured at four times the sample rate, as BS.1770 Annex 2
asks. Limiting lowers the loudness a little, so gain and limiter are repeated until both hold. The
film is then encoded (AAC), decoded and measured again by FFmpeg's EBU R 128 meter; if the codec
pushed a peak over the ceiling, the audio is mastered with the ceiling that much lower and encoded
again. The manifest records what the encoded film measures. If both targets cannot be met (reaching
the loudness would need more than 6 dB of limiting), the build says so and does not claim them.

## Building again

Only the reading of each scene's events uses Blender, once; it is kept, keyed by the scene's plan,
the characters and the engine's code. Change the music, a cue, a level, a bed or the master, and the
next `film` reuses every shot and every scene video and builds only the sound. Interrupted, a build
leaves no half-written sound file: each is written whole and moved into place.

## Measured

On the machine in [TESTING.md](TESTING.md), 2026-11-13:

| What | Result |
|---|---|
| The BS.1770 meter against FFmpeg's EBU R 128 meter (1 kHz tone, pink noise, speech-like bursts, 100 Hz hum) | within 0.02 LU |
| True peak of a sine at a quarter of the sample rate whose samples miss its crests (samples at -3 dB) | 0.09 dB from 0 dBTP |
| The limiter on noise, a loud first sample, isolated clicks; three minutes of stereo noise in 10 s | every true peak at or under the ceiling |
| Sound tests (`tests/test_sound.py`) | ducking depth and recovery, crossfades, placement to the sample, cues, music of any rate and layout, bad files, encoded loudness and true peak, audio-only rebuilds |

How real the sounds made by code are, judged by [earshot](https://github.com/Leonxlnx/earshot)'s
recorded-or-synthesized classifier (`p_real`, 0 to 1; under 0.17 it hears code, over 0.77 a
recording):

| Sound | Alone | Walking in a room, with its air |
|---|---|---|
| Footsteps made by code: wood, tile, carpet | 0.02, 0.04, 0.34 | 0.36, 0.69, 0.39 |
| Kenney's recorded footsteps (CC0): wood, concrete | 0.07 to 0.27, 0.29 to 0.85 | 0.50, 0.64 |
| Doors, laptop, mug, typing, chairs, seats made by code | 0.01 to 0.10 | |

Heard alone, every sound made by code reads as made by code, and so do short game recordings. In a
room with its air, the footsteps made by code sit in the same band as recordings. They are good
enough to place a scene, not studio Foley: for that, bring your own recordings (`sound.library`).

## Licensing

The sounds made by code are made by this repository's code, under its MIT licence. No recording ships
with Clayvoyant. Recordings you bring are yours to clear; `sound.credits` puts their credits in the
manifest. The `kenney` pack is CC0: anyone may use and pass it on, credit optional (it is credited in
its manifest). Mixkit, Pixabay, Sonniss, BBC, ZapSplat, YouTube Audio Library and Epidemic Sound
recordings may be used inside your own films under their licences, but none of their licences allows
passing the files on in a library, so none is offered as a pack.

## Not built

- Voices that laugh, sigh or breathe: a laugh made from noise does not sound like a person. A
  character's own recorded reactions can be placed as cues (`sound: path/to/laugh.wav`).
- Sounds that follow the camera: panning follows where things are in the room, gently, the same in
  every shot of a scene.
- Clothing that rustles with every gesture, and footsteps that change with a character's mood.
- Picking things up and putting them down. A carried mug or phone is in the hand once the fingers
  close round it; nothing yet animates taking it from a table, so nothing is heard. A cue can place
  one where the story needs it (`sound: set_down`).
