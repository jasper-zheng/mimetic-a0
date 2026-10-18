---
license: mit
library_name: stable-audio-tools
pipeline_tag: text-to-audio
tags:
- audio
- music
- text-to-audio
- diffusion
- cc0
---

# mimetic-a0

A text-to-audio model for music, trained only on audio with a clean licence: Freesound clips released as CC0, and synthetic music rendered by our own procedural generators. It writes 48 kHz stereo, up to 16 s: drum loops, basslines, chords, melodies, pads, one-shots and full mixes, at the tempo, key and chords you ask for.

Version 0.1, an early release. Internally it is cc0-sampler v4, checkpoint "anneal 120k".

**Run it:** [github.com/micknoise/mimetic-a0](https://github.com/micknoise/mimetic-a0) has a command-line tool and a local web UI (generate, retake, repaint) for NVIDIA GPUs, Apple Silicon Macs and the CPU.

## Examples

Unedited takes, 50 steps, CFG 6, one seed each.

| Prompt | Length | Audio |
|---|---|---|
| `boom bap drum loop, standard kit, swung, with ghost notes, 90 BPM, 4 bars` | 10.67 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/boom-bap.wav"></audio> |
| `house drum loop, dance kit, open hi-hats, 124 BPM, 4 bars` | 7.74 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/house.wav"></audio> |
| `jazz swing drum loop, brush kit, heavily swung, 120 BPM, 2 bars` | 4 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/jazz-brushes.wav"></audio> |
| `808 kit kick drum hit, one-shot, hard` | 1 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/808-kick.wav"></audio> |
| `warm pad held chords, chords Dm7 - G7 - Cmaj7, soft, 80 BPM, C major, 4 bars` | 12 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/warm-pad.wav"></audio> |
| `analog mono lead synth melody, over Am - F - C - G, 110 BPM, A minor, 4 bars` | 8.73 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/analog-lead.wav"></audio> |
| `marimba arpeggio, chords C - Am - F - G, 120 BPM, C major, 2 bars` | 4 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/marimba.wav"></audio> |
| `single cello note, G3` | 3 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/cello-g3.wav"></audio> |
| `grand piano chord, Cmaj7, block chord` | 3 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/piano-cmaj7.wav"></audio> |
| `steel-string acoustic guitar chord, G, strummed` | 3 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/guitar-g.wav"></audio> |
| `full mix with standard kit, finger bass and electric piano, hip hop, chords Fm7 - Bbm7, 88 BPM, Ab major, 4 bars` | 10.91 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/hip-hop-band.wav"></audio> |
| `full mix with drum machine, synth bass and synth pad, house, Am7 chord, 124 BPM, root A, 4 bars` | 7.74 s | <audio controls src="https://huggingface.co/micknoisemachine/mimetic-a0/resolve/main/examples/house-track.wav"></audio> |

## Usage

With the [mimetic-a0](https://github.com/micknoise/mimetic-a0) package:

```bash
git clone https://github.com/micknoise/mimetic-a0 && cd mimetic-a0 && uv sync
uv run mimetic-a0-webui                     # http://127.0.0.1:8799
uv run mimetic-a0 "finger bass bassline, over Cm - Fm - G7" --bpm 95 --bars 4 -n 4
```

With stock [stable-audio-tools](https://github.com/Stability-AI/stable-audio-tools) (commit `3241adb` or later):

```python
import torch, torchaudio
from stable_audio_tools import get_pretrained_model
from stable_audio_tools.inference.generation import generate_diffusion_cond

model, config = get_pretrained_model("micknoisemachine/mimetic-a0")
model = model.to("cuda").eval()             # or "mps" on Apple Silicon
bpm, bars = 90, 4
seconds = bars * 240 / bpm
audio = generate_diffusion_cond(
    model, steps=50, cfg_scale=6, sample_size=config["sample_size"], seed=1, device="cuda",
    conditioning=[{"prompt": "boom bap drum loop, standard kit, swung, 90 BPM, 4 bars",
                   "seconds_start": 0, "seconds_total": seconds}],
)
audio = audio[0, :, : int(seconds * 48000)].float().cpu()
torchaudio.save("out.wav", audio / audio.abs().max() * 0.9, 48000)
```

It does not load in ComfyUI's Stable Audio nodes, which expect Stable Audio Open's autoencoder.

## Files

| File | |
|---|---|
| `model.safetensors` | the full model in fp32 (2.0 GB): diffusion transformer (EMA weights), conditioners and the autoencoder; no training state |
| `model.fp16.safetensors` | the same in fp16 (1.0 GB); a seed gives a slightly different take than in fp32 |
| `model_config.json` | stable-audio-tools model config |
| `PROMPTING.md` | the prompting guide |
| `examples/` | the clips above |
| `LICENSE`, `NOTICE` | MIT; third-party credits |

## Prompting

The model learned almost everything it knows from captions written by its own data generators, so it follows that wording best. **[PROMPTING.md](https://huggingface.co/micknoisemachine/mimetic-a0/blob/main/PROMPTING.md)** lists every instrument, style and clause it knows, with tested examples. In short, a prompt is what it is, then the music, then tempo, key and length, and the duration should match the bars (seconds = bars × 240 ÷ BPM):

```
hip hop drum loop, standard kit, swung, with ghost notes, 90 BPM, 4 bars
electric piano chords, chords Am7 - D9 - Gmaj7, smooth, sustained, 100 BPM, G major, 2 bars
grand piano chord, Cmaj7/E, rolled, first inversion, soft
single cello note, G3
```

## Model

- A 326M-parameter diffusion transformer (1024 wide, 16 layers, 16 heads), rectified flow, in the latent space of the **ACE-Step 1.5 VAE** (MIT; Oobleck architecture, 48 kHz stereo, 64 channels at 25 Hz), which was used frozen as a codec. 511M parameters in all.
- Conditioned on a frozen **T5-base** text encoder (128 tokens) and on `seconds_start` / `seconds_total`, with padding masks for clips shorter than the 16 s window.
- Trained from scratch with stock stable-audio-tools on 2× RTX PRO 6000: batch 256, learning rate 1e-4 (InverseLR) to step 100k, then annealed linearly from 4e-5 to 4e-6 over 20k steps (this checkpoint is the end of that anneal).

## Training data

- **Freesound, CC0 only (35% of draws).** About 276k clips (up to 30 s each), after a provenance review that excluded 2,762 clips on clear evidence: generative-AI outputs and voice clones; commercial packs, Apple Loops, game, film and YouTube rips; two broadcast sound-effects libraries; named Amen breaks. Prompts are rebuilt from each clip's title, tags and description.
- **Synthetic music (65%).** 1.53M items rendered by our own procedural generators: beats in 17 styles, drum one-shots, chords from triads to 13ths, single notes and phrases for each instrument, loops, electronic tracks and band and orchestral pieces. Each item is cut into bar-aligned windows of 1, 2 or 4 bars, each with a caption computed from the notes actually played there: instruments heard, chords in order, density, swing, articulation, dynamics, tempo, key and length. Most instruments are rendered through the **GeneralUser GS** SoundFont (v2.0.3, S. Christian Collins), dry; a synth engine renders the rest, keeping its reverb and delay.

**About the GeneralUser GS SoundFont:** its author allows its use "without restriction for your own music creation, private or commercial". Its author also notes that the origin of some of its samples is uncertain, though none came from commercial packs. Most of the synthetic data rests on it.

**About the CC0 tags:** a CC0 tag is the uploader's claim. The review screened for song-like material (with CLAP and AcoustID fingerprints, which found no named commercial recordings) and for stated sources, but an unlabelled clip could still slip through.

## Evaluation

The checks below compare the base checkpoint at 100k, where the anneal started, with our earlier model (cc0-sampler v2, 200k steps). They use held-out generator seeds for ground truth (tempo, pitch, chords, instruments) and 44 earlier prompts × 4 seeds for CLAP prompt match. The anneal (105k–120k) stayed within noise of 100k on every measure, with slightly cleaner takes.

| | mimetic-a0 base (100k) | cc0-sampler v2 |
|---|---|---|
| Tempo on beat prompts | 209/272 | 210/272 |
| Held-out tempo | 83% | 67% |
| Tempo from the BPM in the text | 88% | 68% |
| Pitch of single notes | 94% | 84% |
| Chords | 77% | 18% |
| Instrument identification | 41% | 38% |
| CLAP prompt match: beats / synth parts / instruments | 0.399 / 0.267 / 0.194 | 0.388 / 0.275 / 0.244 |

CLAP scores the GeneralUser GS instruments below real recordings, which pulls its instrument score down.

## Intended use and limits

For making samples and parts for music: loops, one-shots, basslines, chords, melodies and sketches of full mixes.

- **Music first.** SFX, foley and field recordings are weak.
- **Wording.** It follows the vocabulary in PROMPTING.md best; far-off phrasings ("120bpm", "strumming") follow less reliably.
- **Timbre.** Most instruments sound like General MIDI samples, dry.
- **4/4 only**, 1, 2 or 4 bars, at most 16 s.
- **The autoencoder** sets a ceiling on quality: upper harmonics are 16 dB down at 15–20 kHz, there is some aliasing above 5 kHz, clicks come out softer, and noise textures can be up to 10 dB off.
- **Tempo** on fast, busy beats (trap, drum and bass) is less reliable; take several variations.

## Licence

MIT ([LICENSE](https://huggingface.co/micknoisemachine/mimetic-a0/blob/main/LICENSE)) for the weights, including the ACE-Step 1.5 VAE weights inside them, which are MIT-licensed by their authors. T5-base (Apache 2.0) is downloaded separately at run time. See [NOTICE](https://huggingface.co/micknoisemachine/mimetic-a0/blob/main/NOTICE) for credits.
