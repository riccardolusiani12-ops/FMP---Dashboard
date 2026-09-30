"""Notifica macOS tramite osascript (titolo "Calcio Italiano")."""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("pipeline")

TITLE = "Calcio Italiano"


def _applescript_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(message: str, subtitle: str | None = None) -> None:
    script = f"display notification {_applescript_str(message)} with title {_applescript_str(TITLE)}"
    if subtitle:
        script += f" subtitle {_applescript_str(subtitle)}"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=15)
        log.info("🔔 Notifica: %s", message)
    except Exception as e:  # la notifica non deve mai far fallire la pipeline
        log.warning("Notifica non inviata (%s): %s", e, message)


if __name__ == "__main__":
    import sys

    notify(" ".join(sys.argv[1:]) or "Test notifica pipeline")
