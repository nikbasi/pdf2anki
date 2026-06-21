"""Helpers for LM Studio local inference."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

LMS_BIN = Path(os.path.expanduser("~/.lmstudio/bin/lms"))


def ensure_model_loaded(model: str, *, context_length: int = 4096) -> None:
    """Load the model via `lms load` if nothing is currently loaded."""
    if not LMS_BIN.is_file():
        return
    ps = subprocess.run([str(LMS_BIN), "ps"], capture_output=True, text=True, check=False)
    if "No models are currently loaded" not in ps.stdout:
        return
    key = model.split(":")[0]
    subprocess.run(
        [str(LMS_BIN), "load", key, "-y", "--context-length", str(context_length)],
        check=True,
    )


def ensure_server(port: int = 1234) -> None:
    """Start the LM Studio OpenAI-compatible server if it is not responding."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        urllib.request.urlopen(url, timeout=2)
        return
    except (urllib.error.URLError, TimeoutError):
        pass
    subprocess.run([str(LMS_BIN), "server", "start", "-p", str(port)], check=False)

