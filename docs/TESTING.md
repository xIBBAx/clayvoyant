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

Clay films need Blender and a few minutes of rendering, so they are checked by hand on a real
machine as well as by the test suite. On 2026-11-11, on an Intel Core i7-10750H with a GeForce
GTX 1660 Ti (6 GB), Blender 5.2.2 under WSL2:

| Check | Result |
|---|---|
| The test suite (jobs, timing, caching, design mapping, sculpting kit, lip sync, free voices, engine contracts) | 280 passed, 1 skipped (the opt-in paid-API test) |
| CI: lint, tests, package build and a render from the wheel, Ubuntu and Windows, Python 3.11 to 3.13 | PASS |
| Wheel contains every engine script; installed into a fresh Python 3.12 environment with the `clay` extra | PASS: `init`, `validate`, `direct`, sculpting a character (19 s) |
| Filming a shot from that fresh installation (`sastudio motion`, 80 drawings, 960x540) | PASS: valid H.264, 159 frames |
| The sample film end to end with `sastudio film --preset draft`: 13 Kokoro lines, 3 sculpts, 14 shots, assembly | PASS: 82.25 s, 1,974 frames, -16.0 LUFS, subtitles and manifest written |
| Every set as an establishing shot; six described characters with every new garment and hair style | rendered and looked at |
| An imported rigged glTF model as a character: fitted, grounded, portrait rendered | PASS |
| Blender for Windows from WSL2 (OptiX) on the same job | UNVERIFIED: recorded as passing for an eight-drawing shot, but a later operator log contradicts it; re-run before relying on it |

Not run: a clay film on native Windows or macOS; the `final` (1920x1080) preset for a whole film;
Hindi dialogue in a clay film judged by a native listener.

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
| Release links and assets online | PASS | 2026-11-09, without logging in: the repository, the [v0.1.0 release](https://github.com/xIBBAx/security-awareness-studio/releases/tag/v0.1.0) and every GitHub link in the docs return 200; `git clone` works; all 18 release files downloaded and match `MEDIA_SHA256SUMS` (14) and `SHA256SUMS` (2) |
