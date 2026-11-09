"""Plan and generate dialogue audio.

Safety rules (see docs/VOICE_PROVIDERS.md):

* Nothing billable happens unless the caller passes live=True AND a character budget > 0.
* Audio is cached by a hash of every non-secret input that changes the sound. A line is never
  requested twice, so re-running after a failure continues where it stopped.
* The budget counts characters before each request; a request that would cross it is not sent.
* Failed requests are retried only for errors the provider marks as temporary (rate limits,
  5xx). Out-of-credit and bad-key errors stop the run at once.
* A timed-out request may still have been billed, so its characters count against the budget.
* One generation run per project at a time (lock file).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import BudgetExceeded, MissingCredential, ProviderError, StudioError
from ..safepath import atomic_write_bytes, atomic_write_text
from .base import Audio, PreparedRequest, RetryPolicy, Transport, Utterance, check_wav, urllib_transport
from .registry import get_provider, set_provider_configs

STATE_DIR = ".studio"


# --------------------------------------------------------------------------- env
def load_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. No shell expansion, no command substitution, no export side effects."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k.replace("_", "").isalnum() and k[:1].isalpha():
            out[k] = v
    return out


def credentials(project_root: Path, env_file: Path | None = None) -> dict[str, str]:
    env = {}
    for p in ([env_file] if env_file else [project_root / ".env", Path.cwd() / ".env"]):
        if p and p.is_file():
            for k, v in load_env_file(p).items():
                env.setdefault(k, v)
    for k in ("SARVAM_API_KEY", "ELEVENLABS_API_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def redact(value: str | None) -> str:
    if not value:
        return "(not set)"
    return f"set ({len(value)} characters)"


# --------------------------------------------------------------------------- plan
@dataclass
class PlanItem:
    utt: Utterance
    spec: object
    req: PreparedRequest
    key: str
    path: Path
    cached: bool
    advice: list[str] = field(default_factory=list)


@dataclass
class Plan:
    items: list[PlanItem]
    cache_dir: Path

    def unique_pending(self) -> list[PlanItem]:
        seen, out = set(), []
        for it in self.items:
            if not it.cached and it.key not in seen:
                seen.add(it.key)
                out.append(it)
        return out

    def summary(self) -> dict[str, dict]:
        s: dict[str, dict] = {}
        pending_keys = {it.key for it in self.unique_pending()}
        for it in self.items:
            p = s.setdefault(it.req.provider, {"lines": 0, "cached": 0, "to_generate": 0, "characters": 0,
                                               "models": {}, "_keys": set()})
            p["lines"] += 1
            if it.cached:
                p["cached"] += 1
            elif it.key in pending_keys and it.key not in p["_keys"]:
                p["_keys"].add(it.key)
                p["to_generate"] += 1
                p["characters"] += it.req.characters
                model = it.req.fields.get("model") or it.req.fields.get("model_id") or it.req.fields.get("engine")
                p["models"][model] = p["models"].get(model, 0) + it.req.characters
        for p in s.values():
            p.pop("_keys")
        return s

    def cost(self, prices: dict) -> list[dict]:
        rows = []
        for provider, info in self.summary().items():
            for model, chars in info["models"].items():
                price = ((prices or {}).get(provider) or {}).get(model)
                row = {"provider": provider, "model": model, "characters": chars}
                if price:
                    row["estimate"] = round(chars / 1000.0 * price["per_1000_characters"], 4)
                    row["currency"] = price["currency"]
                    row["price_checked"] = price.get("checked", "not stated")
                rows.append(row)
        return rows


def cache_key(req: PreparedRequest, language: str) -> str:
    payload = {**req.cache_payload(), "language": language}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_path(cache_dir: Path, provider: str, key: str) -> Path:
    return cache_dir / provider / key[:2] / f"{key}.wav"


def cached_ok(path: Path) -> bool:
    try:
        check_wav(path.read_bytes())
        return True
    except (OSError, ProviderError):
        return False


def iter_utterances(project, langs: Iterable[str], scene_ids: Iterable[str] | None):
    for lang in langs:
        for scene in project.enabled_scenes(scene_ids):
            for ln in scene.lines:
                if ln.is_card or not ln.who:
                    continue
                tmpl = ln.template_for(lang, project.language, project.fallback)
                if tmpl is None:
                    continue
                resolved = project.resolve(tmpl, lang)
                override = ln.spoken.get(lang) or (ln.spoken.get("default") if lang == project.language else None)
                yield Utterance(ln.id, scene.id, lang, ln.who, resolved, override=override)


def build_plan(project, langs: Iterable[str] | None = None, scene_ids: Iterable[str] | None = None,
               fallback_provider: str | None = None) -> Plan:
    from . import sarvam  # advice helper

    configs = project.provider_defaults()
    set_provider_configs(configs)
    cache_dir = project.root / STATE_DIR / "cache" / "voices"
    items = []
    for utt in iter_utterances(project, langs or project.languages, scene_ids):
        spec = project.characters[utt.character_id].voice_for(utt.language, configs)
        if fallback_provider and spec.provider != fallback_provider:
            from ..project import VoiceSpec

            spec = VoiceSpec(provider=fallback_provider)
        provider = get_provider(spec.provider, configs.get(spec.provider))
        req = provider.prepare(utt, spec, project.speech)
        key = cache_key(req, utt.language)
        path = cache_path(cache_dir, req.provider, key)
        advice = []
        if req.provider == "sarvam":
            a = sarvam.advice(req.text, utt.language)
            if a:
                advice.append(a)
        items.append(PlanItem(utt, spec, req, key, path, path.exists() and cached_ok(path), advice))
    return Plan(items, cache_dir)


# --------------------------------------------------------------------------- generate
@dataclass
class RunReport:
    generated: int = 0
    reused: int = 0
    skipped_paid: int = 0
    characters_billed: int = 0
    requests: int = 0
    failures: list[str] = field(default_factory=list)


class _Lock:
    def __init__(self, path: Path, stale_after: float = 6 * 3600):
        self.path, self.stale_after = path, stale_after

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, json.dumps({"pid": os.getpid(), "time": time.time()}).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text())
                    if time.time() - float(info.get("time", 0)) > self.stale_after:
                        self.path.unlink()
                        continue
                except (OSError, ValueError):
                    pass
                raise StudioError("Another voice generation run is active for this project.",
                                  f"Wait for it to finish, or delete {self.path} if no run is active.")
        raise StudioError("Could not take the voice generation lock.")

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def generate(project, plan: Plan, *, live: bool = False, max_characters: int | None = None,
             max_requests: int | None = None, transport: Transport = urllib_transport,
             env: dict[str, str] | None = None, retry: RetryPolicy | None = None,
             log: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic) -> RunReport:
    budget_cfg = (project.voices_cfg.get("budget") or {})
    max_characters = budget_cfg.get("max_characters", 0) if max_characters is None else max_characters
    max_requests = budget_cfg.get("max_requests", 200) if max_requests is None else max_requests
    timeout = float(budget_cfg.get("timeout_seconds", 60))
    rpm = float(budget_cfg.get("requests_per_minute", 30))
    retry = retry or RetryPolicy(max_retries=int(budget_cfg.get("max_retries", 3)), sleep=sleep)
    env = env if env is not None else credentials(project.root)
    configs = project.provider_defaults()
    report = RunReport()
    report.reused = sum(1 for it in plan.items if it.cached)
    pending = plan.unique_pending()

    paid = [it for it in pending if get_provider(it.req.provider, configs.get(it.req.provider)).billable]
    free = [it for it in pending if it not in paid]
    if paid and live:
        need = sum(it.req.characters for it in paid)
        if not max_characters or max_characters <= 0:
            raise BudgetExceeded(
                f"Live generation needs a character budget; this run would send {need:,} characters.",
                "Pass --max-characters N or set voices.budget.max_characters in studio.yaml.",
            )
        missing = sorted({get_provider(it.req.provider).key_env for it in paid
                          if not env.get(get_provider(it.req.provider).key_env or "")})
        if missing:
            raise MissingCredential(f"Missing API key(s): {', '.join(missing)}.",
                                    "Copy .env.example to .env and add your own keys. See docs/API_SETUP.md.")

    ledger = project.root / STATE_DIR / "ledger.jsonl"
    with _Lock(project.root / STATE_DIR / "voices.lock"):
        for it in free:
            _one(project, it, None, transport, timeout, retry, report, ledger, log, billable=False)
        if paid and not live:
            report.skipped_paid = len(paid)
            return report
        last = None
        for it in paid:
            if report.characters_billed + it.req.characters > max_characters:
                raise BudgetExceeded(
                    f"Stopped before {it.utt.line_id}: {report.characters_billed:,} characters used, "
                    f"next line needs {it.req.characters}, budget {max_characters:,}.",
                    "Finished lines are cached. Raise the budget to continue.",
                )
            if report.requests >= max_requests:
                raise BudgetExceeded(f"Stopped after {report.requests} requests (max_requests).",
                                     "Finished lines are cached. Raise max_requests to continue.")
            if last is not None:
                wait = 60.0 / rpm - (clock() - last)
                if wait > 0:
                    sleep(wait)
            last = clock()
            key = env.get(get_provider(it.req.provider).key_env or "")
            _one(project, it, key, transport, timeout, retry, report, ledger, log, billable=True)
    return report


def _one(project, it: PlanItem, key, transport, timeout, retry: RetryPolicy, report: RunReport, ledger: Path,
         log, *, billable: bool) -> None:
    provider = get_provider(it.req.provider, project.provider_defaults().get(it.req.provider))
    attempt = 0
    while True:
        if billable:
            report.requests += 1
        try:
            audio: Audio = provider.synthesize(it.req, key=key, transport=transport, timeout=timeout)
        except ProviderError as e:
            charged = billable and e.code == "timeout"
            if charged:
                report.characters_billed += it.req.characters  # may have been billed; count it
            _ledger(ledger, it, "error", billable, e.status, e.code, None, charged)
            if e.retryable and attempt < retry.max_retries:
                delay = retry.delay(attempt, e.retry_after)
                log(f"  {it.utt.line_id}: {e.message} - retry {attempt + 1}/{retry.max_retries} in {delay:.1f}s")
                retry.sleep(delay)
                attempt += 1
                continue
            raise ProviderError(f"{it.req.provider} failed on {it.utt.line_id}: {e.message}", e.hint,
                                status=e.status, code=e.code)
        from .base import repair_wav

        audio.data = repair_wav(audio.data)
        check_wav(audio.data)
        atomic_write_bytes(it.path, audio.data)
        meta = {"line": it.utt.line_id, "language": it.utt.language, "provider": it.req.provider,
                "text": it.req.text, "fields": it.req.fields, "request_id": audio.request_id,
                "seconds": round(audio.duration(), 3), "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        atomic_write_text(it.path.with_suffix(".json"), json.dumps(meta, ensure_ascii=False, indent=1))
        if billable:
            report.characters_billed += it.req.characters
        report.generated += 1
        _ledger(ledger, it, "ok", billable, 200, None, audio.request_id, billable)
        log(f"  {it.utt.line_id} [{it.utt.language}] {it.req.provider}: {meta['seconds']}s")
        it.cached = True
        return


def _ledger(path: Path, it: PlanItem, status: str, billable: bool, http: int | None, code: str | None,
            request_id: str | None, counted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "line": it.utt.line_id,
           "language": it.utt.language, "provider": it.req.provider, "key": it.key,
           "characters": it.req.characters if billable else 0, "counted": counted, "status": status,
           "http": http, "code": code, "request_id": request_id}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
