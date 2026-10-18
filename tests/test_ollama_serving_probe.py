"""The nightly's Ollama serving probe must be able to fail (bamr87/bamr87#253).

Driven against an in-process fake ``/api/generate`` so it is deterministic and
needs no model: a fast answer passes; a slow one, an empty one, an HTTP error
and a closed port each fail with exit 1.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ollama_serving_probe.py"
_spec = importlib.util.spec_from_file_location("ollama_serving_probe", _PATH)
assert _spec and _spec.loader
probe_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe_mod)


def _serve(behaviour: dict) -> tuple[str, ThreadingHTTPServer]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            behaviour["seen"] = json.loads(self.rfile.read(length) or b"{}")
            time.sleep(behaviour.get("delay", 0))
            status = behaviour.get("status", 200)
            body = json.dumps(behaviour.get("body", {"response": "A contract binds."}))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


@pytest.fixture()
def fake():
    servers: list[ThreadingHTTPServer] = []

    def make(**behaviour):
        url, server = _serve(behaviour)
        servers.append(server)
        return url, behaviour

    yield make
    for s in servers:
        s.shutdown()


def test_a_model_that_answers_in_time_passes(fake) -> None:
    url, seen = fake()
    assert (
        probe_mod.main(
            ["--url", url, "--model", "m", "--deadline", "5", "--tokens", "8"]
        )
        == 0
    )
    # It asks for a real generation of the requested length, not /api/tags.
    assert seen["seen"]["model"] == "m"
    assert seen["seen"]["options"]["num_predict"] == 8


def test_a_model_slower_than_the_deadline_fails(fake) -> None:
    url, _ = fake(delay=2.0)
    assert probe_mod.main(["--url", url, "--model", "m", "--deadline", "0.5"]) == 1


def test_an_empty_answer_fails(fake) -> None:
    url, _ = fake(body={"response": "   "})
    assert probe_mod.main(["--url", url, "--model", "m", "--deadline", "5"]) == 1


def test_an_http_error_fails(fake) -> None:
    url, _ = fake(status=500, body={"error": "model requires more system memory"})
    ok, why = probe_mod.probe(url, "m", 5, 8)
    assert not ok and "HTTP 500" in why


def test_an_unreachable_server_fails() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    ok, why = probe_mod.probe(f"http://127.0.0.1:{port}", "m", 5, 8)
    assert not ok and "unreachable" in why
