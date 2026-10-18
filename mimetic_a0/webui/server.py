"""A small local web UI for mimetic-a0: text to audio, "retake" (regenerate existing audio towards a
new prompt) and "repaint" (regenerate one stretch, keeping the rest). One process, no other services.

  mimetic-a0-webui                       # http://127.0.0.1:8799
  mimetic-a0-webui --port 9000 --half    # another port; fp16 weights
  mimetic-a0-webui --host 0.0.0.0        # reachable from other machines on your network
"""
import argparse
import base64
import io
import threading
from pathlib import Path

import soundfile as sf
import torch
import torchaudio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from stable_audio_tools.inference.generation import generate_diffusion_cond, generate_diffusion_cond_inpaint

from .. import REPO_ID, generate, load_model, pick_device
from ..generate import max_seconds, peak_normalise, resolve_seed

app = FastAPI(title="mimetic-a0")

_lock = threading.Lock()          # one generation at a time
STATE: dict = {}                  # model, config, device, label; filled by main() before serving


def wav_b64(x: torch.Tensor, sr: int) -> str:
    """(channels, samples) float -> base64 of a peak-normalised 24-bit WAV."""
    buf = io.BytesIO()
    sf.write(buf, peak_normalise(x.float().cpu()).T.numpy(), sr, format="WAV", subtype="PCM_24")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def load_upload(data: bytes) -> tuple[int, torch.Tensor]:
    try:
        x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        return sr, torch.from_numpy(x.T.copy())
    except Exception:
        try:   # formats libsndfile can't read (e.g. some m4a) via torchaudio's backends
            x, sr = torchaudio.load(io.BytesIO(data))
            return sr, x
        except Exception as e:
            raise HTTPException(400, f"could not read the audio file: {e}")


def to_model_audio(sr, waveform, sample_rate, n_max):
    """Upload -> (2, n) float at the model rate, at most n_max samples."""
    x = waveform.float()
    if x.shape[0] == 1:
        x = x.repeat(2, 1)
    x = x[:2]
    if sr != sample_rate:
        x = torchaudio.functional.resample(x, sr, sample_rate)
    return x[:, :n_max]


# ---------------------------------------------------------------- API ----

@app.get("/api/info")
def api_info():
    cfg = STATE["config"]
    return {"label": STATE["label"], "device": STATE["device"], "max_seconds": round(max_seconds(cfg), 2),
            "sample_rate": cfg["sample_rate"]}


@app.post("/api/generate")
def api_generate(
    prompt: str = Form(...),
    seconds: float = Form(4.0),
    steps: int = Form(50),
    cfg_scale: float = Form(6.0),
    seed: int = Form(-1),
    n: int = Form(1),
    apg_scale: float = Form(1.0),
):
    model, cfg = STATE["model"], STATE["config"]
    n = max(1, min(n, 8))
    with _lock:
        audio, seed = generate(model, cfg, prompt, seconds, n=n, seed=seed, steps=steps,
                               cfg_scale=cfg_scale, apg_scale=apg_scale)
    results = [{"audio_b64": wav_b64(x, cfg["sample_rate"]), "index": i} for i, x in enumerate(audio)]
    return {"results": results, "seed": seed}


def _from_audio(fn, prompt, seconds, steps, cfg_scale, seed, apg_scale, **kw):
    model, cfg = STATE["model"], STATE["config"]
    cond = [{"prompt": prompt, "seconds_start": 0, "seconds_total": seconds}]
    with torch.no_grad():
        return fn(
            model, steps=steps, cfg_scale=cfg_scale, conditioning=cond, batch_size=1,
            sample_size=cfg["sample_size"], seed=seed, device=STATE["device"], apg_scale=apg_scale, **kw)


@app.post("/api/retake")
async def api_retake(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    change_amount: float = Form(0.65),
    seconds: float = Form(0.0),
    steps: int = Form(50),
    cfg_scale: float = Form(6.0),
    seed: int = Form(-1),
    apg_scale: float = Form(1.0),
):
    cfg = STATE["config"]
    in_sr, waveform = load_upload(await file.read())
    limit = max_seconds(cfg)
    seconds = min(seconds if seconds > 0 else waveform.shape[-1] / in_sr, limit)
    change_amount = max(0.0, min(1.0, change_amount))
    seed = resolve_seed(seed)
    with _lock:
        audio = _from_audio(generate_diffusion_cond, prompt, seconds, steps, cfg_scale, seed, apg_scale,
                             init_audio=(in_sr, waveform), init_noise_level=change_amount)
    x = audio[0][:, : int(seconds * cfg["sample_rate"])]
    return {"audio_b64": wav_b64(x, cfg["sample_rate"]), "seed": seed}


@app.post("/api/repaint")
async def api_repaint(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    mask_start: float = Form(...),
    mask_end: float = Form(...),
    softness: float = Form(0.15),
    steps: int = Form(50),
    cfg_scale: float = Form(6.0),
    seed: int = Form(-1),
    apg_scale: float = Form(1.0),
):
    cfg, device = STATE["config"], STATE["device"]
    sr = cfg["sample_rate"]
    in_sr, waveform = load_upload(await file.read())
    seconds = min(waveform.shape[-1] / in_sr, max_seconds(cfg))
    mask_start = max(0.0, min(mask_start, seconds))
    mask_end = max(mask_start, min(mask_end, seconds))
    softness = max(0.0, min(softness, (mask_end - mask_start) / 2))
    seed = resolve_seed(seed)

    n_samples = int(seconds * sr)
    # 0 = regenerate, 1 = keep, with a hann taper at each edge to avoid a click at the seam
    mask = torch.ones(1, n_samples, device=device)
    s, e = int(mask_start * sr), int(mask_end * sr)
    soft_n = max(1, int(softness * sr))
    mask[:, s:e] = 0.0
    taper = torch.hann_window(soft_n * 2, periodic=False, device=device)[:soft_n]
    l0, l1 = max(0, s - soft_n), s
    mask[:, l0:l1] = torch.flip(taper[: l1 - l0], dims=[0])
    r0, r1 = e, min(mask.shape[1], e + soft_n)
    mask[:, r0:r1] = taper[: r1 - r0]

    with _lock:
        audio = _from_audio(generate_diffusion_cond_inpaint, prompt, seconds, steps, cfg_scale, seed, apg_scale,
                             init_audio=(in_sr, waveform),
                         inpaint_audio=(in_sr, waveform), inpaint_mask=mask)
    # outside the selected stretch the result is the uploaded audio itself, with the same crossfade
    x = audio[0][:, :n_samples].float().cpu()
    orig = to_model_audio(in_sr, waveform, sr, n_samples)
    orig = torch.nn.functional.pad(orig, (0, n_samples - orig.shape[1]))
    keep = mask.float().cpu()
    x = orig * keep + x * (1 - keep)
    return {"audio_b64": wav_b64(x, sr), "seed": seed}


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "index.html").read_text()


def main():
    ap = argparse.ArgumentParser(description="mimetic-a0 web UI")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve your whole network")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--model", default=REPO_ID, help="Hugging Face repo id or local folder")
    ap.add_argument("--device", help="cuda, mps or cpu (default: best available)")
    ap.add_argument("--half", action="store_true", help="fp16 weights: less memory, faster")
    a = ap.parse_args()

    import uvicorn
    device = pick_device(a.device)
    print(f"loading {a.model} on {device}{' (fp16)' if a.half else ''} ...")
    model, config = load_model(a.model, device, a.half)
    STATE.update(model=model, config=config, device=device,
                 label=f"mimetic-a0 · {device}{' · fp16' if a.half else ''}")
    print(f"mimetic-a0 web UI: http://{a.host}:{a.port}")
    uvicorn.run(app, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
