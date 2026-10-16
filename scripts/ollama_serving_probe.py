#!/usr/bin/env python3
"""Fail fast unless an Ollama model actually *serves* a generation in time.

bamr87/bamr87#253 (faults 2 & 3). The nightly's "Pull the LegalBench gate
model" step proved a model was *pulled* (``ollama pull`` + ``ollama list``),
never that it *answered*. Stdlib only, so it runs on the bare runner before
any container is built for it.

    python3 scripts/ollama_serving_probe.py --model mistral:7b-instruct-q4_K_M \
        --url http://127.0.0.1:11434 --deadline 120 --tokens 32

Exit 0 when ``/api/generate`` returns a non-empty ``response`` within
``--deadline`` seconds (the whole request, model load included); exit 1 with a
one-line reason otherwise: unreachable, HTTP error, empty answer, or too slow.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def probe(url: str, model: str, deadline_s: float, tokens: int) -> tuple[bool, str]:
    body = json.dumps(
        {
            "model": model,
            "prompt": "Reply with one short sentence about contracts.",
            "stream": False,
            "options": {"num_predict": tokens, "temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=deadline_s) as res:
            payload = json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        return False, f"{model!r} HTTP {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed = time.monotonic() - started
        if elapsed >= deadline_s * 0.95:
            return False, f"{model!r} did not answer within {deadline_s:.0f}s"
        return False, f"ollama unreachable at {url} ({exc})"
    except ValueError as exc:
        return False, f"{model!r} returned a non-JSON body ({exc})"
    elapsed = time.monotonic() - started
    if elapsed > deadline_s:
        return (
            False,
            f"{model!r} answered in {elapsed:.1f}s, over the {deadline_s:.0f}s deadline",
        )
    answer = str(payload.get("response") or "").strip()
    if not answer:
        return False, f"{model!r} returned an empty response: {str(payload)[:200]}"
    return True, f"{model!r} served {tokens} tokens in {elapsed:.1f}s"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument("--deadline", type=float, default=120.0, help="seconds")
    ap.add_argument("--tokens", type=int, default=32)
    args = ap.parse_args(argv)
    ok, why = probe(args.url, args.model, args.deadline, args.tokens)
    print(("ok: " if ok else "::error::ollama serving probe failed: ") + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
