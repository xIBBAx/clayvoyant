# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Use GitHub's
**Report a vulnerability** button on the repository's Security tab, or email
**ibrahimsultan4705@gmail.com** with "Security Awareness Studio" in the subject.

Include what you found, how to reproduce it and what it affects. I will reply as soon as I
can and credit you in the release notes if you would like that.

This address is for vulnerabilities in this software only. It is not an incident-reporting
inbox for any organisation that uses the films made with it.

## Supported versions

Only the latest release receives fixes.

## How the project protects you

- **Project files are untrusted input.** YAML is read with a safe loader that also rejects
  anchors and aliases; file sizes are capped; every path must stay inside the project folder
  (no absolute paths, no `..`, no symbolic links that leave the folder); nothing in a project
  file is executed.
- **No shell.** Every external program (FFmpeg, ffprobe, espeak-ng) is started with an argument
  list, never through a shell. Dialogue reaches espeak-ng through standard input, so
  text can never be read as an option.
- **Projects can't run code.** A project supplies data only: YAML, JSON character parameters,
  images and audio. It cannot supply Python, shell commands or `.blend` files. (The clay renderer
  is not included in 0.1; when it is, Blender runs only the engine script shipped in this
  package.) Do not open `.blend` files from people you don't trust: Blender files can contain
  scripts.
- **API keys stay out of files.** Keys are read from environment variables or a `.env` file,
  never written to project files, caches, the ledger, manifests or logs. `sastudio credentials`
  shows only whether a key is set.
- **No accidental spending.** Paid speech is only requested with `--live` and a character
  budget. Installation, tests, dry runs and CI never call a paid API.
- **HTTPS only** for provider requests, with certificate checks.
- **CI** ([`.github/workflows/`](.github/workflows/)) runs with read-only repository
  permissions, is never triggered by `pull_request_target`, receives no secrets, and pins every
  third-party action to a full commit SHA. Every push and pull request is scanned for secrets
  (gitleaks) and the locked dependencies are audited for known vulnerabilities (pip-audit).
  Release builds run only from a version tag pushed by a maintainer.

## If you leak a key

Revoke it in the provider's dashboard straight away (Sarvam: API dashboard; ElevenLabs:
profile, API keys), then create a new one. Deleting a commit does not un-leak a key.
