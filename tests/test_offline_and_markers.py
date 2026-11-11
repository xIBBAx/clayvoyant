"""The promises the test suite makes about itself: it never touches the network, and tests that need FFmpeg or
Blender skip, with a reason, on a computer without them."""

from __future__ import annotations

import socket

import pytest

from . import conftest


def test_an_internet_connection_fails_the_test():
    with pytest.raises(conftest.NetworkBlocked):
        socket.create_connection(("192.0.2.1", 443), timeout=1)     # TEST-NET-1: never routable anyway


def test_a_datagram_fails_the_test():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s, pytest.raises(conftest.NetworkBlocked):
        s.sendto(b"x", ("192.0.2.1", 53))


def test_loopback_is_not_the_network():
    import threading

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    t = threading.Thread(target=lambda: srv.accept()[0].close())
    t.start()
    with socket.create_connection(srv.getsockname(), timeout=5):
        pass
    t.join(5)
    srv.close()


def test_local_socket_pairs_still_work():
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"ping")
        assert b.recv(4) == b"ping"


class _Item:
    def __init__(self, *marks):
        self.keywords = set(marks)
        self.added = []

    def add_marker(self, m):
        self.added.append(m)


@pytest.mark.parametrize("mark, flag", [("ffmpeg", "HAS_FFMPEG"), ("blender", "HAS_BLENDER")])
def test_a_missing_program_skips_its_tests(monkeypatch, mark, flag):
    item, other = _Item(mark), _Item()
    monkeypatch.setattr(conftest, flag, False)
    conftest.pytest_collection_modifyitems(None, [item, other])
    assert [m.name for m in item.added] == ["skip"] and "needs" in item.added[0].kwargs["reason"]
    assert other.added == []
    monkeypatch.setattr(conftest, flag, True)
    present = _Item(mark)
    conftest.pytest_collection_modifyitems(None, [present])
    assert present.added == []
