"""Models. Each has .predict(record, window) -> dict merged into the record's "pred".

`window` is a deque of the last N records, so time-series models get history for free.
All imports are lazy: a missing package breaks only the model that needs it.
"""
from __future__ import annotations

import sys
import time


class Model:
    name = "base"
    warmup_note = ""

    def load(self) -> None:  # override for heavy setup
        pass

    def predict(self, record: dict, window) -> dict:
        raise NotImplementedError


# --------------------------------------------------------------------------
class Passthrough(Model):
    """No model. Wiring test: proves source -> pipeline -> UI -> sink works."""

    name = "passthrough"

    def predict(self, record, window):
        keys = [k for k in record if not k.startswith("_") and k != "t"]
        return {"label": "ok", "score": 1.0, "detail": f"{len(keys)} channels: {', '.join(keys[:6])}"}


# --------------------------------------------------------------------------
class Threshold(Model):
    """Dumb baseline. Always have one — it tells you whether the FM is earning
    its keep, and it is a working demo when the FM won't load."""

    name = "threshold"

    def __init__(self, channel: str = "soil", low: float = 500.0, high: float = 10**9):
        self.channel, self.low, self.high = channel, low, high

    def predict(self, record, window):
        v = record.get(self.channel)
        if v is None:
            return {"label": "no-signal", "score": 0.0}
        if v < self.low:
            return {"label": "below", "score": 1.0, "detail": f"{self.channel}={v} < {self.low}"}
        if v > self.high:
            return {"label": "above", "score": 1.0, "detail": f"{self.channel}={v} > {self.high}"}
        return {"label": "normal", "score": 1.0, "detail": f"{self.channel}={v}"}


# --------------------------------------------------------------------------
def _feat(out):
    """transformers>=5 returns a ModelOutput from get_*_features; <5 returned a
    bare tensor. Normalise to the 512-d joint-space embedding either way."""
    if hasattr(out, "pooler_output"):
        out = out.pooler_output
    return out / out.norm(dim=-1, keepdim=True)


class Clap(Model):
    """Zero-shot audio classification with LAION CLAP.

    No training data. You write the class names in plain English at runtime:
        --labels "a kettle boiling,glass breaking,a vacuum cleaner,silence"

    ~600 MB download, runs on CPU in roughly 0.3-1.0 s per 3 s window.
    """

    name = "clap"
    warmup_note = "first run downloads ~600MB from HuggingFace"

    def __init__(self, labels: list[str], checkpoint: str = "laion/clap-htsat-unfused",
                 min_rms: float = 0.004):
        self.labels = labels
        self.checkpoint = checkpoint
        self.min_rms = min_rms
        self.model = None
        self.processor = None
        self._text = None

    def load(self):
        import torch
        from transformers import ClapModel, ClapProcessor

        torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        print(f"[clap] loading {self.checkpoint} (cpu)...", file=sys.stderr)
        t0 = time.time()
        self.processor = ClapProcessor.from_pretrained(self.checkpoint)
        self.model = ClapModel.from_pretrained(self.checkpoint).eval()
        # Text embeddings are fixed for the run: compute once.
        with torch.no_grad():
            ti = self.processor(text=self.labels, return_tensors="pt", padding=True)
            self._text = _feat(self.model.get_text_features(**ti))
        print(f"[clap] ready in {time.time() - t0:.1f}s, {len(self.labels)} labels",
              file=sys.stderr)

    def predict(self, record, window):
        import torch

        audio = record.get("_audio")
        if audio is None:
            return {"label": "no-audio", "score": 0.0}
        if record.get("rms", 1.0) < self.min_rms:
            return {"label": "silence", "score": 1.0, "detail": "below noise gate"}

        sr = record.get("_samplerate", 48000)
        with torch.no_grad():
            ai = self.processor(audio=audio, sampling_rate=sr, return_tensors="pt")
            a = _feat(self.model.get_audio_features(**ai))
            probs = (100.0 * a @ self._text.T).softmax(dim=-1)[0]

        ranked = sorted(zip(self.labels, probs.tolist()), key=lambda x: -x[1])
        return {
            "label": ranked[0][0],
            "score": round(ranked[0][1], 4),
            "all": [{"label": l, "score": round(s, 4)} for l, s in ranked],
        }


# --------------------------------------------------------------------------
class Chronos(Model):
    """Time-series forecasting FM. Forecasts one channel N steps ahead and
    reports when it will cross a threshold — e.g. "soil hits dry in 4 minutes".
    """

    name = "chronos"
    warmup_note = "needs `uv pip install chronos-forecasting`; ~50MB for chronos-bolt-small"

    def __init__(self, channel: str = "soil", horizon: int = 24, threshold: float | None = None,
                 checkpoint: str = "amazon/chronos-bolt-small", min_history: int = 64):
        self.channel, self.horizon, self.threshold = channel, horizon, threshold
        self.checkpoint, self.min_history = checkpoint, min_history
        self.pipe = None
        self._last = 0.0

    def load(self):
        from chronos import BaseChronosPipeline

        print(f"[chronos] loading {self.checkpoint} (cpu)...", file=sys.stderr)
        self.pipe = BaseChronosPipeline.from_pretrained(self.checkpoint, device_map="cpu")
        print("[chronos] ready", file=sys.stderr)

    def predict(self, record, window):
        import torch

        hist = [r[self.channel] for r in window if self.channel in r]
        if len(hist) < self.min_history:
            return {"label": "warming-up", "score": 0.0,
                    "detail": f"{len(hist)}/{self.min_history} samples"}

        # Forecasting is slow relative to sensor rate; throttle to ~1 Hz.
        now = time.time()
        if now - self._last < 1.0 and getattr(self, "_cache", None):
            return self._cache
        self._last = now

        q, _mean = self.pipe.predict_quantiles(
            torch.tensor(hist[-512:], dtype=torch.float32).unsqueeze(0),
            prediction_length=self.horizon,
            quantile_levels=[0.1, 0.5, 0.9],
        )
        median = q[0, :, 1].tolist()
        lo, hi = q[0, :, 0].tolist(), q[0, :, 2].tolist()

        out = {"label": "forecast", "score": 1.0, "forecast": [round(v, 3) for v in median],
               "lo": [round(v, 3) for v in lo], "hi": [round(v, 3) for v in hi],
               "channel": self.channel}
        if self.threshold is not None:
            cross = next((i for i, v in enumerate(median) if v < self.threshold), None)
            if cross is None:
                out["label"] = "safe"
                out["detail"] = f"stays above {self.threshold} for {self.horizon} steps"
            else:
                out["label"] = "will-cross"
                out["steps_to_cross"] = cross
                out["detail"] = f"{self.channel} crosses {self.threshold} in {cross} steps"
        self._cache = out
        return out


# --------------------------------------------------------------------------
def build(name: str, args) -> Model:
    if name == "passthrough":
        return Passthrough()
    if name == "threshold":
        return Threshold(channel=args.channel, low=args.low, high=args.high)
    if name == "clap":
        labels = [s.strip() for s in args.labels.split(",") if s.strip()]
        if not labels:
            raise SystemExit("--labels is required for the clap model")
        return Clap(labels=labels)
    if name == "chronos":
        return Chronos(channel=args.channel, horizon=args.horizon,
                       threshold=args.low if args.low > -10**8 else None)
    raise SystemExit(f"unknown model: {name}")


MODELS = ["passthrough", "threshold", "clap", "chronos"]
