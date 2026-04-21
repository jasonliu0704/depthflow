from importlib.metadata import PackageNotFoundError, metadata

try:
    from dearlog import logger  # type: ignore[import-not-found] # isort: split
except ImportError:  # pragma: no cover - fallback for local development
    import logging

    logger = logging.getLogger(__package__ or "depthflow")

try:
    __meta__ = metadata(str(__package__))
except PackageNotFoundError:  # pragma: no cover - local source tree fallback
    __meta__ = {}

__about__   = __meta__.get("Summary", "Images to parallax effect videos")
__author__  = __meta__.get("Author", "Tremeschin")
__version__ = __meta__.get("Version", "0.10.0")

from pathlib import Path

from platformdirs import PlatformDirs

resources = Path(__file__).parent/"resources"

directories = PlatformDirs(
    appname=__package__,
    ensure_exists=True,
    opinion=True,
)

import os

# macOS: Enable CPU fallback for unsupported operations in MPS
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Make telemetries opt-in
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
