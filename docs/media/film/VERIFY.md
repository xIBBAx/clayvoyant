# Reference media verification

What was checked before the reference films were attached to the release, and how. Every film was
rendered from this repository alone by `tools/make_reference_media.py`, with
`sastudio 0.1.0`, Pillow 13.0.0 and ffmpeg version 6.1.1-3ubuntu5, on the machine described in
[REQUIREMENTS.md](../../REQUIREMENTS.md).

**What the films are.** Illustrated cards with hard cuts: a still portrait of whoever is speaking,
the line in large on-screen text, key-point cards and title cards. The characters are not animated.
The voices are the free offline placeholder, which is digital silence (measured below); the
dialogue is in the burned-in text and in the `.srt` and `.vtt` files beside each film.

## Films

| Film | Release file | Made from | Size | Duration | Frames | Bytes | SHA-256 |
|---|---|---|---|---|---|---|---|
| Starter film (master) | `Security_Awareness_in_Twelve_Stories.en-IN.mp4` | starter template, Quillmere branding, `--preset final` | 1920x1080 | 862.625 s | 20,703 | 50,519,718 | `1871815a16debd86…` |
| Trailer | `Security_Awareness_Trailer.en-IN.mp4` | 5 scenes built from starter lines, `--preset final` | 1920x1080 | 83.250 s | 1,998 | 3,636,518 | `6eee4b363a0b2120…` |
| Example, English | `Example_Quillmere_Security_Essentials.en-IN.mp4` | `examples/quillmere`, its own `draft` preset | 960x540 | 260.667 s | 6,256 | 2,381,905 | `e1de4d7efd022284…` |
| Example, Hindi | `Example_Quillmere_Security_Essentials.hi-IN.mp4` | `examples/quillmere`, `--lang hi-IN` | 960x540 | 312.375 s | 7,497 | 2,677,747 | `3570a856dbcd6d39…` |

Full checksums are in the release's `MEDIA_SHA256SUMS` file. (`SHA256SUMS` covers the wheel and
source archive built by the release workflow.)

## Checks on the starter film

| Check | Method | Result |
|---|---|---|
| Video stream | `ffprobe` | h264, 1920x1080, 24/1 fps, yuv420p |
| Audio stream | `ffprobe` | aac, 48000 Hz, 2 channels |
| Audio level | `ffmpeg -af volumedetect` | peak -91.0 dB: digital silence (placeholder voices) |
| Still frames | `ffmpeg -vf freezedetect=n=0.001:d=1` | 219 holds of 1 s or more, 809.3 s of 862.6 s (93.8 %) |
| Frame count equals the timeline | manifest and `ffprobe` | 20,703 = 20,703 |
| Black frames | `ffmpeg -vf blackdetect=d=0.25:pic_th=0.98`, all four films | 0 found |
| Subtitles | build checks (overlap, width, reading speed) | 187 cues, 0 warning(s) |
| Container metadata | `ffprobe -show_entries format_tags` | tags present: compatible_brands, encoder, major_brand, minor_version, title |

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
