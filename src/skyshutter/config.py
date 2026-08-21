"""Persistent client identity.

A camera remembers which GUIDs it has paired with, so skyshutter has to
present the *same* GUID on every connection.  It is stored in the user's
config directory and can be overridden (e.g. with the GUID recovered from a
SnapBridge pairing) via ``--guid`` or ``SKYSHUTTER_GUID``.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

ENV_GUID = "SKYSHUTTER_GUID"
ENV_NAME = "SKYSHUTTER_NAME"
DEFAULT_NAME = "skyshutter"


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "skyshutter" / "config.json"


def load() -> dict[str, str]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, str]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def client_guid(override: str | None = None) -> uuid.UUID:
    """The GUID to present to the camera, creating a stable one if needed."""
    raw = override or os.environ.get(ENV_GUID)
    if raw:
        return uuid.UUID(raw)

    data = load()
    stored = data.get("guid")
    if stored:
        try:
            return uuid.UUID(stored)
        except ValueError:
            pass

    generated = uuid.uuid4()
    data["guid"] = str(generated)
    try:
        save(data)
    except OSError:
        pass
    return generated


def client_name(override: str | None = None) -> str:
    return override or os.environ.get(ENV_NAME) or load().get("name") or DEFAULT_NAME
