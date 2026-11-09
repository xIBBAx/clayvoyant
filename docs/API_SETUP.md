# API keys

You need an API key for one thing only: generating real voices with Sarvam or ElevenLabs
(`sastudio voices generate --live`). Everything else works without an account:

| Works with no key | Needs a key |
|---|---|
| `init`, `doctor`, `validate`, `scenes`, `characters`, `script` | `voices generate --live` for characters whose voice is `sarvam` or `elevenlabs` |
| `voices plan`, `voices generate` without `--live`, `voices lexicon` | |
| `render` with offline voices, or `--voice-fallback offline` | |
| the whole test suite | |

## 1. Get a key from your provider

- **Sarvam AI**: create an account and an API subscription key as described in the
  [Sarvam documentation](https://docs.sarvam.ai/).
- **ElevenLabs**: create an account and an API key as described in the
  [ElevenLabs documentation](https://elevenlabs.io/docs/).

Use a key for this project only. If your provider lets you restrict a key (for example to
text-to-speech, or to a credit limit), restrict it. Check what each plan allows you to do with the
audio before you publish a film ([ASSET_LICENSES.md](../ASSET_LICENSES.md#speech-you-generate)).

## 2. Give the key to sastudio

Either set environment variables:

```bash
export SARVAM_API_KEY="..."            # Windows PowerShell: $env:SARVAM_API_KEY = "..."
export ELEVENLABS_API_KEY="..."
```

or copy [`.env.example`](../.env.example) to `.env` in your project folder (or the folder you run
`sastudio` from) and fill it in:

```
SARVAM_API_KEY=...
ELEVENLABS_API_KEY=...
```

Rules:

- Environment variables win over `.env`. A `.env` in the project folder wins over one in the
  current folder.
- `.env` is read as plain `KEY=value` lines. Nothing in it is executed or expanded.
- There is no place for a key in `studio.yaml`, on purpose. Keys are never written to project
  files, the voice cache, the ledger, manifests or logs.
- `.env` is ignored by git in this repository. Add `.env` to the `.gitignore` of any repository
  you keep your own project in.

## 3. Check it, without revealing it

```bash
sastudio credentials my-film
```

```
SARVAM_API_KEY: set (18 characters)
ELEVENLABS_API_KEY: (not set)
Keys are only read from the environment or a .env file; they are never written to project files, caches, logs or manifests. This check makes no network request.
```

The command shows only whether a key is set and how long it is. It does not contact the provider,
so a wrong key is only discovered by the first live request. That request fails with "Sarvam (or
ElevenLabs) rejected the API key" and the run stops at once, without retrying.

## 4. Spend safely

Paid requests happen only with `--live` **and** a character budget above zero. Start small:

```bash
sastudio voices plan my-film --scenes first_day
sastudio voices generate my-film --scenes first_day --live --max-characters 300
```

The budget, retries, rate limit, ledger and cache are described in
[VOICE_PROVIDERS.md](VOICE_PROVIDERS.md#generating-speech).

## If a key leaks

Revoke it in your provider's dashboard straight away and create a new one. Deleting a commit,
an issue comment or a screenshot does not un-leak a key: it may already be copied. Never paste a
key into an issue, a pull request, a screenshot or a log, including when asking for help.

## Tests and CI never use keys

The default test suite replays recorded provider responses and never touches the network. The
project's CI has no provider secrets. A test marked `live` exists as an opt-in hook
(`SASTUDIO_LIVE_TESTS=1`); it is skipped unless you enable it yourself.
