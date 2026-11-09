# Requirements and performance

## Minimum

- Any 64-bit computer that runs Python 3.11+ and FFmpeg with libx264.
- About 1 GB of free memory for a `preview` render with `--jobs 4`, and 2 GB of free disk for a
  short film and its working files.
- No GPU. The cards renderer runs on the CPU.

## Measured numbers

Measured on one machine in November 2026: Intel Core i7-10750H (6 cores, 12 threads), 7.7 GB of
memory available to WSL2, Ubuntu 24.04, FFmpeg 6.1.1, Python 3.13. The film is the 12-scene starter
project (14 min 23 s) with silent placeholder voices. These are examples, not promises; your
hardware will differ.

| Job | Wall clock | Peak memory | Output |
|---|---|---|---|
| Whole film, `preview` 1280 x 720, `--jobs 4` | 74 s | 237 MB | 19.5 MB MP4 |
| Whole film, `final` 1920 x 1080, `--jobs 3` | 2 min 22 s | 615 MB | 50.6 MB MP4 |
| Same render again, nothing changed | every scene reused | | |
| Three-scene example, `draft` 960 x 540, English | 14 s | 126 MB | 4 min 21 s of film |
| Same example, Hindi | 21 s | 128 MB | 5 min 12 s of film |

Real voices change a film's length, and therefore its render time, because placeholder timing is
only an estimate of speech.

## How sastudio uses your hardware

- Speech lines are cleaned in parallel processes.
- Scenes render in parallel (`--jobs`, default: half your CPU threads, at most 6), and each
  scene's FFmpeg encoder gets an equal share of the threads.
- Only scenes whose content changed are rendered again; only lines whose spoken text or voice
  changed are generated again.
- Memory is usually the limit, not CPU. Lower `--jobs` if the computer starts swapping.
