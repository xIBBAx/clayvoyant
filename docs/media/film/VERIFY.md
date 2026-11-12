# Reference media verification

What was checked before the reference films were attached to the release, and how. Every film was
rendered from this repository alone by `tools/make_reference_media.py`, with
`sastudio 0.3.1`, Pillow 13.0.0 and ffmpeg version 6.1.1-3ubuntu5, on the machine described in
[REQUIREMENTS.md](../../REQUIREMENTS.md).

**What the films are.** Illustrated cards with hard cuts: whoever is speaking, the line in large
on-screen text, key-point cards and title cards. In the drawn styles (sketch, flat, cut-out) the
speaker's mouth and eyes move, 12 changes a second; bodies stay still. In the clay style the
portraits are still images.
The voices are the free offline placeholder, which is digital silence (measured below); the
dialogue is in the burned-in text and in the `.srt` and `.vtt` files beside each film.

## Films

| Film | Release file | Made from | Size | Duration | Frames | Bytes | SHA-256 |
|---|---|---|---|---|---|---|---|
| Starter film (master) | `Security_Awareness_in_Twelve_Stories.en-IN.mp4` | starter template, Quillmere branding, `cutout` style, `--preset final` | 1920x1080 | 862.625 s | 20,703 | 55,680,755 | `cae727ab6e244752…` |
| Trailer, v1 sketch | `Security_Awareness_Trailer.v1-sketch.en-IN.mp4` | 5 starter scenes, `sketch` style, `--preset final` | 1920x1080 | 83.250 s | 1,998 | 4,117,033 | `3419e1770fd6a8f5…` |
| Trailer, v2 flat | `Security_Awareness_Trailer.v2-flat.en-IN.mp4` | 5 starter scenes, `flat` style, `--preset final` | 1920x1080 | 83.250 s | 1,998 | 3,012,957 | `406d759811bc1b18…` |
| Trailer, v3 cutout | `Security_Awareness_Trailer.v3-cutout.en-IN.mp4` | 5 starter scenes, `cutout` style, `--preset final` | 1920x1080 | 83.250 s | 1,998 | 4,012,643 | `498da870d319bcfb…` |
| Trailer, v4 clay | `Security_Awareness_Trailer.v4-clay.en-IN.mp4` | 5 starter scenes, `clay` style, `--preset final` | 1920x1080 | 83.250 s | 1,998 | 3,629,886 | `7c3a73de91667990…` |
| Example, English | `Example_Quillmere_Security_Essentials.en-IN.mp4` | `examples/quillmere`, `cutout` style, its own `draft` preset | 960x540 | 260.667 s | 6,256 | 2,331,879 | `9973d8d5080c2b98…` |
| Example, Hindi | `Example_Quillmere_Security_Essentials.hi-IN.mp4` | `examples/quillmere`, `--lang hi-IN` | 960x540 | 312.375 s | 7,497 | 2,616,394 | `fa33132799dac441…` |

Full checksums are in the release's `MEDIA_SHA256SUMS` file. (`SHA256SUMS` covers the wheel and
source archive built by the release workflow.)

## Checks on the starter film

| Check | Method | Result |
|---|---|---|
| Video stream | `ffprobe` | h264, 1920x1080, 24/1 fps, yuv420p |
| Audio stream | `ffprobe` | aac, 48000 Hz, 2 channels |
| Audio level | `ffmpeg -af volumedetect` | peak -91.0 dB: digital silence (placeholder voices) |
| Long still stretches | `ffmpeg -vf freezedetect=n=0.001:d=1` (whole-frame change; a moving mouth is below its threshold) | 228 of 1 s or more, 807.3 s of 862.6 s |
| Frame count equals the timeline | manifest and `ffprobe` | 20,703 = 20,703 |
| Black frames | `ffmpeg -vf blackdetect=d=0.25:pic_th=0.98`, all four films | 0 found |
| Subtitles | build checks (overlap, width, reading speed) | 187 cues, 1 warning(s) |
| Container metadata | `ffprobe -show_entries format_tags` | tags present: compatible_brands, encoder, major_brand, minor_version, title |

## Does it move? The trailer in four styles

The same five scenes in each style. Counted: frames whose largest pixel change from the frame
before is 48 or more (of 255), from `ffmpeg -vf tblend=all_mode=difference,signalstats`. In clay
only cuts, fades and new subtitles cross it, so clay is the control; the extra frames in the drawn
styles are the speaker's mouth and blinks.

| Style | Frames with a strong change |
|---|---|
| v1 sketch | 532 of 1,997 |
| v2 flat | 538 of 1,997 |
| v3 cutout | 542 of 1,997 |
| v4 clay | 88 of 1,997 |

## Scenes in the starter film

| Id | Title | Topic | Starts at | Frames | Seconds |
|---|---|---|---|---:|---:|
| `_intro` | Title card |  | 0:00.00 | 108 | 4.500 |
| `first_day` | First Day | introduction | 0:04.50 | 1,727 | 71.958 |
| `too_good_email` | The Too-Good Email | phishing | 1:16.46 | 1,826 | 76.083 |
| `passwords_and_mfa` | One Password, Everywhere | passwords | 2:32.54 | 2,010 | 83.750 |
| `helpful_caller` | The Helpful Caller | social engineering | 3:56.29 | 1,795 | 74.792 |
| `urgent_from_the_top` | Urgent, From the Top | payment fraud | 5:11.08 | 1,644 | 68.500 |
| `lunch_break` | Lunch Break | clear desk | 6:19.58 | 1,689 | 70.375 |
| `free_gifts` | Free Gifts | removable media | 7:29.96 | 1,875 | 78.125 |
| `train_home` | The Train Home | remote work | 8:48.08 | 1,695 | 70.625 |
| `need_to_know` | Need to Know | data handling | 9:58.71 | 1,524 | 63.500 |
| `helpful_robot` | The Helpful Robot | ai tools | 11:02.21 | 1,332 | 55.500 |
| `report_early` | Report Early | incident reporting | 11:57.71 | 2,028 | 84.500 |
| `what_rook_fears` | What Rook Fears Most | closing | 13:22.21 | 1,306 | 54.417 |
| `_outro` | Closing card |  | 14:16.62 | 144 | 6.000 |
| | **Total** | | | **20,703** | **862.625** |

## Images in this folder

| File | What it is |
|---|---|
| `cover-1280x640.png` | README hero and GitHub social preview, composed by `tools/make_readme_media.py` |
| `cover-1920x1080.png` | 16:9 cover for slides and release pages, same tool |
| `thumbnail-1280x720.png` | video thumbnail, same tool |
| `loop.gif` | 8 seconds of the starter film (80-88 s), 800 px wide, 10 fps |
| `stills/01-title.png` to `stills/04-closing.png` | frames from the starter film at 2 s, 248 s, 74 s, 858 s, scaled to 1280 px |
| `stills/05-hindi.png` | a frame from the Hindi example at 95 s (960 x 540) |

The stills are checked for embedded text, EXIF and time chunks when they are made; none are written.
