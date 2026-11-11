# Requirements and performance

## Minimum

- Any 64-bit computer that runs Python 3.11+ and FFmpeg with libx264.
- About 1 GB of free memory for a `preview` render with `--jobs 4`, and 2 GB of free disk for a
  short film and its working files.
- No GPU. The cards renderer runs on the CPU.

## Measured numbers

Measured on one machine in November 2026: Intel Core i7-10750H (6 cores, 12 threads), 7.7 GB of
memory available to WSL2, Ubuntu 24.04, FFmpeg 6.1.1, Python 3.13. The film is the 12-scene starter
project (14 min 19 s) with silent placeholder voices, re-measured on 2026-11-11 except where a row
says otherwise. These are examples, not promises; your
hardware will differ.

| Job | Wall clock | Peak memory | Output |
|---|---|---|---|
| Whole film, `preview` 1280 x 720, `--jobs 4` | 90 s | 244 MB | |
| Whole film, `final` 1920 x 1080, `--jobs 3` | 2 min 41 s | 621 MB | 52.1 MB MP4 |
| Same render again, nothing changed | every scene reused | | |
| Three-scene example, `draft` 960 x 540, English (0.1.0, not re-run) | 14 s | 126 MB | 4 min 21 s of film |
| Same example, Hindi (0.1.0, not re-run) | 21 s | 128 MB | 5 min 12 s of film |

Real voices change a film's length, and therefore its render time, because placeholder timing is
only an estimate of speech.

## Clay films

Blender 4.2 or newer, the `clay` extra (numpy, scipy, scikit-image) and, for free voices, the
`voices` extra and the Kokoro model (350 MB, once). A GPU is not required but makes filming many
times faster. Measured on the same laptop with a GeForce GTX 1660 Ti (6 GB), on 2026-11-11:

| Job | Wall clock | Peak memory |
|---|---|---|
| Sculpt the sample's three characters | 46 s | 0.9 GB |
| Voice its 13 lines with Kokoro (47 s of speech) | 26 s | 0.6 GB |
| Film and assemble the 82-second sample at `preview`, every shot from nothing | 54 min 57 s | 1.95 GB |
| The same when only its last shot changed (16 reused, 1 filmed) | 3 min 17 s | 1.8 GB |

Filming runs one Blender at a time. Leave about 2 GB of memory for it, and about 1 GB of disk for
the sample's filmed shots in `.studio/cache/clay` (`sastudio clean --shots` lists the ones nothing
uses any more).

## How sastudio uses your hardware

- Speech lines are cleaned in parallel processes.
- Scenes render in parallel (`--jobs`, default: half your CPU threads, at most 6), and each
  scene's FFmpeg encoder gets an equal share of the threads.
- Only scenes whose content changed are rendered again; only lines whose spoken text or voice
  changed are generated again.
- Memory is usually the limit, not CPU. Lower `--jobs` if the computer starts swapping.
