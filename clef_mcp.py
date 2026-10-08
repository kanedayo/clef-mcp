#!/usr/bin/env python3
"""MCP server exposing Cloudflare Clef (an Ollama-hosted Jev-compatible
"System One" decision model) to Claude Code.

Clef answers typed questions (noul / choice / score) about a given state
with calibrated probabilities in one fast pass — no prose generation.
This server wraps the Ollama `POST /v1/systemone` endpoint so Claude Code
can request decisions without managing curl calls.

Environment variables:
  CLEF_BASE_URL   Ollama base URL. Defaults to http://$OLLAMA_HOST when
                  OLLAMA_HOST is set, else http://localhost:11434.
  CLEF_MODEL      Model name (default "clef").
  CLEF_TIMEOUT    Per-request timeout in seconds (default 180).
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Union

from mcp.server.fastmcp import FastMCP

_ollama_host = os.environ.get("OLLAMA_HOST", "").strip()
_default_base = (
    f"http://{_ollama_host}" if _ollama_host else "http://localhost:11434"
)
BASE_URL = os.environ.get("CLEF_BASE_URL", _default_base).rstrip("/")
MODEL = os.environ.get("CLEF_MODEL", "clef")
TIMEOUT = float(os.environ.get("CLEF_TIMEOUT", "180"))

mcp = FastMCP("clef")


def _post_systemone(payload: dict) -> str:
    req = urllib.request.Request(
        f"{BASE_URL}/v1/systemone",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        hints = {
            404: " (is the /v1/systemone endpoint supported by this Ollama version?)",
            400: " (check the request shape: model, state, questions)",
        }
        return f"error: Ollama returned HTTP {e.code}{hints.get(e.code, '')}: {body}"
    except urllib.error.URLError as e:
        return (
            f"error: cannot reach Ollama at {BASE_URL} ({e.reason}). "
            "Is the Ollama server running and is the network path available?"
        )
    except TimeoutError:
        return (
            f"error: request timed out after {TIMEOUT}s "
            "(the first call loads the model into memory; retry once)"
        )


@mcp.tool()
def decide(state: Union[str, dict[str, Any], list[Any]], questions: dict) -> str:
    """Ask the local Clef decision model for fast typed decisions.

    Use for classification, yes/no judgments, and ratings — NOT for writing
    prose or code. Prefer this over reasoning step-by-step when the question
    is a well-defined choice, because it is one-shot and millisecond-fast.

    Args:
        state: The material to judge. A plain string, or a JSON object/array
            with named fields that the question instructions can refer to,
            e.g. {"diff": "...", "test_status": "34/34 passing"}.
        questions: Mapping of question id -> question spec. Each spec has:
            - "type": one of
                "noul"   -> yes/no; returns a 0-1 probability,
                "choice" -> pick one of several options,
                "score"  -> ordered rating across levels;
            - "instructions": what to decide (may reference state fields);
            - "criteria": for choice, object {option: description} (2-255
              options); for score, array of levels from low to high (2-10);
              for noul, optionally {"true": "...", "false": "..."}.

    Returns:
        JSON string with one entry per question id — the decision,
        per-option probabilities, and confidence — plus token usage.
    """
    payload = {"model": MODEL, "state": state, "questions": questions}
    return _post_systemone(payload)


@mcp.tool()
def health() -> str:
    """Check that the Ollama endpoint is reachable and report configuration.

    Returns JSON: ok, ollama_version, base_url, model.
    """
    try:
        with urllib.request.urlopen(
            f"{BASE_URL}/api/version", timeout=10
        ) as resp:
            version = json.loads(resp.read().decode("utf-8")).get("version")
        return json.dumps(
            {"ok": True, "ollama_version": version, "base_url": BASE_URL, "model": MODEL}
        )
    except Exception as e:  # noqa: BLE001 - report any failure in the payload
        return json.dumps(
            {"ok": False, "base_url": BASE_URL, "model": MODEL, "error": str(e)}
        )


if __name__ == "__main__":
    mcp.run()
