"""Check an exported mimetic-a0 .pte set (.pte + .json + tokenizer files) on the Python ExecuTorch runtime
(MLX), through the same path Max takes.

  uv run python validate.py artifacts/<stem>.pte

1. metadata: the .json declares the interface neural.gen~ expects (names, roles, shapes, dtypes, output)
2. tokenizer: the bundled tokenizer, encoded as neural.tokenizer does it (tokenizers-cpp, no special
   tokens), gives the stock T5 tokens once </s> is appended (the graph does this, modules.ensure_eos),
   on every prompt in docs/prompting.md plus edge cases
3. graph: the .pte fed neural.tokenizer's tokens vs the PyTorch pipeline (stock precision, stock
   tokens; equal to stock generate() at a fixed length) on the same noise, for 3 prompts ×
   (S, cfg 6), (S, cfg 1), (S/2, cfg 6), (1 s, cfg 6). Gates: output finite and [1, 2, S·48000];
   audio after seconds_total + 6 s exactly 0; for fp32 exports SNR ≥ 20 dB (measured 30–60 dB).
   fp16 exports are a different take (like stock half=True), so their SNR is reported, not gated.
Exit code 0 = PASS. Writes <stem>.validate.json. Takes a few minutes (the reference runs on the CPU).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import torch
from tokenizers import Tokenizer

from mimetic_a0 import load_model
from modules import LATENT_CHANNELS, T5_MAX_LENGTH, build_full_pipeline, ensure_eos, latent_length, tokenize

PROMPTING_DOC = Path(__file__).resolve().parents[2] / "docs" / "prompting.md"
EDGE_CASES = ["", " ", "techno drum loop,130 BPM", "  house   drum loop  ", "Café jazz brush kit — swung, ½ time",
              "violin melody, D minor\n4 bars", "</s> inside", ", ".join(["grand piano chord, Cmaj7, block chord"] * 12)]
PROMPTS = [("house drum loop, dance kit, open hi-hats, 124 BPM, 4 bars", 1),
           ("finger bass bassline, over Cm - Fm - G7, sparse, 95 BPM, C minor, 4 bars", 2),
           ("grand piano chord, Cmaj7/E, rolled, first inversion, soft", 3)]
MIN_SNR_DB_FP32 = 20.0


def corpus() -> list[str]:
    """docs/prompting.md: code-block lines and the "Tested examples" prompts, plus edge cases."""
    text = PROMPTING_DOC.read_text()
    prompts = []
    for block in re.findall(r"```\n(.*?)```", text, re.S):
        prompts += [line.strip() for line in block.splitlines() if line.strip()]
    prompts += [row.strip() for row in re.findall(r"^\| ([^|]+?) \| [\d.]+ \|", text, re.M)]
    return list(dict.fromkeys(prompts)) + EDGE_CASES


def host_tokenize(tok: Tokenizer, prompt: str, cfg: dict) -> tuple[torch.Tensor, torch.Tensor]:
    """neural.tokenizer (NnTokenizer::encode): encode without special tokens, truncate, pad."""
    n = cfg["max_length"]
    enc = tok.encode(prompt, add_special_tokens=False).ids[:n]
    ids, mask = [tok.token_to_id(cfg["pad_token"])] * n, [0] * n
    off = n - len(enc) if cfg["padding_side"] == "left" else 0
    for i, t in enumerate(enc):
        ids[off + i], mask[off + i] = t, 1
    return torch.tensor([ids], dtype=torch.int64), torch.tensor([mask], dtype=torch.int32)


def stats(ref: torch.Tensor, ours: torch.Tensor) -> dict:
    ref, ours = ref.double(), ours.double()
    d = (ref - ours).abs()
    snr = 10 * torch.log10(ref.pow(2).sum() / d.pow(2).sum().clamp(min=1e-30))
    corr = torch.corrcoef(torch.stack([ref.flatten(), ours.flatten()]))[0, 1]
    return {"max": float(d.max()), "snr_db": round(float(snr), 1), "corr": round(float(corr), 6),
            "finite": bool(torch.isfinite(ours).all())}


def check_metadata(meta: dict, S: float, L: int, sr: int) -> list[str]:
    m = meta["methods"]["forward"]
    got = [(i["name"], i["role"], i["shape"], i["dtype"]) for i in m["inputs"]]
    want = [("input_ids", "condition", [1, T5_MAX_LENGTH], "int64"),
            ("attention_mask", "condition", [1, T5_MAX_LENGTH], "int32"),
            ("seconds_total", "attribute", [1], "float32"), ("cfg_scale", "attribute", [1], "float32"),
            ("init_noise", "noise", [1, LATENT_CHANNELS, L], "float32")]
    errors = [f"inputs {got} != {want}"] if got != want else []
    out = m["output"]
    if (out["shape"], out["sample_rate"]) != ([1, 2, int(S * sr)], sr):
        errors.append(f"output {out['shape']} @ {out['sample_rate']}")
    st = next(i for i in m["inputs"] if i["name"] == "seconds_total")
    if (st["default"], st["max"]) != (S, S):
        errors.append(f"seconds_total default/max {st['default']}/{st['max']} != {S}")
    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate an exported mimetic-a0 .pte set.")
    ap.add_argument("pte", type=Path)
    ap.add_argument("--model", default=None, help="HF repo or local folder the export was made from")
    a = ap.parse_args()
    torch.set_grad_enabled(False)
    from executorch.runtime import Runtime

    stem = a.pte.with_suffix("")
    match = re.search(r"_(\d+)steps(_fp16)?$", stem.name)
    if not match:
        sys.exit(f"can't read the step count from {a.pte.name} (expected <name>_<steps>steps[_fp16].pte)")
    steps, fp16 = int(match.group(1)), bool(match.group(2))
    meta = json.loads(a.pte.with_suffix(".json").read_text())
    tok_cfg = json.loads(Path(f"{stem}.tokenizer.config.json").read_text())
    tok = Tokenizer.from_file(str(a.pte.parent / tok_cfg["tokenizer_file"]))
    out = meta["methods"]["forward"]["output"]
    S = out["length"] / out["sample_rate"]

    model, config = load_model(*([a.model] if a.model else []), device="cpu")
    sr = config["sample_rate"]
    L = latent_length(S, config, model.pretransform.downsampling_ratio)
    report = {"pte": a.pte.name, "seconds": S, "steps": steps, "fp16": fp16}
    failures = [f"metadata: {e}" for e in check_metadata(meta, S, L, sr)]

    bad = []
    for p in corpus():
        stock = tokenize(model, p)
        host = ensure_eos(*host_tokenize(tok, p, tok_cfg))
        if not all(torch.equal(x, y) for x, y in zip(host, stock)):
            bad.append(p)
    report["tokenizer"] = {"prompts": len(corpus()), "mismatches": bad}
    failures += [f"tokenizer: {p!r}" for p in bad]
    print(f"tokenizer: {len(corpus()) - len(bad)}/{len(corpus())} prompts give the stock tokens", flush=True)

    ref_pipe = build_full_pipeline(model, config, S, steps)
    method = Runtime.get().load_program(str(a.pte)).load_method("forward")
    report["graph"] = []
    for prompt, seed in PROMPTS:
        host = host_tokenize(tok, prompt, tok_cfg)
        stock = tokenize(model, prompt)
        torch.manual_seed(seed)
        noise = torch.randn([1, LATENT_CHANNELS, L])
        for st, cfg in [(S, 6.0), (S, 1.0), (S / 2, 6.0), (1.0, 6.0)]:
            attrs = [torch.tensor([st]), torch.tensor([cfg])]
            (y,) = method.execute([*host, *attrs, noise])
            ref = ref_pipe(*stock, *attrs, noise)
            tail_start = int((st + 6.0) * sr)
            r = {"prompt": prompt[:40], "seconds_total": st, "cfg": cfg, **stats(ref, y),
                 "tail_zero": bool((y[..., tail_start:] == 0).all()) if tail_start < y.shape[-1] else None}
            name = f"{prompt[:30]!r} seconds_total={st:g} cfg={cfg:g}"
            if list(y.shape) != [1, 2, int(S * sr)] or not r["finite"]:
                failures.append(f"graph {name}: shape {list(y.shape)}, finite {r['finite']}")
            if r["tail_zero"] is False:
                failures.append(f"graph {name}: audio after seconds_total + 6 s is not silent")
            if not fp16 and r["snr_db"] < MIN_SNR_DB_FP32:
                failures.append(f"graph {name}: SNR {r['snr_db']} dB < {MIN_SNR_DB_FP32} dB")
            print(f"graph: {name:<60} SNR {r['snr_db']:5} dB  corr {r['corr']:.4f}", flush=True)
            report["graph"].append(r)

    report["failures"] = failures
    a.pte.with_suffix(".validate.json").write_text(json.dumps(report, indent=2))
    print("\n".join(failures) or "no failures")
    print(f"{a.pte.name}: {'FAIL' if failures else 'PASS'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
