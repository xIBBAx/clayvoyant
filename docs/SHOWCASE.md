# Showcase: the sample film, and what each fix looks like

Everything here was rendered by the code in this repository, from
[`examples/the-fast-one`](../examples/the-fast-one/): two scene files and one page of character
descriptions.

## The film

[![The Fast One: Tara and Odile at a cafe table at dusk. Press to watch.](media/film/the-fast-one-poster.jpg)](https://cdn.jsdelivr.net/gh/xIBBAx/clayvoyant@8cb3c0a/docs/media/the-fast-one.mp4)

**[Watch The Fast One](https://cdn.jsdelivr.net/gh/xIBBAx/clayvoyant@8cb3c0a/docs/media/the-fast-one.mp4)** (82 seconds, 6.6 MB; it plays in the browser, with the subtitles in
the picture. The file itself is [`docs/media/the-fast-one.mp4`](media/the-fast-one.mp4); GitHub's own
file page will not play a file this size). Made with
`sastudio film examples/the-fast-one --preset preview`: 1280x720, 24 frames a second, 1,974 frames,
seventeen filmed shots, thirteen lines voiced by Kokoro, -16 LUFS. Filming every shot from nothing
took 55 minutes on a laptop GeForce GTX 1660 Ti (measured on 11 November, before the solid-contact
re-film, which shared the machine with a second film). [TESTING.md](TESTING.md) lists what was checked.

![Twelve frames from the film: a cafe at dusk, then an office in morning light.](media/film/the-fast-one-sheet.jpg)

## Before and after

Each pair is two real renders of the same moment: before a fix on the left, after it on the right.

**People turn to the person they talk to.** Every standing spot on a set used to pin a body to the
lens, so Tara faced the camera while Bashir talked to her.

![Left: Tara square to the camera. Right: Tara turned towards Bashir.](media/proof/eyelines.jpg)

**Everyone a shot is on stays inside the frame.** The framing measured the people's spread at the aim
point, so the speaker nearest the lens lost half her face to perspective. Now every head is projected
through the real lens.

![Left: the speaker cut by the left edge of a wide. Right: the same wide with her inside the frame.](media/proof/framing-wide.jpg)

**No shot shows the back of a speaker's head.** An over-the-shoulder placed behind a listener who
stands upstage saw the speaker from behind; it is now filmed from the front.

![Left: the back of Tara's head. Right: Tara's face, reading her phone.](media/proof/over-the-shoulder.jpg)

**A long line cuts to the listener between two words**, on a drawing where the speaker's mouth rests.

![Left: Odile speaking behind the counter. Right: the cut to Tara listening, the same line still playing.](media/proof/reaction-cut.jpg)

## Asked for in a scene file

**`direction.light`**: a room's own light. The preset on the left; a low, warm key from camera right
on the right.

![Left: a close-up under the preset light. Right: the same close-up under a tuned light.](media/proof/light-tuned.jpg)

**`direction.props`**: Bashir's laptop, open as the shot starts, closes as Tara arrives.

![A home office at the start and the end of a shot: the laptop on the desk open, then closed.](media/proof/laptop-closes.jpg)

**`direction.dressing: [steam]`** and **`direction.clock: "07:05"`**.

![Left: steam rising off a mug on a cafe table. Right: a wall clock at five past seven.](media/proof/steam-and-clock.jpg)

How to ask for each of these: [DIRECTION.md](DIRECTION.md).
