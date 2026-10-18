"""Load the mimetic-a0 weights (Hugging Face or a local folder) onto the best available device."""
import json
from pathlib import Path

import torch
from stable_audio_tools.models import create_model_from_config
from stable_audio_tools.models.utils import load_ckpt_state_dict

REPO_ID = "micknoise/mimetic-a0"


def pick_device(name: str | None = None) -> str:
    """'cuda' if there is an NVIDIA GPU, else 'mps' on Apple Silicon, else 'cpu'."""
    if name:
        return name
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _files(source: str, half: bool) -> tuple[Path, Path]:
    weights = "model.fp16.safetensors" if half else "model.safetensors"
    local = Path(source).expanduser()
    if local.is_dir():
        return local / "model_config.json", local / weights
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(source, "model_config.json")), Path(hf_hub_download(source, weights))


def _apg_on_cpu(project):
    """stable-audio-tools' APG projection casts to float64, which MPS lacks: run it (small latents) on the CPU."""
    def wrapped(v0, v1, padding_mask=None):
        if padding_mask is not None:
            padding_mask = padding_mask.cpu()
        parallel, orthogonal = project(v0.cpu(), v1.cpu(), padding_mask=padding_mask)
        return parallel.to(v0.device), orthogonal.to(v0.device)
    return wrapped


def load_model(source: str = REPO_ID, device: str | None = None, half: bool = False):
    """-> (model, config). `source` is a Hugging Face repo id or a folder holding model_config.json and
    model.safetensors. half=True loads the fp16 weights and runs in fp16 (less memory, faster on GPU and
    Apple Silicon; a seed gives a slightly different take than in fp32)."""
    device = pick_device(device)
    config_path, weights_path = _files(source, half)
    config = json.loads(config_path.read_text())
    model = create_model_from_config(config)
    model.load_state_dict(load_ckpt_state_dict(str(weights_path)))
    model = model.to(device).eval().requires_grad_(False)
    if half:
        model = model.half()
    if device == "mps":
        for module in model.modules():
            if hasattr(module, "apg_project"):
                module.apg_project = _apg_on_cpu(module.apg_project)
    return model, config
