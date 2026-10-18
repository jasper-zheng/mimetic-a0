# Releasing mimetic-a0 0.1 (from a MacBook)

Instructions for the agent on the release MacBook. Work through the steps in order and report back at the end of each numbered step. Stop and ask the user before anything public: both repos stay **private** until the user says otherwise.

The packages were built and tested on the training workstation (Linux, CUDA, and its CPU). **Nothing has run on Apple Silicon yet.** Step 3 is the first real test of the MPS path.

## What is where

- This repo (`micknoise/mimetic-a0`, private on GitHub): the CLI (`mimetic-a0`), the web UI (`mimetic-a0-webui`) and the docs. `huggingface/` holds the text files of the Hugging Face repo: model card (`README.md`), `PROMPTING.md` (the same file as `docs/prompting.md`), `LICENSE`, `NOTICE`, `model_config.json` and `SHA256SUMS`.
- The large files are on the workstation `mimetic@100.124.240.83` (reached over Tailscale) in `/home/mimetic/workspace/mimetic-a0-hf-build/hf/`: `model.safetensors` (2.0 GB, fp32), `model.fp16.safetensors` (1.0 GB) and `examples/*.wav` (14 clips, 28 MB).
- The model is cc0-sampler v4, checkpoint "anneal 120k". `model.safetensors` is bit-identical to it. Do not modify, re-export or re-quantise the weights.

## 1. Set up

```bash
brew install uv gh            # if missing; git comes with the Xcode command line tools
gh auth status                # must be logged in as micknoise
gh repo clone micknoise/mimetic-a0 && cd mimetic-a0
uv sync                       # Python 3.11, torch 2.7.1 (macOS arm64 wheel), stable-audio-tools at 3241adb
uv run python -c "import torch; print(torch.__version__, 'mps', torch.backends.mps.is_available())"
```

Expect `2.7.1 mps True`. If `uv sync` fails on any package, report the exact error. Pins worth knowing: `numpy<2` (stable-audio-tools' PyWavelets 1.4.1 breaks on numpy 2), `transformers<5`, and `pytorch_lightning`, which stable-audio-tools imports at load time.

## 2. Fetch and assemble the Hugging Face folder

```bash
mkdir -p release
rsync -av --progress mimetic@100.124.240.83:/home/mimetic/workspace/mimetic-a0-hf-build/hf/model.safetensors \
  mimetic@100.124.240.83:/home/mimetic/workspace/mimetic-a0-hf-build/hf/model.fp16.safetensors \
  mimetic@100.124.240.83:/home/mimetic/workspace/mimetic-a0-hf-build/hf/examples release/
cp huggingface/* release/
(cd release && shasum -a 256 -c SHA256SUMS)     # every line must say OK
```

`release/` is gitignored. It is exactly what gets uploaded to Hugging Face in step 5. `SHA256SUMS` goes up with it.

## 3. Test on Apple Silicon

Use the local weights (`--model release`) for every test, so nothing depends on Hugging Face yet. Record how long each command takes. Keep all console output; in particular, look for warnings containing `not currently supported on the MPS backend` (an op fell back to the CPU, which is allowed but should be reported) and for any NaN or error.

**CLI, fp32 and fp16:**

```bash
mkdir -p outs
time uv run mimetic-a0 "single cello note, G3" --seconds 3 --seed 1 --model release --out outs
time uv run mimetic-a0 "boom bap drum loop, standard kit, swung, with ghost notes" --bpm 90 --bars 4 -n 2 --seed 1 --model release --out outs
time uv run mimetic-a0 "warm pad held chords, chords Dm7 - G7 - Cmaj7, soft" --bpm 80 --bars 4 --half --seed 1 --model release --out outs
```

Each must print `on mps` and write WAVs. Check that every file is sound and not silence, noise or NaN:

```bash
uv run python - <<'EOF'
import glob, numpy as np, soundfile as sf
for f in sorted(glob.glob("outs/*.wav")):
    x, sr = sf.read(f)
    print(f"{f}: {x.shape[0]/sr:.2f} s, {sr} Hz, peak {np.abs(x).max():.3f}, rms {np.sqrt((x**2).mean()):.4f}, nan {np.isnan(x).any()}")
EOF
```

Expected: 3.00 s, 10.67 s and 12.00 s at 48000 Hz; rms well above 0.001; no NaN. If `--half` gives silence or NaN while fp32 is fine, the likely cause is the fp16 path on MPS. Report it; the fix would be to keep the T5 text encoder or the VAE in fp32 under `--half` (`mimetic_a0/model.py`).

Seeds do not reproduce the workstation's audio on a Mac (the noise is drawn differently on MPS), so don't compare against those files.

**Web UI:**

```bash
uv run mimetic-a0-webui --model release --port 8799 > outs/webui.log 2>&1 &
sleep 30; curl -s localhost:8799/api/info; echo           # expect "device":"mps"
curl -s -F prompt="house drum loop, dance kit, open hi-hats, 124 BPM, 2 bars" -F seconds=3.87 -F n=2 -F seed=3 \
  localhost:8799/api/generate | uv run python -c "import sys,json,base64;d=json.load(sys.stdin);open('outs/gen0.wav','wb').write(base64.b64decode(d['results'][0]['audio_b64']));print('generate ok', len(d['results']))"
curl -s -F file=@outs/gen0.wav -F prompt="techno drum loop, 808 kit, 124 BPM, 2 bars" -F change_amount=0.5 \
  localhost:8799/api/retake | uv run python -c "import sys,json;d=json.load(sys.stdin);print('retake ok', 'audio_b64' in d)"
curl -s -F file=@outs/gen0.wav -F prompt="house drum loop, dance kit, 124 BPM, 2 bars" -F mask_start=1.0 -F mask_end=2.5 \
  localhost:8799/api/repaint | uv run python -c "import sys,json,base64;d=json.load(sys.stdin);open('outs/rep.wav','wb').write(base64.b64decode(d['audio_b64']));print('repaint ok')"
uv run python -c "
import soundfile as sf, numpy as np
a,_=sf.read('outs/gen0.wav'); b,_=sf.read('outs/rep.wav'); n=int(0.8*48000)
print('repaint keeps the start:', np.corrcoef(a[:n,0], b[:n,0])[0,1] > 0.999)"
grep -i "error\|traceback\|mps backend" outs/webui.log
```

Then ask the user to open http://127.0.0.1:8799 in a browser and try Generate (click a few example prompts), Retake and Repaint by ear. Leave the server running until they are done, then stop it by its PID (`kill <pid>`; don't use `pkill -f`).

**If something fails on MPS:** first retry with `--device cpu` to separate MPS problems from general ones. Fix as little as possible, in `mimetic_a0/` only (never in the installed stable-audio-tools), and re-run the whole of step 3. Commit each fix with a message that says what failed on MPS and why. Update the README's macOS notes if behaviour differs from what it says (speed, memory, `--half`).

Report: timings, peak memory if easy to see (Activity Monitor), any fallback warnings, and the user's verdict from listening.

## 4. Listen to the example clips

The 14 clips in `release/examples/` were picked by automatic checks (CLAP instrument class, tempo, pitch, chord), not by ear. Ask the user to listen to them, for example with `open release/examples`. Each one comes from the prompt shown next to it in the model card's Examples table (`release/README.md`). If the user wants one replaced, the workstation has a second seed for every prompt in `/home/mimetic/workspace/mimetic-a0-hf-build/example_takes/` (`NN_s1_*` and `NN_s2_*`). Copy the chosen take over the file of the same name in `release/examples/`, then regenerate `SHA256SUMS` for the examples and copy it back to `huggingface/SHA256SUMS`.

## 5. Upload to Hugging Face (private)

```bash
uv tool install "huggingface_hub[cli]"     # provides `hf`
hf auth login                               # the user pastes a micknoise write token
hf auth whoami                              # must say micknoise
hf repo create micknoise/mimetic-a0 --private
hf upload micknoise/mimetic-a0 release . --commit-message "mimetic-a0 0.1"
```

Then check it from Hugging Face rather than the local folder, in a clean cache:

```bash
HF_HOME=$(mktemp -d) HF_TOKEN=$(cat ~/.cache/huggingface/token) \
  uv run mimetic-a0 "single grand piano note, C4, soft" --seconds 3 --seed 1 --out outs/hf
```

It must download `model_config.json` and `model.safetensors` from `micknoise/mimetic-a0` and write a WAV. While the repo is private, the download needs the token; that is what the `HF_TOKEN` above is for. Check that the model card renders on the website, including the audio players in the Examples table. They use `resolve/main/examples/...` URLs, which only play for a logged-in owner while the repo is private.

## 6. Finish

- Commit and push any changes to `micknoise/mimetic-a0`, including an updated `huggingface/` if the card or examples changed. If the card changed after step 5, upload it again.
- Do **not** make either repo public. Report to the user that both are ready. They flip visibility themselves: on GitHub with `gh repo edit micknoise/mimetic-a0 --visibility public --accept-visibility-change-consequences`, and on Hugging Face under the repo's Settings.
- The model card links to this GitHub repo. Once the user has made both public, check that the links work.
