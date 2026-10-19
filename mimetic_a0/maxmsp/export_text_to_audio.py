"""Export mimetic-a0 text-to-audio to one ExecuTorch MLX .pte for Max/MSP's neural.gen~ (neural_tilde).

  uv run python export_text_to_audio.py [--seconds 8 | --bpm 120 --bars 4] [--steps 24] [--half]
                                        [--model <repo|folder>] [--seed 0] [--out artifacts]

The generation length S and the number of Euler steps are fixed at export; to change either, export
again. Writes, in --out (`<stem>` = mimetic-a0_t2a_<S>s_<steps>steps[_fp16]):
  <stem>.pte                    the model: T5 conditioning + unrolled Euler/APG sampler + VAE decoder
  <stem>.json                   neural.gen~ metadata (inputs, attributes, output)
  <stem>.tokenizer.json         T5 tokenizer for neural.tokenizer
  <stem>.tokenizer.config.json  its settings

Precision: fp32 by default (T5 in fp16, as stock mimetic-a0 runs it). --half runs the diffusion model
and the decoder in fp16 as well, like `load_model(half=True)`: about 10 % faster and 45 % smaller on
disk, a different take for the same seed, not audibly worse.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from huggingface_hub import hf_hub_download
from neural_tilde import GenModule

from mimetic_a0 import load_model
from mimetic_a0.generate import bars_to_seconds, max_seconds
from mimetic_a0.model import REPO_ID
from modules import LATENT_CHANNELS, T5_MAX_LENGTH, build_full_pipeline, latent_length

HERE = Path(__file__).parent


def stem_for(seconds: float, steps: int, half: bool) -> str:
    return f"mimetic-a0_t2a_{seconds:g}s_{steps}steps{'_fp16' if half else ''}"


def build_gen_module(pipe, seconds: float, latent_len: int, sample_rate: int) -> GenModule:
    """Register the forward inputs by name + role, in FullPipeline.forward's (load-bearing) order."""
    gm = GenModule(pipe)
    gm.register_condition("input_ids", [1, T5_MAX_LENGTH], "int64")
    gm.register_condition("attention_mask", [1, T5_MAX_LENGTH], "int32")
    gm.register_attribute("seconds_total", float(seconds), 0.0, float(seconds),
                          "Duration conditioning in seconds. Output stays the full export length; "
                          "audio after seconds_total + 6 s is silent.")
    gm.register_attribute("cfg_scale", 6.0, 1.0, 15.0,
                          "Classifier-free guidance scale (APG). 1 = no guidance.")
    gm.register_noise("init_noise", [1, LATENT_CHANNELS, latent_len])
    gm.register_method("forward", inputs=["input_ids", "attention_mask", "seconds_total", "cfg_scale", "init_noise"],
                       out_channels=2, out_length=int(seconds * sample_rate), out_sample_rate=sample_rate)
    # the tokenizer stock T5Conditioner loads; neural.tokenizer encodes without </s>, which the
    # graph appends (modules.ensure_eos)
    gm.register_tokenizer(hf_hub_download("t5-base", "tokenizer.json"), max_length=T5_MAX_LENGTH,
                          pad_token="<pad>", padding_side="right",
                          ids_key="input_ids", mask_key="attention_mask")
    return gm


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seconds", type=float, help="generation length S in seconds (default 8)")
    ap.add_argument("--bpm", type=float, help="with --bars: S = bars · 240 / BPM")
    ap.add_argument("--bars", type=float)
    ap.add_argument("--steps", type=int, default=24, help="Euler steps (default 24; 16 is the fast option)")
    ap.add_argument("--half", action="store_true", help="fp16 diffusion model + decoder (default fp32)")
    ap.add_argument("--model", default=REPO_ID, help=f"HF repo or local folder (default {REPO_ID})")
    ap.add_argument("--seed", type=int, default=0, help="default seed written to the metadata (Max can change it)")
    ap.add_argument("--out", type=Path, default=HERE / "artifacts")
    a = ap.parse_args()
    if (a.bpm is None) != (a.bars is None):
        ap.error("--bpm and --bars go together")
    if a.bpm is not None and a.seconds is not None:
        ap.error("give either --seconds or --bpm/--bars")
    torch.set_grad_enabled(False)

    model, config = load_model(a.model, device="cpu")
    seconds = round(bars_to_seconds(a.bars, a.bpm), 2) if a.bpm is not None else (a.seconds or 8.0)
    if not 0 < seconds <= max_seconds(config):
        ap.error(f"length must be in (0, {max_seconds(config):g}] s, got {seconds:g}")

    dtype = torch.float16 if a.half else torch.float32
    pipe = build_full_pipeline(model, config, seconds, a.steps, dit_dtype=dtype, decoder_dtype=dtype)
    if a.half:
        model.model.model.to("meta")   # the stock fp32 diffusion model is no longer needed: free its memory
    latent_len = latent_length(seconds, config, model.pretransform.downsampling_ratio)
    gm = build_gen_module(pipe, seconds, latent_len, config["sample_rate"])
    gm.set_seed(a.seed)

    stem = stem_for(seconds, a.steps, a.half)
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"Exporting {stem} ({seconds:g} s, {a.steps} steps, {'fp16' if a.half else 'fp32'}); "
          f"this takes several minutes and ~{17 if a.steps <= 16 else 33} GB of RAM "
          f"(measured at 16 / 24 steps; more steps need more) ...", flush=True)
    t0 = time.time()
    pte = gm.export_to_pte(str(a.out / stem), delegate="mlx", decompose_conv=True)
    info = {"stem": stem, "seconds": seconds, "steps": a.steps, "precision": "fp16" if a.half else "fp32",
            "model": a.model, "export_s": round(time.time() - t0, 1),
            "pte_mb": round(Path(pte).stat().st_size / 2**20, 1)}
    print(json.dumps(info))
    print(f"\nWrote {pte} (+ .json, tokenizer files).\n"
          f"Check it:   uv run python validate.py {pte}")


if __name__ == "__main__":
    main()
