# Troubleshooting

Start with:

```bash
sastudio doctor my-film       # what is installed, what is missing, and how to fix it
sastudio validate my-film     # every problem in the project, with a fix for each
```

Most errors end with a `fix:` line. Exit codes: `1` other error, `2` project or path problem,
`3` provider error, `4` budget stop, `5` missing API key, `6` missing tool, `7` render failure.

When you ask for help, paste the command and its output, but never an API key, a `.env` file, or
anything confidential from your organisation.

## Installation

**`sastudio: command not found`**
The virtual environment is not active. Run `. .venv/bin/activate` (Windows:
`.venv\Scripts\activate`), or use `uv run sastudio ...`.

**`error: FFmpeg was not found.`**
Install FFmpeg ([INSTALLATION.md](INSTALLATION.md#1-python-and-ffmpeg)) and open a new terminal.
If it is installed somewhere unusual, set `SASTUDIO_FFMPEG` and `SASTUDIO_FFPROBE` to the programs.

**`[FAIL] FFmpeg: ... This FFmpeg has no libx264 encoder`**
Your FFmpeg build cannot write H.264 video. Install a full build (the Ubuntu package and the
`Gyan.FFmpeg` winget package include it).

**`[WARN] Text shaping (Raqm): missing`**
Hindi and other Indic scripts will be drawn with broken letter joins. Use the official Pillow
wheel from PyPI (`pip install --force-reinstall pillow`) or install `libraqm` on Linux.

**`[INFO] espeak-ng ... offline voices will be timed silence`**
Not an error. Films render with subtitles and silence. Install espeak-ng for a robotic placeholder
voice ([INSTALLATION.md](INSTALLATION.md#3-optional-free-placeholder-voice-espeak-ng)).

**`The clay renderer needs Blender 4.2 or newer.`**
Install Blender and put it on `PATH`, or set `SASTUDIO_BLENDER` to the program's path. On WSL2 the
Windows `blender.exe` works too.

**`Sculpting clay characters needs numpy, scipy and scikit-image.`**
`pip install "security-awareness-studio[clay]"` (from a clone: `pip install -e ".[clay]"`).

**`The Kokoro model is not downloaded yet.`**
`sastudio voices install kokoro` (about 350 MB, once). The package itself comes with
`pip install "security-awareness-studio[voices]"`.

**`warning: device CPU ... rendering on the CPU is much slower`**
Blender found no usable GPU. The film is still made. Check the graphics driver, or set
`SASTUDIO_CLAY_DEVICE=CPU` to stop asking.

**A clay render was interrupted**
Run the same command again. Finished shots are reused and the interrupted one resumes at its first
missing drawing.

## Project files

**`studio.yaml is not valid YAML: ...`**
Usually indentation, or text containing `:` without quotes. Put dialogue in double quotes.

**`YAML anchors ('&name') are not allowed.` / `YAML aliases are not allowed`**
Write repeated values out in full. Anchors are refused because they can make small files expand
enormously.

**`... is an absolute path.` / `... uses '..' to leave the project folder.` / `... resolves outside the project folder (through a symbolic link).`**
Every path must be inside the project folder: `assets/logo.png`, not `C:\Users\...\logo.png` or
`../shared/logo.png`. Copy the file into the project instead.

**`'assets/logo.png': logo.png is not a readable image (...)`**
The file is damaged, is not really an image, or is over 40 megapixels. `validate` opens every logo,
portrait and backdrop to check. Re-export it as PNG, JPG or WebP.

**`This project uses format 2; this tool understands up to 1.`**
The project was made with a newer version of Security Awareness Studio. Update the tool.

**`Unknown character or token 'arav' in: ...` / `Unknown organisation field 'x' in: ...`**
The word after `{` is not a character id, and the word after `{org.` is not an organisation field
or one of your `organization.terms`. Ids are lower case; check the spelling.

**`Scene 'report_early' builds on scene 'too_good_email', which is turned off.`**
Turn the required scene back on, turn this scene off, or rewrite it to stand alone and remove its
`requires` entry ([SCENES.md](SCENES.md#dependencies-between-scenes)).

**`characters.x,y: 2 characters share the display name ...` (warning)**
Viewers won't know who is speaking. Give them different names.

**`render.renderer: The clay engine files are missing from this installation.`**
Reinstall the package, or set `render.renderer: cards`.

## Voices

**`N line(s) have no generated audio yet: ...`**
Some characters use a paid voice whose lines are not generated. Either generate them
(`sastudio voices generate my-film --live --max-characters N`) or render a preview with
`--voice-fallback offline`, which uses labelled placeholders for those lines only.

**`Missing API key(s): ELEVENLABS_API_KEY.`**
See [API_SETUP.md](API_SETUP.md). Check with `sastudio credentials my-film`.

**`Sarvam rejected the API key` / `ElevenLabs rejected the API key`**
The key is wrong, revoked or for another account. The run stops without retrying. Fix the key;
lines that were already generated are kept.

**`... out of credits`**
Top up with your provider. Nothing is retried; run the same command again afterwards and it
continues where it stopped.

**`'priya' is not a bulbul:v2 speaker` / `'X' does not look like an ElevenLabs voice ID`**
Speakers belong to one Sarvam model and are case-sensitive; ElevenLabs voice ids are letters and
digits copied from your voice library. `validate` names the right model when it can.

**`ElevenLabs could not find the voice`**
The voice was removed from your account or library. Choose another voice and update `voice_id`.
sastudio never swaps in a different voice for you.

**Rate limit or service errors**
Temporary errors are retried with backoff up to `voices.budget.max_retries`. If the run still
stops, run the same command later; finished lines are cached and are not paid for twice.

**`Another voice generation run is active for this project.`**
Two `voices generate` runs on one project at once are refused. If no run is active (a previous one
crashed), the lock expires after six hours, or delete `.studio/voices.lock`.

**`Line X is 3000 characters; bulbul:v3 accepts 2500.`**
Split the line into two lines.

**A name or acronym is mispronounced**
Use `spoken:`, `pronunciation:` or `speech.lexicon` and check with `sastudio script`
([VOICE_PROVIDERS.md](VOICE_PROVIDERS.md#how-names-and-words-are-spoken)).

## Rendering

**`Fix these problems first: ...`**
`render` runs the same checks as `validate`. Run `sastudio validate my-film` for the full list.

**`Scene X runs 92.3s; its max_seconds is 90.`**
New audio made the scene longer than its slot. Shorten dialogue, remove a card or raise
`max_seconds`.

**`Line X audio is 412s long, which looks broken.`**
A cached take is damaged. Delete that line's file under `.studio/cache/voices/` and generate it
again.

**`The film has N frames; the timeline has M.` / `Audio is ...s but video is ...s.`**
The finished file failed its own check and was not reported as done. This usually means the disk
filled up or FFmpeg was interrupted. Free some space and render again. Stored scene videos are
checked before they are reused, and damaged ones are rendered again ("the stored scene video is
damaged"). If the error persists, run `sastudio clean my-film` and render once more.

**`error: Permission denied: ...`**
sastudio cannot write to the output folder or `.studio/`. Check the folder exists and that you
can write to it (on Windows, that it is not a protected folder such as Program Files).

**`error: No space left on device: ...`**
Free some space and run the same command again. Finished voices and scenes are kept. The 14-minute
starter film at `final` quality used 502 MB of working files in `.studio/` plus the 51 MB film.

**The computer becomes slow or runs out of memory**
Lower the number of scenes rendered at once: `--jobs 2` or `--jobs 1`.

**Hindi text shows boxes or broken letters**
See "Text shaping (Raqm)" above.

**I changed something but the scene was not re-rendered**
Scenes are reused when nothing that affects their pictures changed. Run `sastudio clean my-film`
to force every scene to render again (finished films and the voice cache are kept).

## Windows and WSL

- Under WSL, keep projects in the Linux file system (for example `~/films`) for speed. Projects on
  `/mnt/c` or `/mnt/d` work but read and write more slowly.
- Paths in `studio.yaml` use forward slashes on every system: `assets/logo.png`.
- Hindi or other non-Latin text looks garbled when you pipe `sastudio` output through Windows
  PowerShell 5.1 (for example into `Select-Object` or `Out-File`). sastudio writes UTF-8; the old
  PowerShell re-decodes it with the console code page. Use Windows Terminal or PowerShell 7, redirect
  with `cmd /c "sastudio ... > out.txt"`, or run `[Console]::OutputEncoding = [Text.Encoding]::UTF8` first.
- Windows desktop and macOS have not been tested by the maintainer yet. Reports are welcome.
