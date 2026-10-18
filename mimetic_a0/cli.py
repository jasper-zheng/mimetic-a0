"""mimetic-a0: text to audio from the command line.

  mimetic-a0 "boom bap drum loop, standard kit, swung, 90 BPM, 4 bars" --bpm 90 --bars 4
  mimetic-a0 "single cello note, G3" --seconds 3 -n 4 --seed 1 --out takes/
"""
import argparse
import re
from pathlib import Path

import soundfile as sf

from . import REPO_ID, bars_to_seconds, generate, load_model, pick_device
from .generate import peak_normalise


def main():
    ap = argparse.ArgumentParser(description="mimetic-a0: text to audio (48 kHz stereo, up to 16 s)")
    ap.add_argument("prompt")
    ap.add_argument("--seconds", type=float, help="length; default from --bpm and --bars, else 8")
    ap.add_argument("--bpm", type=float, help="adds 'N BPM' to the prompt if it isn't there; with --bars, sets the "
                    "length to exactly that many bars")
    ap.add_argument("--bars", type=int, choices=(1, 2, 4), help="adds 'N bars' to the prompt if it isn't there")
    ap.add_argument("-n", type=int, default=1, help="number of takes")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--cfg", type=float, default=6.0)
    ap.add_argument("--out", default=".", help="output folder")
    ap.add_argument("--model", default=REPO_ID, help="Hugging Face repo id or local folder")
    ap.add_argument("--device", help="cuda, mps or cpu (default: best available)")
    ap.add_argument("--half", action="store_true", help="fp16 weights: less memory, faster on NVIDIA GPUs")
    a = ap.parse_args()

    # the clause order the training captions use: ..., tempo, key, length
    if a.bpm and not re.search(r"\d\s*BPM", a.prompt):
        a.prompt += f", {a.bpm:g} BPM"
    if a.bars and not re.search(r"\d\s*bars?\b", a.prompt):
        a.prompt += f", {a.bars} bar{'s' if a.bars > 1 else ''}"
    if a.seconds is None:
        a.seconds = bars_to_seconds(a.bars, a.bpm) if a.bpm and a.bars else 8.0
    device = pick_device(a.device)
    print(f"prompt: {a.prompt}  ({a.seconds:.2f} s)")
    print(f"loading {a.model} on {device}{' (fp16)' if a.half else ''} ...")
    model, config = load_model(a.model, device, a.half)
    audio, seed = generate(model, config, a.prompt, a.seconds, n=a.n, seed=a.seed, steps=a.steps, cfg_scale=a.cfg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.prompt.lower()).strip("-")[:48]
    for i, x in enumerate(audio):
        path = out / f"{slug}_{seed}_{i}.wav"
        sf.write(path, peak_normalise(x).T.numpy(), config["sample_rate"], subtype="PCM_24")
        print(path)


if __name__ == "__main__":
    main()
