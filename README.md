# mimetic-a0

A text-to-audio model for music, trained only on audio with a clean licence: Freesound clips released as CC0, and synthetic music rendered by our own procedural generators. It writes 48 kHz stereo, up to 16 s: drum loops, basslines, chords, melodies, pads, one-shots and full mixes, at the tempo, key and chords you ask for.

**Speed.** A 12 s clip at 50 steps takes:

| | fp32 (`model.safetensors`, 2.0 GB) | fp16 (`model.fp16.safetensors`, 1.0 GB) |
|---|---|---|
| NVIDIA RTX PRO 6000 | 1.7 s | 0.4 s |
| Apple M1 Max (32 GB) | 6.7 s | 6.7 s |

The fp16 version (`--half`) needs about half the memory: generating a 12 s clip on the M1 Max peaked at 2.2 GB in fp16 against 4.1 GB in fp32. It is four times faster on an NVIDIA GPU, whose tensor cores do fp16 arithmetic at several times the fp32 rate. On the M1 Max it runs at the same speed as fp32 and only saves memory: its GPU does fp16 matrix multiplication at the same rate as fp32 (we measured 7.1 and 6.6 TFLOPS), and the diffusion transformer's time is mostly matrix multiplication. Loading the model adds about 10 s to each command-line run; the web UI loads it once.

- The model has 511M parameters: a 326M diffusion transformer plus the autoencoder (VAE).
- The CPU works too: a 3 s clip took 18 s on a many-core workstation CPU.
- The same seed gives different audio on CUDA, Apple Silicon and the CPU, and with or without `--half`, because each draws its starting noise differently.
- On a Mac, the Metal driver keeps more memory than the model uses in its cache: 6.7 GB in fp32 and 3.3 GB in fp16.
- On CUDA, one clip peaked at 4.4 GB in fp32.

**A base for fine-tuning.** mimetic-a0 is also intended as a base model for fine-tuning, and we will be releasing updates for this.

This repo runs it: a command-line tool and a local web UI, on NVIDIA GPUs, Apple Silicon Macs (M1 and later) or the CPU. The weights are on Hugging Face: [micknoisemachine/mimetic-a0](https://huggingface.co/micknoisemachine/mimetic-a0). They download on first run.

mimetic-a0 is version 0.1, an early release. Internally it is cc0-sampler v4 (checkpoint "anneal 120k").

## Install

You need [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`) and git.

```bash
git clone https://github.com/micknoise/mimetic-a0
cd mimetic-a0
uv sync
```

`uv sync` creates `.venv` with Python 3.11, PyTorch 2.7.1 and stock [stable-audio-tools](https://github.com/Stability-AI/stable-audio-tools) at the commit the model was made with. On a Mac it installs the standard PyTorch build, which uses the GPU through Metal (MPS). On x86-64 Linux it installs the CUDA 12.6 build.

**RTX 50xx (Blackwell) cards** need the CUDA 12.8 build instead. After `uv sync`:

```bash
uv pip install --torch-backend=cu128 --reinstall-package torch --reinstall-package torchaudio torch==2.7.1 torchaudio==2.7.1
```

After that, run the tools from `.venv/bin/` (or with `uv run --no-sync`), since a plain `uv run` would put the CUDA 12.6 build back.

The first run downloads the weights (2 GB, or 1 GB with `--half`) and the T5-base text encoder (about 900 MB) into the Hugging Face cache.

## Web UI

```bash
uv run mimetic-a0-webui
```

Then open http://127.0.0.1:8799. It picks the best device (CUDA, then Apple Silicon, then CPU) and prints it at start-up.

- **Generate:** text to audio. Click an example prompt to start. The **musical fields** (BPM, bars, key, chords, feel, density, dynamics) add clauses to the prompt the way the training captions word them, and BPM + bars set the duration to exactly that many bars. The "Prompt sent" line shows what goes to the model.
- **Retake:** regenerates uploaded audio from a noisy copy of it. The prompt describes the result you want; the slider sets how far it may move from your audio.
- **Repaint:** regenerates a stretch you select on the waveform and keeps the rest of your audio exactly, crossfaded at the edges.

Options: `--port 9000`, `--host 0.0.0.0` (serve your network, with no authentication), `--half` (fp16 weights: less memory, faster on NVIDIA GPUs), `--device cpu`, `--model <folder>` (load local weights instead of downloading).

## Command line

```bash
uv run mimetic-a0 "boom bap drum loop, standard kit, swung, with ghost notes" --bpm 90 --bars 4 -n 4
uv run mimetic-a0 "single cello note, G3" --seconds 3 --seed 1 --out takes/
```

`--bpm` and `--bars` set the length to exactly that many bars of 4/4 and add "90 BPM, 4 bars" to the prompt if it isn't there. Files are written as 24-bit WAV, `<prompt>_<seed>_<take>.wav`. `uv run mimetic-a0 --help` lists the rest (`--steps`, `--cfg`, `--half`, `--device`, `--model`).

From Python:

```python
from mimetic_a0 import load_model, generate, bars_to_seconds

model, config = load_model()              # micknoisemachine/mimetic-a0 on the best device
audio, seed = generate(model, config, "house drum loop, dance kit, open hi-hats, 124 BPM, 4 bars",
                       bars_to_seconds(4, 124), n=2)
# audio: (2 takes, 2 channels, samples) float32 at 48 kHz
```

The weights also load in stock stable-audio-tools (`get_pretrained_model("micknoisemachine/mimetic-a0")`), at commit `3241adb` or later.

## Max/MSP

**[mimetic_a0/maxmsp](mimetic_a0/maxmsp/README.md)** exports the model to run locally on Max/MSP, with the `neural.gen~` external from [neural_tilde](https://github.com/jasper-zheng/neural_tilde), see [mimetic_a0/maxmsp/README.md](mimetic_a0/maxmsp/README.md) for instructions.

## Prompting

The model follows the wording of its training captions best. **[docs/prompting.md](docs/prompting.md)** lists every instrument, style and clause it knows, with tested examples. In short, a prompt is what it is, then the music, then tempo, key and length:

```
hip hop drum loop, standard kit, swung, with ghost notes, 90 BPM, 4 bars
finger bass bassline, over Cm - Fm - G7, sparse, 95 BPM, C minor, 4 bars
electric piano chords, chords Am7 - D9 - Gmaj7, smooth, sustained, 100 BPM, G major, 2 bars
analog mono lead synth melody, over Am - F - C - G, laid-back, 110 BPM, A minor, 4 bars
808 kit snare hit, one-shot, hard
grand piano chord, Cmaj7/E, rolled, first inversion, soft
single cello note, G3
```

Set the duration to the bars you ask for: seconds = bars × 240 ÷ BPM. 50 steps and CFG 6 (the defaults) are what it was tested with. Results vary by seed, so ask for several variations.

## Limits

- **Music first.** SFX, foley and field recordings are weak.
- **Wording.** It follows the vocabulary in the prompting guide best; far-off phrasings ("120bpm", "strumming") follow less reliably.
- **Timbre.** Most instruments come from the GeneralUser GS SoundFont and sound like General MIDI samples, dry.
- **4/4 only**, 1, 2 or 4 bars, at most 16 s.
- **The autoencoder** sets a ceiling on quality, especially in the top octave, on clicks and on noise textures.

## Data and licence

The code and weights are MIT-licensed ([LICENSE](LICENSE)). [NOTICE](NOTICE) credits the parts that come from elsewhere: the ACE-Step 1.5 VAE (MIT), T5-base (Apache 2.0) and stable-audio-tools (MIT).

Training data:
- **Freesound clips tagged CC0**, about 276k after a provenance review that excluded 2,762 clips: generative-AI outputs and voice clones, commercial packs, Apple Loops, game, film and YouTube rips, and named Amen breaks. A CC0 tag is the uploader's claim; the review screened for song-like material and stated sources.
- **Synthetic music**, 1.53M items rendered by our own procedural generators (beats, drum hits, chords, solo instruments, loops, electronic and acoustic pieces), each with a caption computed from the notes that were played. Most of it is rendered through the [GeneralUser GS](https://schristiancollins.com/generaluser) SoundFont, whose author allows its use "without restriction for your own music creation, private or commercial" and notes that the origin of some of its samples is uncertain. The rest is pure synthesis.

The model card on Hugging Face has the evaluation and more detail.
