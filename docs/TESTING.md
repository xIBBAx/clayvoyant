# Testing and the edge-case matrix

```bash
uv run pytest          # or: pytest
uv run ruff check .
```

The suite runs offline, needs no API key and never calls a paid API. Tests that need FFmpeg skip
themselves when it is missing. Provider adapters are tested against recorded responses through a
fake transport (`tests/conftest.py`).

## Results for 0.1.0

| Where | Result |
|---|---|
| Ubuntu 24.04 (WSL2), Python 3.13, FFmpeg 6.1.1 | 158 passed, 1 skipped (the opt-in paid-API hook) |
| Clean copy of the repository, fresh locked environment | same |
| Windows 11, Python 3.13, no FFmpeg | 148 passed, 11 skipped: the 8 FFmpeg tests, a symlink test that needs admin rights, a POSIX-only test and the paid-API hook |
| CI ([ci.yml](../.github/workflows/ci.yml)): Ubuntu (FFmpeg 6.1) and Windows (FFmpeg 9.0.2), Python 3.11-3.13 | all six jobs pass, including a render from the built wheel on each (2026-11-09) |
| Ubuntu 24.04 (WSL2), Python 3.13, FFmpeg **9.0.2** on PATH | the FFmpeg end-to-end tests pass (15 passed, 1 skipped) |

## Clay films: what was run, and where

Clay films need Blender and minutes of rendering, so they are checked on a real machine as well as
by the test suite. On 2026-11-11, on an Intel Core i7-10750H with a GeForce GTX 1660 Ti (6 GB),
Blender 5.2.2 under WSL2:

| Check | Result |
|---|---|
| The test suite, `pytest -o addopts='' -q`, with Blender and FFmpeg present | 318 passed, 1 skipped (the opt-in paid-API test) |
| `tests/test_clay_smoke.py` with Blender present: sculpt two characters, film two drawings of a sample shot, check they are not blank, film again and see it reused | PASS, 41 s |
| The suite with FFmpeg and Blender hidden from `PATH` | PASS: the FFmpeg and Blender tests skip with a reason, none fails |
| CI: lint, tests, package build and a render from the wheel, Ubuntu and Windows, Python 3.11 to 3.13 | PASS |
| The sample film at `preview`, every shot filmed from nothing (17 shots, 666 drawings) | PASS: 82.25 s, 1,974 frames, -16.0 LUFS, 55 min 11 s (2026-11-12, after the eyeline fix); frames looked at shot by shot |
| Eyelines in the office scene, where Bashir's desk is behind Tara | PASS: her body turns -0.68 rad towards him (it stood at 0 before the fix); the projected eyeball axes and the rendered irises in the reaction close-up both point his way |
| Solid contact on the sample, `tools/check_contacts.py` sampling every sixth drawing of all 17 shots (116 drawings) | PASS: 0 intersections (192 in the render before the chair, route and grip fixes); the sample filmed again from nothing with them, 82.25 s, 1,974 frames (2026-11-12, sharing the machine with a second film, so not timed) |
| The same film after a change to its last shot | 16 shots reused by content, 1 filmed, 3 min 17 s |
| `sastudio` killed with SIGKILL while Blender was at drawing 14 of 21 of a new shot | PASS: no Blender left running; the next run said "21 drawings (14 already done)" and finished the shot |
| A shot renumbered by an edit to the plan | PASS: reused from its old folder ("filmed as ..."); a half-filmed one carried on ("28 already done") |
| Framing fixes, on drafts and in the sample | the cafe wide keeps the speaker inside the frame; an over-the-shoulder that would show the speaker's back is filmed as a two-shot or a medium; close-ups and reactions leave room in front of the face |
| Cutting inside a line, in the sample | the cut to the listener lands where the speaker's mouth rests; the speaker's name tag leaves before the cut |
| `direction.light`, a line's `beats`, an `insert` on a prop and `direction.clock`, each filmed at `draft` in a copy of the sample | looked at: the tuned close-up is lit from a low warm key on the other side; the nod and the worried face land at 40 % and 75 % of the line; the insert films the cafe's sign; the home office clock reads 07:05 |
| Every set as an establishing shot; six described characters with every new garment and hair style | rendered and looked at (earlier session) |
| An imported rigged glTF model as a character: fitted, grounded, portrait rendered | PASS (earlier session) |
| Blender for Windows from WSL2 (OptiX) on the same job | UNVERIFIED: recorded as passing for an eight-drawing shot, but a later operator log contradicts it; re-run before relying on it |

Not run: a clay film on native Windows or macOS; the `final` (1920x1080) preset for a whole film;
Hindi dialogue in a clay film judged by a native listener.

## Results for 0.4.0

On 2026-11-13 and 14, on the same laptop (Intel Core i7-10750H, GeForce GTX 1660 Ti 6 GB, Blender 5.2.2 under
WSL2):

| Check | Result |
|---|---|
| `pytest -m "not blender"` | 533 passed, 1 skipped (the opt-in paid-API test) on Python 3.13; 532 passed, 2 skipped on 3.11 (the same, and one that needs scipy) |
| `tests/test_sound.py` (meter, limiter, ducking, crossfades, placement, cues, bad files, encoded loudness, audio-only rebuilds) | 29 passed on Python 3.13 and 3.11 |
| The Blender tests (`pytest -m blender`): sculpting and filming two drawings, feet that never slide or swivel, turns, a new direction replacing the old plan, turning back mid-stride, blinking, two walkers, sitting and getting up, an imported model, the sounds of the staging scenes read from their plans, a walking foot never hovering over a lower floorboard, a shot on one person seeing their face past everyone else, and every drawing of the staging project | 15 passed on the release engine (`327005d`), in 32 and 19 minutes. Measuring every second drawing, the staging check read a step taken between two measured drawings as a 20 cm slide (the same with the engine before this release's last fix); it measures every drawing now, as filming does |
| Every drawing of four projects, posed and measured (`sastudio check`): the staging project (`tests/data/staging`: three bodies on a sofa, chairs, a bench and pupils' chairs, getting up, walking in and out, a phone, a mug, a desk), Nineteen Thirty, The Fast One and Held Door | 71 shots, 3,672 drawings: 0 contacts (238 in the staging project before this release's last fixes). The two camera fixes that came after move three shots of the staging project and two of Held Door, so those were measured again, every drawing: 0 contacts. The floorboard fix after them acts only on a drawing the check would refuse, so it moves nothing in these |
| The `india` template as `init` makes it, the clay film the README shows: every second drawing of its 58 planned shots, posed and measured | 1,753 drawings: 0 contacts. The `starter`, `short` and `education` templates film drawn by default and nobody in them walks, sits or stands up; they were not checked in clay |
| Nineteen Thirty in English at `preview`, filmed from nothing | 19 shots, 1,050 drawings, each measured before it was drawn: 0 contacts. 107.4 s of film; 2 h 46 min, with a second film rendering for an hour of it; 2.9 GB at most. Sound: -16.0 LUFS, -2.0 dBTP, both targets met |
| Held Door at `preview`, filmed from nothing after the camera fixes | 14 shots, 510 drawings, each measured before it was drawn: 0 contacts. 68.8 s of film; 1 h 11 min, with other checks rendering beside it; 3.1 GB at most. Sound: -17.1 LUFS (its target, -17), -1.9 dBTP |
| A new user on Python 3.11, from the built wheel, with the README's India commands: `init --template india`, `doctor`, `validate --strict`, `check` of one scene, and that scene filmed in clay at `draft` in Hindi with Kokoro voices | `validate`: 0 errors, 0 warnings. `check`: 10 shots, 521 drawings, 0 contacts. The film: 11 shots, each measured before it was drawn, 0 contacts; 54.1 s at 960x540, -16.0 LUFS, -2.0 dBTP; 37 min 46 s; 2.6 GB at most |

## Edge cases

**PASS** = covered by an automated test or a command run for this release. **UNVERIFIED** = not
tested yet. **BLOCKED** = needs something outside the project (a paid account, a published
release). **N/A** = does not apply to 0.1 (for example, clay-only cases). Test names refer to
functions in `tests/`.

### Configuration

| Case | Status | Evidence |
|---|---|---|
| Missing project or file | PASS | `test_missing_project` |
| Invalid schema, unknown setting, wrong format version | PASS | `test_unknown_setting_rejected`, `test_wrong_schema_version` |
| Unknown character in a line or token | PASS | `test_unknown_speaker_and_token` |
| Empty or NUL-containing paths | PASS | `test_nul_and_empty_rejected` |
| Extremely long values | PASS | `test_extremely_long_values_rejected` |
| Duplicate ids and display names | PASS | `test_duplicate_ids_and_names` |
| Unicode, multi-word and punctuated names | PASS | `test_unicode_multiword_and_punctuated_names` |
| Unsupported language code | PASS | `test_unsupported_language_code_rejected` |
| Unsupported preset | PASS | `sastudio render --preset ultra` is refused by the command line; the schema allows only the three presets |
| Missing asset | PASS | `validate` reports "does not exist" with the expected location |
| Absolute paths, `..`, symbolic links leaving the project | PASS | `test_unsafe_paths_rejected`, `test_absolute_logo_is_an_error`, `test_symlink_escape_rejected`, `test_scene_file_traversal_rejected` |
| Paths with spaces and Windows separators | PASS | `test_relative_paths_with_spaces_and_backslashes`; native Windows run |
| Unsupported file extension | PASS | `test_logo_wrong_extension` |
| Damaged image | PASS | `test_corrupt_image_is_a_validation_error` |
| Disabled or misordered scene dependency | PASS | `test_disabled_dependency_is_an_error`, `test_dependency_order` |
| Two projects sharing state | PASS | `test_two_projects_do_not_share_state` |
| YAML anchors, aliases and oversized files | PASS | `test_yaml_aliases_rejected`, `test_oversized_file_rejected` |

### Voice providers

| Case | Status | Evidence |
|---|---|---|
| Missing key, or no budget, for a live run | PASS | `test_live_needs_budget_and_key` |
| Invalid or expired key (401/403) | PASS | `test_sarvam_errors`, `test_elevenlabs_errors` (recorded responses) |
| Out of credits (402), no retry | PASS | `test_retry_then_success_and_no_retry_on_402` |
| Rate limiting (429) with retry | PASS | `test_sarvam_errors`, `test_elevenlabs_errors`, `test_retry_then_success_and_no_retry_on_402` |
| Provider down (5xx) and retry exhaustion | PASS | `test_retry_exhaustion` |
| Timeout, counted against the budget | PASS | `test_timeout_counts_against_budget` |
| Network disconnected | PASS | `test_network_failures_become_retryable_provider_errors` |
| Invalid model, removed voice | PASS | `test_sarvam_validation`, `test_elevenlabs_validation`, `test_elevenlabs_errors` |
| Unsupported language or parameter for a model | PASS | `test_sarvam_validation`, `test_elevenlabs_request_shape` |
| Empty, corrupt or truncated audio | PASS | `test_sarvam_empty_and_corrupt_audio`, `test_streamed_wav_header_is_repaired_and_cache_validation_rejects_lies` |
| Line longer than the model accepts | PASS | `test_sarvam_text_limit` |
| Duplicate billable requests, resume after failure | PASS | `test_identical_lines_requested_once`, `test_live_generation_caches_and_is_idempotent` |
| Two generation runs at once | PASS | `test_lock_blocks_concurrent_runs` |
| A dry run never calls a paid provider | PASS | `test_dry_run_never_calls_paid_provider` |
| Changed provider response format | UNVERIFIED | parse errors are mapped to provider errors, but no test simulates a schema change |
| Mixed providers in one film | UNVERIFIED | every line is converted to mono 48 kHz and levelled; not tested with real provider audio |
| Real Sarvam and ElevenLabs requests | BLOCKED | needs a paid account and an authorised budget; not run for this release |

### Dialogue

| Case | Status | Evidence |
|---|---|---|
| Renamed characters, everywhere and nowhere else | PASS | `test_rename_changes_every_reference_and_nothing_else`, `test_rename_in_project_file_flows_everywhere`, `examples/quillmere` |
| Identical display names | PASS | `test_duplicate_ids_and_names` (warning) |
| Hindi script, mixed Hindi and English | PASS | the Hindi example film; `test_hindi_output_survives_a_legacy_console_encoding` |
| Abbreviations, emails, URLs | PASS | `test_speech_normalisation`, `test_org_fields_emails_and_localization` |
| Numbers and dates | UNVERIFIED | passed to providers as written (documented); no normalisation |
| Pronunciation overrides per provider | PASS | `test_provider_pronunciation_hints`, `test_elevenlabs_phoneme_only_where_supported`, `test_names_never_touched_by_lexicon` |
| Inflected names and gendered grammar | PASS | `test_gender_select`, `test_language_specific_display_form`, `test_pronouns_and_capitals` |
| Dialogue longer than its scene's time limit | PASS | render stops with "Scene X runs 70.5s; its max_seconds is 30" (exit 7) |
| Captions matching audio | PASS | `test_cues_cover_the_line`; cue times come from the real audio |
| Stale cache keys | PASS | `test_cache_key_rules`, `test_cache_key_is_stable` |

### Rendering

| Case | Status | Evidence |
|---|---|---|
| No GPU | PASS | the cards renderer uses only the CPU; `test_doctor_gpu_fallbacks` |
| Damaged stored scene video | PASS | `test_damaged_stored_scene_is_rendered_again` |
| Render interrupted midway | PASS | interrupted with SIGINT after 20 s: finished scenes kept, the next run reused 5 and rendered 9 |
| Frame count and audio length of the finished film | PASS | checked by every build; `test_build_end_to_end` |
| Different output sizes | PASS | `draft`, `preview` and `final` films rendered for this release |
| Subtitle overflow | PASS | `test_wrap_and_chunk_limits`, `test_subtitle_checks_flag_overlap_and_speed` |
| Very long organisation name | PASS | a 104-character name wrapped onto two lines on the title card (frame inspected) |
| Transparent, very wide, very tall logos | PASS | `test_logos_of_any_shape_render` |
| Missing fonts | N/A | fonts are bundled in the package |
| Running out of memory | UNVERIFIED | peak memory is measured and `--jobs` documented; no low-memory test |
| Missing Blender, missing sculpting packages, missing engine files | PASS | each stops with what to install (`test_missing_blender_says_how_to_fix_it`, `test_clay_commands_explain_the_missing_engine`); the engine loads no textures or add-ons |

### Sound

| Case | Status | Evidence |
|---|---|---|
| A music file shorter than the film, at another sample rate, in mono, as MP3 or WAV | PASS | `test_music_of_any_rate_and_layout_is_matched_looped_and_faded`: a 3 s, 44.1 kHz mono track under a 12 s film is looped without a hole and faded in and out |
| A corrupt sound file; a missing one | PASS | `test_a_bad_sound_file_is_named_not_mixed`; `sastudio validate` names a missing music file and where it looked |
| Music while somebody speaks, and in the pauses | PASS | `test_music_dips_under_speech_recovers_in_pauses_and_never_jumps`, `test_a_pause_between_words_does_not_bring_the_music_up` |
| One music cue or place crossing into the next | PASS | `test_an_equal_power_crossfade_keeps_two_beds_at_the_same_level`, `test_ambience_crosses_from_one_place_to_the_next_without_a_hole` |
| A short effect at any frame | PASS | `test_an_effect_is_placed_on_its_exact_sample`, `test_a_sound_lands_on_the_drawing_that_first_shows_its_cause` |
| The same action in two overlapping shots; a cue for a sound the motion already makes | PASS | `test_one_action_is_one_sound_and_a_cue_wins_over_the_motion` |
| The same film built twice | PASS | `test_event_identities_are_stable`, `test_the_mix_is_dialogue_first_and_the_same_every_time`, `test_no_two_steps_sound_the_same_and_each_is_made_the_same_way_twice` |
| A loudness target the true-peak ceiling will not allow | PASS | `test_mastering_reaches_the_target_or_says_why`: the build says the target would take heavy limiting instead of claiming it |
| Peaks between samples | PASS | `test_true_peaks_are_found_between_samples`, `test_the_limiter_never_lets_a_true_peak_over_the_ceiling` |
| No sound settings at all; a film with no sound | PASS | `test_a_project_without_any_sound_settings_still_builds_a_mastered_film`, `test_a_silent_film_stays_silent` |
| What people hear: the encoded film, not the mix before it | PASS | `test_the_encoded_film_measures_what_its_manifest_says_and_meets_its_targets` |
| Only the sound changed | PASS | `test_changing_only_the_sound_renders_no_scene_again` |
| A build stopped while writing sound | PASS | `test_wav_files_are_written_whole` |
| A direction the plan drops (told to sit, sent away before arriving) | PASS | `test_sounds_come_from_what_the_engine_animates` (Blender): no sit is heard |
| Laughter, sighs and breaths; picking things up and putting them down | N/A | not made ([#36](https://github.com/xIBBAx/clayvoyant/issues/36), [#35](https://github.com/xIBBAx/clayvoyant/issues/35)) |

### Files and folders

| Case | Status | Evidence |
|---|---|---|
| Read-only folder, permission denied | PASS | real read-only output folder: plain error and fix, exit 1; `test_filesystem_errors_are_explained_not_dumped` |
| Disk full | PASS (simulated) | `test_filesystem_errors_are_explained_not_dumped`; a real full disk was not tested |
| Existing output, non-empty `init` folder | PASS | `test_cli_init_refuses_non_empty`; outputs are written atomically |
| Writes outside the project | PASS | `test_output_outside_project_refused`, `test_output_dir_protected` |
| Long and unusual file names | PASS | `test_safe_name` |
| Windows drives under WSL (`/mnt/d`) | PASS | the repository and tests ran from `/mnt/d` |
| Case-insensitive file systems | UNVERIFIED | |
| Archives | N/A | the tool reads and writes no archives |

### Distribution

| Case | Status | Evidence |
|---|---|---|
| Broken links and missing files in the docs | PASS | `test_relative_links_resolve`, `test_docs_mention_only_commands_that_exist` |
| README images without alt text | PASS | `test_every_readme_image_has_alt_text` |
| Clean clone, install and render | PASS | `git clone` from GitHub into an empty folder: `uv sync --frozen`, `init`, `validate --strict`, a draft scene; the README's `pip install -e .` path rendered the whole starter film as a draft in 51 s (227 MB peak) |
| `init` with the organisation's details | PASS | `tests/test_init_options.py`: values with quotes and Devanagari round-trip, comments stay, logo converted to PNG, every bad option rejected before anything is created, all three templates; a fresh `init --style v3` project rendered the whole starter as a draft in 60 s |
| Drawn character styles (v1-v3) | PASS | `tests/test_figures.py`: every bundled character in every style, every documented hair, outfit, shoe and extra, determinism, face-only variants, schema accept/reject, unchanged cache keys for existing projects, talking and blinking on twos, the `--sheet` command, a full render; every style and option was also checked by eye |
| Colour tags with newer FFmpeg | PASS | FFmpeg 9 dropped BT.709 primaries and transfer; frames are now tagged with `setparams` (found by the Windows CI run, reproduced locally with 9.0.2, byte-identical output on 6.1) |
| Secrets in the tree | PASS | gitleaks 8.30.1: no leaks; the history scan runs in CI |
| Credentials in logs and output | PASS | `test_cli_credentials_never_prints_values`; keys are never written |
| Metadata in published images | PASS | every PNG and the GIF checked: no text, EXIF or time chunks |
| Known vulnerable dependencies | PASS | pip-audit 2.10.1 on the lock file: none |
| CI permissions and untrusted pull requests | PASS | read-only permissions, no `pull_request_target`, no secrets; actionlint and zizmor report nothing |
| Release links and assets online | PASS | 2026-11-09, without logging in: the repository, the [v0.1.0 release](https://github.com/xIBBAx/clayvoyant/releases/tag/v0.1.0) and every GitHub link in the docs return 200; `git clone` works; all 18 release files downloaded and match `MEDIA_SHA256SUMS` (14) and `SHA256SUMS` (2) |
