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


# ----------------------------------------------------------------------------------- markers and the network guard
import os  # noqa: E402
import socket  # noqa: E402

HAS_BLENDER = bool(os.environ.get("SASTUDIO_BLENDER")) or shutil.which("blender") is not None


def pytest_collection_modifyitems(config, items):
    """`ffmpeg` and `blender` tests skip, with a reason, on a computer that lacks the program."""
    for item in items:
        if "ffmpeg" in item.keywords and not HAS_FFMPEG:
            item.add_marker(pytest.mark.skip(reason="needs FFmpeg on PATH"))
        if "blender" in item.keywords and not HAS_BLENDER:
            item.add_marker(pytest.mark.skip(reason="needs Blender (set SASTUDIO_BLENDER or put blender on PATH)"))


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """The suite promises it never touches the network: any connection or datagram to an address off this machine
    fails the test. Loopback (127.0.0.0/8, ::1) and Unix sockets are untouched: they never leave the computer, and
    Windows builds socket.socketpair() out of a loopback connection. A test that truly needs the network says so with
    @pytest.mark.network; none does today."""
    if "network" in request.keywords:
        yield
        return
    real_connect, real_connect_ex, real_sendto = socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto

    import ipaddress

    def _off_machine(sock, address) -> bool:
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            return False
        host = address[0] if isinstance(address, tuple) else address
        try:
            return not ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host not in ("localhost",)     # a name to look up is the network

    def connect(self, address):
        if _off_machine(self, address):
            raise NetworkBlocked(f"test tried to connect to {address!r}; tests run offline")
        return real_connect(self, address)

    def connect_ex(self, address):
        if _off_machine(self, address):
            raise NetworkBlocked(f"test tried to connect to {address!r}; tests run offline")
        return real_connect_ex(self, address)

    def sendto(self, *args):
        if _off_machine(self, args[-1]):
            raise NetworkBlocked("test tried to send a datagram off this machine; tests run offline")
        return real_sendto(self, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    yield
