"""mimetic-a0 (cc0-sampler v4): text-to-audio for music, trained only on CC0 and synthetic audio."""
import os

# Apple Silicon: let the few ops MPS lacks run on the CPU instead of failing. Must be set before torch loads.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from .model import REPO_ID, load_model, pick_device  # noqa: E402
from .generate import bars_to_seconds, generate  # noqa: E402

__all__ = ["REPO_ID", "load_model", "pick_device", "generate", "bars_to_seconds"]
