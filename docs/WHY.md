# Why Clayvoyant exists

A minute of generated video is expensive. The services that make it charge by the second or ration
it by the month, the open models that replace them want a graphics card most people do not own, and
either way the result is a few seconds long, with a face that changes between shots and a mouth
that does not say your words.

Most of what people need video for is not that. It is two people talking: a lesson, a warning, an
explanation, a story for a class, a message for a team. That can be made a different way, on an
ordinary computer, for nothing.

Clayvoyant makes a film the way a stop-motion studio does, with every job done by code that runs
on your machine. Characters are sculpted from a description. Rooms are built. A director plans the
shots. Voices are synthesised locally. The film is drawn frame by frame and assembled with
subtitles. There is no video model anywhere in it, so there is nothing to pay per second, no queue,
no quota and no account.

## Who it is for

- **People with no budget for video.** Teachers, students, volunteers, small charities, one-person
  IT departments, community groups. If you can write a conversation, you can make the film of it.
- **People who have used up their allowance.** The script is text. Write it yourself, or ask the
  chat assistant you already use ([how](WRITING_WITH_AN_ASSISTANT.md)): a script is a page of words,
  which even a free plan will write, and none of your video allowance is touched because none is
  needed.
- **People who cannot send their material anywhere.** Nothing leaves the computer. No upload, no
  telemetry, no key. After one download of the free voice it works with the network unplugged.
- **People who need it in their own language.** One script makes one film per language. English
  and Hindi are free and offline, with Devanagari subtitles; other Indian languages work with
  recorded lines or a paid Indian voice service. The `india` template is five scenes about the
  scams that reach Indian phones every day ([films for India](INDIA.md)).
- **People who need the same film next year.** The film is a folder of text files. Change a name,
  a line or a language and film it again; only the shots that changed are redrawn.

## What it costs

Nothing but time and electricity. Measured on a 2020 laptop (Intel Core i7-10750H, GeForce GTX 1660
Ti with 6 GB, bought for games, not for machine learning):

| | |
|---|---|
| The 82-second sample film, every shot from nothing | about an hour at 1280x720 |
| One second of filmed footage | about a minute of drawing at 1280x720, about half that at 960x540 |
| Changing one line afterwards | only the shots it touches are filmed again, usually a few minutes |
| The other renderer (drawn characters, no Blender, no graphics card) | a 14-minute film in 90 seconds on the processor alone |
| Accounts, keys, subscriptions, credits | none |

[What was measured and how](CLAY_MOTION.md#measured). An hour is slow next to a paid service and
free next to its invoice, and the hour is unattended: start it and come back.

## What you get that a video model does not give you

- **The same person in every shot.** A character is a sculpture, not a sample. Tara in the first
  shot is Tara in the last, from any angle, in any light, in next year's sequel.
- **Words that are said.** Lines are voiced, mouths follow the sounds, and the subtitles are the
  script itself, timed to the frame. Not a guess at what a clip seems to say.
- **Length.** A scene is as long as its conversation. The sample runs 82 seconds; the starter film
  runs 14 minutes.
- **Edits.** Move someone to another chair, swap a close-up for a two-shot, soften the light,
  change one word. Each is a line of text and a short re-film, not a new roll of the dice.
- **Nothing passing through anything.** People walk round furniture, sit on seats and hold mugs
  by the outside, and a [checker](CLAY_MOTION.md#nothing-passes-through-anything) proves it shot by
  shot.
- **A film that is yours.** Everything on screen is made by this code from your text. No stock
  footage, no model weights with terms attached, no likeness of anyone. MIT licence; no credit
  required in what you make.

## How it compares

Checked in November 2026 against each project's own documentation. They are good at what they are
for; the table is about which problem each one solves.

| | What it makes | What it needs | Same characters across a film | Spoken, lip-synced dialogue |
|---|---|---|---|---|
| **Clayvoyant** | Whole acted scenes of any length, in clay stop motion or as drawn cards | Python, FFmpeg, Blender; a modest graphics card helps and is not required | Yes: they are sculpted once | Yes, with exact subtitles |
| Paid text-to-video services | Photoreal or stylised clips a few seconds long | An account and credits, or a subscription with a monthly limit | Not reliably | On some plans, for short clips |
| Open video models run locally, such as [Wan](https://github.com/Wan-Video/Wan2.2) | Clips of about five seconds from a prompt | A large graphics card: its documentation asks for 24 GB for 720p on one card, and lighter community set-ups trade away resolution | Not reliably | No |
| Stock-footage assemblers, such as [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | A narrated montage of stock clips | Keys for a footage library and usually for a language model | There are no characters | Narration only |
| Agent film pipelines, such as [FilmAgent](https://github.com/HITsz-TMG/FilmAgent) | Scenes staged in prepared 3D spaces by language-model agents | A language model for every decision, and a game engine | Yes, from a fixed set | Voiced; evaluated in its paper with a paid model |
| Talking-avatar animators, such as [synctoon](https://github.com/Automate-Animation/synctoon) and [AvatarScript](https://github.com/receptron/avatarscript) | One drawn character speaking a script | For real voices, a cloud voice service key (ElevenLabs, or OpenAI and Gemini); otherwise your own recording and an aligner | One character; scenes with several are not described | Yes: English, and Japanese in AvatarScript |
| Screenplay previsualisation, such as [Blender Screenwriter](https://github.com/tin2tin/Blender_Screenwriter) | Timed strips and blocked scenes for planning a shoot | Blender and your own assets | Yours to supply | No |
| Stop-motion add-ons for Blender, such as [Stopmagic](https://github.com/aldrinmathew/stopmagic) | A stop-motion look for animation you have already made | Blender, and an animator | Yours to model and rig | Yours to animate |
| Code-driven motion graphics (Remotion, Manim, Motion Canvas) | Titles, charts, diagrams and explainers you program | A programmer | There are no characters unless you draw and animate them | No |

We looked for another open project that takes a written conversation and returns a finished,
acted, voiced, subtitled film with no model, no key and no paid step, and did not find one. If you
know of one, [open an issue](https://github.com/xIBBAx/clayvoyant/issues): it belongs in this table.

## When something else is the better tool

- You need photographs of the real world, or a particular real place or product. Clayvoyant draws
  clay people in eight built sets.
- You need a film in the next five minutes and have credits to spend.
- You need crowds, vehicles in motion, weather or action. It films conversations: up to a handful
  of people who walk, sit, gesture, react and talk.
- You need a look other than clay stop motion or drawn cards.

[Known limits](../README.md#known-limits) lists what is not built, and
[the roadmap](ROADMAP.md) what could be.

## If your computer is small

- **No graphics card, no Blender.** `sastudio render` draws the same script as a captioned film of
  drawn characters who talk and blink. It needs only Python and FFmpeg and renders faster than the
  film plays ([quickstart](QUICKSTART.md)).
- **A laptop graphics card.** `sastudio film --preset draft` at 960x540 is about twice as fast as
  the sample's setting, and the cache means you pay for each shot once.
- **No graphics card, but Blender.** Clay films still render on the processor
  (`SASTUDIO_CLAY_DEVICE=CPU`). It is slower; we have not measured by how much on a machine without
  one, so try a single shot first: `sastudio motion PROJECT --scene ID --shot 1`.
- **No room for the 350 MB voice.** Record the lines yourself, one file per line
  ([voices](VOICE_PROVIDERS.md)); a phone's recorder is enough.
