# mimetic-a0 in max/msp

**Run mimetic-a0 locally in Max/MSP (Apple Silicon GPU).**  
These scripts export mimetic-a0 to Max/MSP, using the [`neural.gen~`](https://github.com/jasper-zheng/neural_tilde) object. The model runs on the Apple Silicon GPU through an [ExecuTorch](https://pytorch.org/executorch/) MLX backend. 

**GPU acceleration:** On an M4 Max, an 8 s clip takes **1.4 s at 24 steps**. For comparison, PyTorch on the GPU (MPS) takes 2.4 s on the same clip.

**Example Patch:**  
<img src="docs/interface.jpg" width="500">

## Requirements

### Run the pre-exported model
- An Apple Silicon Mac, peak at 14 GB in fp32.
- Max 9 with the **neural_tilde** package (0.1.0 or later). Get neural_tilde from its [releases page](https://github.com/jasper-zheng/neural_tilde/releases).
- Open the example patch `example-patch/mimetic-a0-8s.maxpat`, the first tab will guide you to download the pre-exported model.

### Export the model yourself
- [uv](https://docs.astral.sh/uv/) package manager, for the Python environment.

## Export

Clone this repo:
```bash
git clone https://github.com/jasper-zheng/mimetic-a0.git
```

The exporting pipeline has its own environment (i.e., ExecuTorch 1.5.1 needs PyTorch 2.14 while mimetic-a0 uses 2.7.1), to setup:

```bash
cd mimetic_a0/maxmsp
uv sync
```
Command for exporting:
```bash
uv run python export_text_to_audio.py   # default: 8 s, 24 steps, fp32
```
**Note #1:** The export can takes several minutes.  

**Note #2:** Generation length, sampling steps, and precision are fixed at export. The exported model can generate any length up to the export length. To change these parameters, re-run the export with flags:

```bash
uv run python export_text_to_audio.py --seconds 12   # export 12 s
uv run python export_text_to_audio.py --steps 16     # number of diffusion steps
uv run python export_text_to_audio.py --half         # fp16
```

Other flags:
- `--model <repo|folder>` to export local weights.
- `--seed N` sets the seed `neural.gen~` starts with.
- `--out <folder>` (default `artifacts/`).

Each export writes four files to `artifacts/`:

| file | content |
|---|---|
| `<model_name>.pte` | the model |
| `<model_name>.json` | model metadata: inputs, attributes, output |
| `<model_name>.tokenizer.json` and `<model_name>.tokenizer.config.json` | the tokenizer for `neural.tokenizer` |


## Use in Max

**The example patch:** open `example-patch/mimetic-a0-8s.maxpat`. It is set to `mimetic-a0_t2a_8s_24steps`. To use your own export, add `artifacts/` to Max's search path (Options - File Preferences) and change the model name in the patch's `neural.tokenizer`, `neural.gen~` and `neural.info` boxes.

**Two objects:**
- `[neural.tokenizer <model_name>]` turns a prompt into `input_ids` and `attention_mask`.
- `[neural.gen~ <model_name> forward <buffer>]` takes `input_ids` and `attention_mask` as the first two inlets, then a `generate` message to generate. It also takes a `set` message to set the output buffer.

**Attributes of the exported model in `neural.gen~`:**

| attribute | range | what it does |
|---|---|---|
| `seconds_total` | 0 – S, default S | the duration the model aims for |
| `cfg_scale` | 1 – 15, default 6 | guidance; 1 = none |
| `seed` | | the starting noise; the same seed gives the same clip |

**Sample rate:** the buffer is set to 48 kHz, and `play~` / `groove~` resample it, so clips play at the right pitch in a 44.1 kHz session.

## How it works

`modules.py` rebuilds stock `generate()` as one graph with fixed shapes. It calls the stock stable-audio-tools modules, so their code is unchanged:

1. **Conditioning:** T5-base, in fp16 as stock runs it.
2. **Padding mask:** built inside the graph from `seconds_total`.
3. **Sampler:** the Euler steps, unrolled, with batch-2 classifier-free guidance using APG. The step schedule is fixed at export.
4. **Decoder:** the VAE decoder.

`export_text_to_audio.py` hands this graph to neural_tilde's `GenModule`, which lowers it to MLX.

## Limits

- neural_tilde v0.1.0 or later supports Windows/CUDA, but it is not tested here. 
- **Length and steps are fixed per export.** Any lenght up to `seconds_total` works at runtime. 
- **Memory:** generating takes about 13.6 GB at peak in the Python runtime, mostly due to the decoder working on 48 kHz audio. This was measured on a 48 GB machine.
- The first inference after loading might be a bit slower, as it also compiles the GPU kernels.

## Licence

An exported `.pte` contains the mimetic-a0 weights (MIT) and T5-base (Apache 2.0); see [NOTICE](../../NOTICE).

The exporter ([neural-tilde](https://pypi.org/project/neural-tilde/)) and the Max externals that run the export are © Jasper Shuoyang Zheng, licensed [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (non-commercial). They are installed separately and not included here.
