# The Fast One

A two-scene clay stop-motion short: a cafe at dusk where one Wi-Fi network is a little too keen,
and an office the next morning where somebody collects near-misses. About seventy seconds.

Everything here is invented (Quillmere Logistics, the cafe, Tara, Odile and Bashir), and
everything on screen is made by the commands below from the three text files in this folder.

```bash
pip install -e ".[clay,voices]"
sastudio voices install kokoro
sastudio direct examples/the-fast-one              # the shot list, before anything is filmed
sastudio film examples/the-fast-one --preset draft # 960x540; use preview or final for more
```

The film, its subtitles (`.srt`, `.vtt`), a transcript and a manifest with checksums appear in
`examples/the-fast-one/build/en-GB/`. `--preset final` refuses the placeholder reporting address
on purpose; add `--allow-placeholder-contacts` for a demonstration.

## What to look at

| In the files | On screen |
|---|---|
| `studio.yaml`: three `look.design` blocks | three sculpted people who do not share a face: a ponytail and a zip jacket, a bun and a sweater, a beard, glasses and a shirt |
| `acting:` on each character | Tara is quick and loose, Odile unhurried, Bashir upright and economical |
| `blocking` and `business` in scene one | Tara is already sitting and typing when the scene opens; Odile is behind the counter |
| `go: table_left_2` with `act: [hold_mug]` | Odile walks over carrying a mug and takes the other chair |
| `transition_in: fade_from_black` | the film fades up on the cafe, with the title over the shot |
| `transition_in: follow_object`, `object: laptop` | scene two opens close on a laptop and pulls back to find Bashir at his desk |
| `act: [walk_in, wave]` | Tara comes in through the door, which opens for her, and arrives on her line |
| `act: [stand_up, nod]`, `[check_phone]`, `[thumbs_up]` | he stands to make the point; she reads it off her phone; the last shot pushes in |
| `emotion:` and `reactions:` | faces change on the line, and the listener's changes too |
| `voice: { provider: kokoro, ... }` | three free neural voices; mouths follow their sounds |

Change a line and run the command again: only the shots that line can affect are filmed.
