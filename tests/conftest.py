import shutil
import textwrap
from pathlib import Path

import pytest

from sastudio.voices.base import HttpResponse

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


MINIMAL = """
schema_version: 1
project:
  title: "Test Film"
  language: en-IN
  languages: {languages}
organization:
  name: "Test Org"
  security_email: "security@example.com"
  reporting_url: "https://example.com/report"
characters:
  - id: ana
    name: Ana
    pronouns: she
    gender: feminine
    voice: {{ provider: offline, settings: {{ rate: 200 }} }}
  - id: dev
    name: Dev
    pronouns: he
    gender: masculine
    voice: {{ provider: {dev_provider} {dev_extra} }}
scenes:
  - id: one
    title: "Scene One"
    lines:
      - {{ id: l1, who: ana, say: "Hello {{dev}}, check the device." }}
      - {{ id: l2, who: dev, say: "Report to {{org.security_email}}." }}
  - id: two
    title: "Scene Two"
    requires: [one]
    lines:
      - {{ id: l3, card: {{ text: "Lock your screen.", seconds: 1 }} }}
      - {{ id: l4, who: ana, say: "Thanks, {{dev}}." }}
voices:
  providers:
    offline: {{ engine: silence }}
  budget: {{ max_characters: {budget}, max_requests: 50, max_retries: 2, requests_per_minute: 1000 }}
render:
  preset: draft
  output: build
  burn_subtitles: true
"""


def write_project(root: Path, *, languages="[en-IN]", dev_provider="offline", dev_extra="", budget=0, extra="") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    text = MINIMAL.format(languages=languages, dev_provider=dev_provider, dev_extra=dev_extra, budget=budget)
    (root / "studio.yaml").write_text(textwrap.dedent(text) + extra, encoding="utf-8")
    return root


@pytest.fixture
def project_dir(tmp_path):
    return write_project(tmp_path / "proj")


class FakeTransport:
    """Records requests and replays canned responses. Never touches the network."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def wav_bytes(seconds=0.5, rate=24000):
    import math
    import struct

    from sastudio.voices.base import pcm_to_wav

    n = int(seconds * rate)
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(i / 8.0))) for i in range(n))
    return pcm_to_wav(pcm, rate)


def ok_wav(seconds=0.5):
    return HttpResponse(200, {"content-type": "audio/wav", "request-id": "req-1"}, wav_bytes(seconds))
