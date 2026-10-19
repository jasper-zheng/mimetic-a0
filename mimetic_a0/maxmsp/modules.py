"""
mimetic-a0 export building blocks: an export-shaped rebuild of stock `generate()` (text-to-audio).

Tensors in, tensors out, static shapes; the generation length S and the step count are baked in
at build time. Every learned part is the stock stable-audio-tools module, taken by reference from
`load_model()`'s output and called directly, so mimetic-a0 / stable-audio-tools stay unmodified.

    FullPipeline
      ├─ TextConditioning       T5-base encoder (zero padding) + seconds_start/seconds_total embedders
      ├─ padding_mask           valid latents from seconds_total (stock varlen mask, 6 s headroom)
      ├─ UnrolledEulerCFG       N Euler steps, batch-2 CFG with masked APG, sigmas baked as floats
      └─ DecoderExport          Oobleck decoder → audio mask → trim to S seconds

Precision: T5 runs in fp16 (stock). The DiT and the decoder run in fp32 (stock default) or fp16
(stock half=True); reduced-precision parts are cast copies, so the stock model is left as loaded.
The Euler state, APG and CFG combine always stay fp32.

Forward contract (positional; order + dtype are load-bearing for the host):
  input_ids       (1, 128)   int64    T5 token ids                     (condition)
  attention_mask  (1, 128)   int32    1 = token, 0 = pad               (condition)
  seconds_total   (1,)       float32  duration conditioning, [0, S]    (attribute)
  cfg_scale       (1,)       float32  guidance scale, 1 = none         (attribute)
  init_noise      (1, 64, L) float32  initial Gaussian noise           (noise)
  → audio         (1, 2, S·48000) float32 @ 48 kHz

Reproduces (stable-audio-tools @3241adb): generate_diffusion_cond → sample_diffusion →
sample_discrete_euler → DiffusionTransformer.forward (CFG branch, apg_scale=1) → pretransform.decode.
"""

import copy
import math

import torch
import torch.nn as nn
from stable_audio_tools.inference.sampling import build_schedule

T5_MAX_LENGTH = 128
T5_EOS_ID = 1                # </s>
LATENT_CHANNELS = 64
DURATION_PADDING_SEC = 6.0  # generate_diffusion_cond's duration_padding_sec (= sample_diffusion headroom)
# Latents past the S-second trim that still reach it through the decoder's receptive field. Stock decodes
# all L latents (S + 6 s) and trims; decoding ceil(S·sr/ds) + margin is bit-identical in the kept part
# (measured: max|Δ| = 0 from 12 latents on, 4e-6 at 8) and skips ~40 % of the decoder at S = 8 s.
DECODE_MARGIN_LATENTS = 16


# ===========================================================================
# Graph prep
# ===========================================================================

def remove_weight_norm_all(module: nn.Module) -> None:
    """Bake weight_norm (old-style hooks) into plain weights on every conv, transposed ones
    included, so torch.export traces a plain conv. Same formula the hook evaluates, so exact."""
    from torch.nn.utils import remove_weight_norm
    for submodule in module.modules():
        if isinstance(submodule, (nn.Conv1d, nn.ConvTranspose1d)):
            try:
                remove_weight_norm(submodule)
            except ValueError:
                pass  # no weight_norm on this layer


def cast_copy(module: nn.Module, dtype: torch.dtype) -> nn.Module:
    """`module` itself if it already has `dtype`, else a deep copy cast to it."""
    return module if dtype == next(module.parameters()).dtype else copy.deepcopy(module).to(dtype)


# ===========================================================================
# Length / mask helpers
# ===========================================================================

def latent_length(seconds: float, config: dict, downsampling_ratio: int) -> int:
    """Latent length stock generate() samples at for `seconds_total=seconds`: (seconds + 6 s) of
    audio, aligned up to the downsampling ratio, capped at the model's 16 s window."""
    target = int((seconds + DURATION_PADDING_SEC) * config["sample_rate"])
    target = -(-target // downsampling_ratio) * downsampling_ratio
    return min(target, config["sample_size"]) // downsampling_ratio


def padding_mask(seconds_total: torch.Tensor, latent_len: int, sample_rate: int,
                 downsampling_ratio: int) -> torch.Tensor:
    """(1,) seconds → (1, L) bool, True = valid latent. In-graph version of sample_diffusion's
    compute_effective_seq_len_from_conditioning + headroom + create_padding_mask_from_lengths."""
    effective = torch.ceil(torch.floor(seconds_total * sample_rate) / downsampling_ratio)
    headroom = int(DURATION_PADDING_SEC * sample_rate / downsampling_ratio)
    valid = (effective + headroom).clamp(max=latent_len)                       # (1,)
    positions = torch.arange(latent_len, device=seconds_total.device).unsqueeze(0)
    return positions < valid.unsqueeze(1)                                      # (1, L)


# ===========================================================================
# Conditioning
# ===========================================================================

def ensure_eos(input_ids, attention_mask, eos_id: int = T5_EOS_ID):
    """Right-padded tokens → the tokens stock T5 tokenisation gives: </s> appended after the content,
    or, when the content fills max_length, written over the last token (truncation keeps
    max_length - 1 tokens + </s>). No-op when the content already ends in </s>.

    neural.tokenizer encodes without special tokens (tokenizers-cpp Encode(text) passes
    add_special_tokens=false), so without this every prompt would reach T5 without its </s>.
    """
    max_len = input_ids.shape[1]
    n = attention_mask.sum(dim=1, keepdim=True).long()                         # (1, 1) content tokens
    last = input_ids.gather(1, (n - 1).clamp(min=0))
    has_eos = (last == eos_id) & (n > 0)
    at = torch.arange(max_len, device=input_ids.device).unsqueeze(0) == n.clamp(max=max_len - 1)
    put = at & ~has_eos                                                        # (1, L)
    return (torch.where(put, torch.full_like(input_ids, eos_id), input_ids),
            torch.where(put, torch.ones_like(attention_mask), attention_mask))


class TextConditioning(nn.Module):
    """T5-base + NumberConditioners → the two tensors the DiT consumes.

    cross_attn_cond: (1, 130, 768)  128 prompt tokens + seconds_start + seconds_total
    global_cond:     (1, 1536)      [seconds_start ; seconds_total]

    Accepts tokens with or without the trailing </s> (ensure_eos), so both stock tokenisation
    and neural.tokenizer's (no special tokens) give the stock conditioning.

    Stock T5Conditioner runs the encoder in fp16 even on CPU (the module lives outside the
    registered submodules; its autocast line is a no-op). t5_dtype=float16 reproduces that,
    float32 is an fp32 copy of the same weights.
    """
    def __init__(self, t5_cond, ss_cond, st_cond, t5_dtype: torch.dtype = torch.float16):
        super().__init__()
        self.t5 = cast_copy(t5_cond.model, t5_dtype)
        self.proj_out = t5_cond.proj_out                     # nn.Identity for mimetic-a0
        self.ss_embedder, self.ss_min, self.ss_max = ss_cond.embedder, ss_cond.min_val, ss_cond.max_val
        self.st_embedder, self.st_min, self.st_max = st_cond.embedder, st_cond.min_val, st_cond.max_val

    @staticmethod
    def _number(embedder, x, lo, hi):
        """NumberConditioner.forward: clamp, normalise to [0, 1], embed → (1, 1, 768)."""
        return embedder((x.clamp(lo, hi) - lo) / (hi - lo)).unsqueeze(1)

    def forward(self, input_ids, attention_mask, seconds_total):
        input_ids, attention_mask = ensure_eos(input_ids, attention_mask)
        emb = self.t5(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        emb = self.proj_out(emb)
        emb = emb * attention_mask.unsqueeze(-1).float()     # padding_mode "zero" (→ float32)

        ss = self._number(self.ss_embedder, torch.zeros_like(seconds_total), self.ss_min, self.ss_max)
        st = self._number(self.st_embedder, seconds_total, self.st_min, self.st_max)

        cross_attn_cond = torch.cat([emb, ss, st], dim=1)            # (1, 130, 768)
        global_cond = torch.cat([ss, st], dim=-1).squeeze(1)         # (1, 1536)
        return cross_attn_cond, global_cond


# ===========================================================================
# Sampler
# ===========================================================================

def apg_orthogonal(diff, cond_denoised, mask, dtype: torch.dtype = torch.float32):
    """Masked branch of DiffusionTransformer.apg_project, orthogonal part only, with explicit ops.

    Stock computes it in float64 (which MLX lacks); dtype=float64 reproduces that exactly,
    float32 is the export path. mask: (B, T) bool, True = valid.
    """
    out_dtype = diff.dtype
    v0, v1 = diff.to(dtype), cond_denoised.to(dtype)
    m = mask.unsqueeze(1).to(dtype)                                          # (B, 1, T)
    v1 = v1 * m
    v1 = v1 / v1.pow(2).sum(dim=(-1, -2), keepdim=True).sqrt().clamp(min=1e-8)
    orthogonal = (v0 - (v0 * v1).sum(dim=(-1, -2), keepdim=True) * v1) * m
    return orthogonal.to(out_dtype)


class UnrolledEulerCFG(nn.Module):
    """sample_discrete_euler over a baked schedule, with DiffusionTransformer.forward's CFG branch
    (zero null cross-attention cond, shared global cond, full APG) on a batch-2 _forward.

    Always runs the guided branch: at cfg_scale=1 it equals stock's unguided call up to rounding.
    `sigmas` and `dts` are Python floats holding the stock float32 schedule values exactly.
    With dit_dtype=float16 only dit._forward runs in fp16 (cast in, cast out).
    """
    def __init__(self, dit, sigmas: list[float], dts: list[float], apg_dtype: torch.dtype = torch.float32,
                 dit_dtype: torch.dtype = torch.float32):
        super().__init__()
        self.dit = cast_copy(dit, dit_dtype)
        self.dit_dtype = dit_dtype
        self.sigmas = sigmas
        self.dts = dts
        self.apg_dtype = apg_dtype

    def velocity(self, x, sigma: float, cross_attn_cond, global_cond, mask, cfg_scale):
        t = x.new_full((1,), sigma)
        dt_ = self.dit_dtype
        batch_out = self.dit._forward(
            torch.cat([x, x], dim=0).to(dt_),
            torch.cat([t, t], dim=0).to(dt_),
            cross_attn_cond=torch.cat([cross_attn_cond, torch.zeros_like(cross_attn_cond)], dim=0).to(dt_),
            global_embed=torch.cat([global_cond, global_cond], dim=0).to(dt_),
            padding_mask=torch.cat([mask, mask], dim=0),
        ).to(x.dtype)
        cond_out, uncond_out = torch.chunk(batch_out, 2, dim=0)
        cond_denoised = x - cond_out * sigma
        uncond_denoised = x - uncond_out * sigma
        orthogonal = apg_orthogonal(cond_denoised - uncond_denoised, cond_denoised, mask, self.apg_dtype)
        cfg_denoised = cond_denoised + (cfg_scale - 1) * orthogonal
        return (x - cfg_denoised) / sigma

    def forward(self, x, cross_attn_cond, global_cond, mask, cfg_scale):
        for sigma, dt in zip(self.sigmas, self.dts):
            x = x + dt * self.velocity(x, sigma, cross_attn_cond, global_cond, mask, cfg_scale)
        return x


# ===========================================================================
# Decoder
# ===========================================================================

class DecoderExport(nn.Module):
    """AutoencoderPretransform.decode → AudioAutoencoder.decode, unrolled for batch 1: scale,
    bottleneck decode (identity for the VAE), Oobleck decoder; then sample_diffusion's audio mask
    and generate()'s trim to S seconds. Skips the wrappers' iterate_batch / no_grad branches.

    The decoder is a copy with weight_norm baked in (exact), cast to `dtype`. Only the latents that
    reach the first out_len samples are decoded (DECODE_MARGIN_LATENTS), which leaves them unchanged."""
    def __init__(self, pretransform, out_len: int, dtype: torch.dtype = torch.float32):
        super().__init__()
        ae = pretransform.model
        assert ae.pretransform is None and not ae.soft_clip and not pretransform.model_half
        self.scale = pretransform.scale
        self.bottleneck = ae.bottleneck
        self.decoder = copy.deepcopy(ae.decoder).to(dtype)
        remove_weight_norm_all(self.decoder)
        self.dtype = dtype
        self.downsampling_ratio = pretransform.downsampling_ratio
        self.out_len = out_len
        self.decode_len = -(-out_len // self.downsampling_ratio) + DECODE_MARGIN_LATENTS

    def forward(self, latents, mask):
        z = latents[..., :self.decode_len] * self.scale
        z = self.bottleneck.decode(z)
        audio = self.decoder(z.to(self.dtype))[..., :self.out_len].float()      # (1, 2, S·sr)
        audio_mask = mask.unsqueeze(1).repeat_interleave(self.downsampling_ratio, dim=-1)
        return audio * audio_mask[..., :self.out_len].to(audio.dtype)


# ===========================================================================
# Full pipeline
# ===========================================================================

class FullPipeline(nn.Module):
    """Text conditioning → Euler/CFG denoising → Oobleck decode → (1, 2, S·48000) audio."""
    def __init__(self, text_cond, sampler, decoder, latent_len: int, sample_rate: int):
        super().__init__()
        self.text_cond = text_cond
        self.sampler = sampler
        self.decoder = decoder
        self.latent_len = latent_len
        self.sample_rate = sample_rate

    def padding_mask(self, seconds_total):
        return padding_mask(seconds_total, self.latent_len, self.sample_rate, self.decoder.downsampling_ratio)

    def forward(self, input_ids, attention_mask, seconds_total, cfg_scale, init_noise):
        cross_attn_cond, global_cond = self.text_cond(input_ids, attention_mask, seconds_total)
        mask = self.padding_mask(seconds_total)
        latents = self.sampler(init_noise, cross_attn_cond, global_cond, mask, cfg_scale)
        return self.decoder(latents, mask)


def euler_schedule(model, steps: int, latent_len: int) -> tuple[list[float], list[float]]:
    """Stock RF schedule (build_schedule with the model's sampling dist_shift, LogSNRShift(rate=0)
    for mimetic-a0), as the (sigma, dt) Python floats sample_discrete_euler uses in float32."""
    t = build_schedule(steps=steps, sigma_max=1.0, dist_shift=model.sampling_dist_shift,
                       fallback_seq_len=latent_len, include_endpoint=True).float()
    return [float(s) for s in t[:-1]], [float(t[i + 1] - t[i]) for i in range(steps)]


def build_full_pipeline(model, config: dict, seconds: float = 8.0, steps: int = 24,
                        t5_dtype: torch.dtype = torch.float16,
                        apg_dtype: torch.dtype = torch.float32,
                        dit_dtype: torch.dtype = torch.float32,
                        decoder_dtype: torch.dtype = torch.float32) -> FullPipeline:
    """Eval'd FullPipeline for a fixed length `seconds` (S) and step count, from load_model()'s output.

    Defaults are stock precision (T5 fp16, DiT + decoder fp32) with the fp32 APG of the export.
    """
    assert model.diffusion_objective == "rectified_flow"
    assert model.cross_attn_cond_ids == ["prompt", "seconds_start", "seconds_total"]
    assert model.global_cond_ids == ["seconds_start", "seconds_total"]
    assert model.mask_padding_attention and not model.use_effective_length_for_schedule

    sample_rate = config["sample_rate"]
    ds_ratio = model.pretransform.downsampling_ratio
    latent_len = latent_length(seconds, config, ds_ratio)
    sigmas, dts = euler_schedule(model, steps, latent_len)

    conds = model.conditioner.conditioners
    text_cond = TextConditioning(conds["prompt"], conds["seconds_start"], conds["seconds_total"], t5_dtype)
    sampler = UnrolledEulerCFG(model.model.model, sigmas, dts, apg_dtype, dit_dtype)
    decoder = DecoderExport(model.pretransform, int(seconds * sample_rate), decoder_dtype)
    return FullPipeline(text_cond, sampler, decoder, latent_len, sample_rate).eval()


def tokenize(model, prompt: str) -> tuple[torch.Tensor, torch.Tensor]:
    """Prompt → ((1, 128) int64 ids, (1, 128) int32 mask), as stock T5Conditioner tokenizes it."""
    tok = model.conditioner.conditioners["prompt"].tokenizer
    enc = tok([prompt], truncation=True, max_length=T5_MAX_LENGTH, padding="max_length", return_tensors="pt")
    return enc["input_ids"].long(), enc["attention_mask"].int()
