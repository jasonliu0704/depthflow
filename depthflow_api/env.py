from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries from a .env file without overriding env."""
    for env_path in _candidate_env_files(path):
        if env_path.is_file():
            _load_env_path(env_path)
            return


def _candidate_env_files(path: Path | None) -> list[Path]:
    if path is not None:
        return [path.expanduser().resolve()]

    candidates: list[Path] = []
    configured_path = os.getenv("DEPTHFLOW_API_ENV_FILE")
    if configured_path:
        candidates.append(Path(configured_path).expanduser().resolve())

    candidates.append((Path.cwd() / ".env").resolve())
    candidates.append((Path(__file__).resolve().parents[1] / ".env").resolve())
    return candidates


def _load_env_path(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()
        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if not os.environ.get(key):
            os.environ[key] = value
