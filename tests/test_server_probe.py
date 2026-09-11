"""Detecting an absent local server must be cheap, and still correct.

`aihwbench runtimes` took 24 seconds on the reference machine, and 16 of those
were spent waiting for four HTTP servers that were not running. The cause is
how slowly this platform says no: a TCP connect to a *closed* port on
127.0.0.1 takes 2.0 seconds before it refuses, and `localhost` resolves to two
addresses, so each absent server cost about four seconds. Nothing was wrong
with the code; it was politely waiting.

The fix is a short-timeout TCP pre-flight before the HTTP request, and the two
things that could go wrong with it are what these tests cover:

- It must not report a *running* server as absent. That would be a silent
  downgrade, turning a usable backend into "not installed" — much worse than
  the slowness it replaces.
- Each backend must actually consult it. A helper nothing calls is the defect
  this repository keeps finding.

The probe lives inside each backend's `_api_get`, not in its `detect()`. The
first attempt put it in the caller, which worked and broke a test that mocked
`_api_get` to stand for a running server. That was the right signal rather than
a nuisance: if `_api_get` is where "talk to the server" lives, it is where "is
the server there" belongs, and tests keep one seam instead of two.

Deliberately not tested: that the probe is fast. That assertion would measure
the CI runner's scheduler, and a timing test which fails when a machine is busy
is a test people learn to re-run rather than read.
"""

from __future__ import annotations

import socket
from contextlib import closing

import pytest

from aihwbench.backends import lemonade, lmstudio, ollama, openai_server
from aihwbench.backends.base import RuntimeStatus, server_is_listening


@pytest.fixture
def listening_port():
    """A real socket, actually accepting connections."""
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        yield sock.getsockname()[1]


def test_a_listening_port_is_found(listening_port):
    """The failure that matters: reporting a running server as absent."""
    assert server_is_listening(f"http://127.0.0.1:{listening_port}") is True


def test_a_closed_port_is_not(listening_port):
    """Bound, then released: the same port with nothing behind it."""
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        closed = sock.getsockname()[1]
    assert server_is_listening(f"http://127.0.0.1:{closed}") is False


def test_the_port_is_read_from_the_url(listening_port):
    """A probe that fell back to port 80 would answer about something else."""
    assert server_is_listening(f"http://127.0.0.1:{listening_port}") is True
    assert server_is_listening(f"http://127.0.0.1:{listening_port + 1}") is False


def test_a_bare_host_and_port_still_parses(listening_port):
    """Callers pass `http://host:port`, but a bare `host:port` must not be
    read as a path and silently probed on port 80."""
    assert server_is_listening(f"127.0.0.1:{listening_port}") is True


def test_a_url_with_no_host_is_not_listening():
    assert server_is_listening("") is False


# --- every backend actually consults it -------------------------------------


def test_ollama_does_not_open_a_request_when_nothing_is_listening(monkeypatch):
    """`urlopen` must not be reached: that call is the four seconds."""
    monkeypatch.setattr(ollama, "server_is_listening", lambda *a, **k: False)
    monkeypatch.setattr(
        ollama.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("HTTP request made despite no listener"),
    )
    monkeypatch.setattr(ollama, "run_command", lambda *a, **k: (0, "ollama version is 0.0.0"))
    info = ollama.detect()
    assert info.status is RuntimeStatus.CONFIGURATION_REQUIRED


def test_lmstudio_does_not_open_a_request_when_nothing_is_listening(monkeypatch):
    monkeypatch.setattr(lmstudio, "server_is_listening", lambda *a, **k: False)
    monkeypatch.setattr(
        lmstudio.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("HTTP request made despite no listener"),
    )
    assert lmstudio.detect().status is RuntimeStatus.NOT_INSTALLED


def test_openai_servers_do_not_open_a_request_when_nothing_is_listening(monkeypatch):
    """One patch covering vLLM and SGLang, which share this detection."""
    monkeypatch.setattr(openai_server, "server_is_listening", lambda *a, **k: False)
    monkeypatch.setattr(
        openai_server.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("HTTP request made despite no listener"),
    )
    # The real vLLM server descriptor, so this cannot pass against a shape the
    # backends do not use.
    from aihwbench.backends import vllm

    info = openai_server.detect_server(vllm.SERVER)
    assert info.status is RuntimeStatus.NOT_INSTALLED
    assert info.detail == vllm.SERVER.install_hint


def test_lemonade_health_returns_none_without_a_listener(monkeypatch):
    monkeypatch.setattr(lemonade, "server_is_listening", lambda *a, **k: False)
    assert lemonade._health() is None


def test_a_listening_server_is_still_asked(monkeypatch):
    """The pre-flight must gate the request, not replace it.

    A backend that reported AVAILABLE on an open socket alone would call any
    process holding that port an inference server.
    """
    asked: list[str] = []

    def fake_get(path, *a, **k):
        asked.append(path)
        return {"data": [{"id": "some-model"}]}

    monkeypatch.setattr(lmstudio, "_api_get", fake_get)
    info = lmstudio.detect()
    assert asked == ["/v1/models"]
    assert info.status is RuntimeStatus.AVAILABLE
