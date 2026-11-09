# Installation

You need **Python 3.11 or newer** and **FFmpeg**. Everything else is optional.

| You want to | Install |
|---|---|
| Make a film with the cards renderer (any computer) | Python, FFmpeg, this package |
| Hear a free placeholder voice | + espeak-ng |
| Real voices | + a Sarvam or ElevenLabs account ([API_SETUP.md](API_SETUP.md)) |

No Docker, no Node.js, no GPU, no Blender and no cloud account are needed. The clay renderer is
not included in this release ([RENDERING.md](RENDERING.md#renderers)).

## 1. Python and FFmpeg

**Ubuntu / Debian / WSL2**

```bash
sudo apt update
sudo apt install python3 python3-venv ffmpeg git
```

**Windows 10/11** (PowerShell)

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id Gyan.FFmpeg --exact
winget install --id Git.Git --exact
```

Open a new terminal afterwards so `python`, `ffmpeg` and `git` are on your PATH.

**macOS:** `brew install python ffmpeg git`. macOS has not been tested yet.

Check: `ffmpeg -version` should print a version line, and its configuration should include
`--enable-libx264`. `sastudio doctor` checks this for you.

## 2. This package

```bash
git clone https://github.com/xIBBAx/security-awareness-studio
cd security-awareness-studio
python3 -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e .
sastudio doctor
```

`sastudio doctor` lists what is installed and what is missing, with a fix for each problem.

With [uv](https://docs.astral.sh/uv/), `uv sync` installs the exact versions pinned in `uv.lock`,
and `uv run sastudio doctor` runs the tool.

## 3. Optional: free placeholder voice (espeak-ng)

- Ubuntu/WSL: `sudo apt install espeak-ng`
- Windows: install the `.msi` from the [espeak-ng releases page](https://github.com/espeak-ng/espeak-ng/releases)
  (not yet tested on Windows by the maintainer).

If espeak-ng is missing, offline voices are timed silence: the film still renders, with
subtitles, so you can check timing and layout.

If espeak-ng is installed somewhere unusual, set `SASTUDIO_ESPEAK` to the program's path.

## Environment variables

| Variable | Purpose |
|---|---|
| `SARVAM_API_KEY`, `ELEVENLABS_API_KEY` | your provider keys (only for `--live` generation; see [API_SETUP.md](API_SETUP.md)) |
| `SASTUDIO_FFMPEG`, `SASTUDIO_FFPROBE` | FFmpeg programs, if not on PATH |
| `SASTUDIO_ESPEAK` | espeak-ng program, if not on PATH |

## Where it has been tested

| Environment | What was run | Result |
|---|---|---|
| Ubuntu 24.04 under WSL2 on Windows, Python 3.13.13, FFmpeg 6.1.1 | full test suite; the 12-scene starter film in `preview` and `final`; the example project in English and Hindi | passed (November 2026) |
| Same machine, clean virtual environments, Python 3.11, 3.12 and 3.13, installed from the built wheel | `sastudio --version`, `doctor`, `init`, `validate`, `render` | passed (November 2026) |
| GitHub Actions ([ci.yml](../.github/workflows/ci.yml)): Ubuntu and Windows, Python 3.11, 3.12, 3.13 | lint, tests, package build, install from the wheel and a draft render, on every push and pull request | results on the repository's Actions tab |
| Windows 11, Python 3.13, native (no FFmpeg installed) | test suite; `init`, `validate`, `script` in Hindi, `doctor` | 148 passed, 11 skipped (FFmpeg-dependent and POSIX-only tests); commands work, including Hindi output (November 2026). A Windows render with FFmpeg is covered by CI only |
| macOS | | not tested yet; reports welcome |
