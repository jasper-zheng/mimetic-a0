"""Text to audio with mimetic-a0: the defaults the model was tested with (50 steps, CFG 6)."""
import numpy as np
import torch
from stable_audio_tools.inference.generation import generate_diffusion_cond


def bars_to_seconds(bars: float, bpm: float) -> float:
    """Length of `bars` bars of 4/4 at `bpm`."""
    return bars * 240.0 / bpm


def max_seconds(config: dict) -> float:
    return config["sample_size"] / config["sample_rate"]


def resolve_seed(seed: int) -> int:
    """stable-audio-tools picks a random seed for -1 without reporting it; pick it here so it can be shown."""
    return seed if seed != -1 else int(np.random.randint(0, 2**32 - 1))


def generate(model, config, prompt: str, seconds: float, *, n: int = 1, seed: int = -1, steps: int = 50,
             cfg_scale: float = 6.0, apg_scale: float = 1.0) -> tuple[torch.Tensor, int]:
    """-> ((n, 2, samples) float32 audio on the CPU, seed used). Seconds are capped at the 16 s window."""
    seconds = min(seconds, max_seconds(config))
    seed = resolve_seed(seed)
    device = next(model.parameters()).device
    cond = [{"prompt": prompt, "seconds_start": 0, "seconds_total": seconds}] * n
    with torch.no_grad():
        audio = generate_diffusion_cond(
            model, steps=steps, cfg_scale=cfg_scale, conditioning=cond, batch_size=n,
            sample_size=config["sample_size"], seed=seed, device=device, apg_scale=apg_scale,
        )
    return audio[:, :, : int(seconds * config["sample_rate"])].float().cpu(), seed


def peak_normalise(x: torch.Tensor, peak: float = 0.891) -> torch.Tensor:
    """(channels, samples) -> scaled so the loudest sample is at `peak` (-1 dBFS)."""
    return x / x.abs().max().clamp(min=1e-6) * peak
