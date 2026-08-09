# Foundation Model Physical AI hack

Sundai — 2026-08-09. **Demo at 8pm. No slides. Live demo over Zoom screenshare.**
Card + voting: `sundai.club/pitch` (top 5 pitch for 5 min).

## Idea
_TBD — team decides._

## The architecture

One spine serves nearly every idea in the Sundai deck:

```
board (dumb)                laptop (smart)
  sensors ──NDJSON over USB serial──▶ rolling window ──▶ foundation model
                                                             │
  relay/buzzer/LED ◀────command line────────── rule ◀────────┘
                                                  └──▶ .jsonl log + live web UI
```

**The model never runs on the MCU.** The board only reads sensors and prints JSON.

## Quickstart

```bash
# no hardware needed — synthetic sensors + UI, proves the whole chain
.venv/Scripts/python run.py

# what hardware can I see?
.venv/Scripts/python run.py --list

# zero-shot audio events (CLAP). You write the classes in plain English.
.venv/Scripts/python run.py --source audio --model clap \
  --labels "a kettle boiling,glass breaking,a vacuum cleaner,a person talking,silence" \
  --when "glass breaking" --action ALERT

# real board + time-series forecasting
.venv/Scripts/python run.py --source serial --port COM3 --model chronos \
  --channel soil --low 480 --when will-cross --action PUMP_ON

# demo insurance: replay a recorded run through the identical pipeline
.venv/Scripts/python run.py --source replay --file logs/run-XXXX.jsonl --model clap --labels "..."
```

UI at http://127.0.0.1:8000 — giant label, class-score bars, live plot with
forecast tail, action flash banner. Click the plot to cycle channels.

## What's verified working (CPU-only, no GPU on this machine)

| Piece | Status | Numbers |
|---|---|---|
| CLAP zero-shot audio | ✅ | 2.4 s cached load, **0.36 s** per 3 s window |
| Chronos-Bolt-small forecasting | ✅ | **0.22 s** per forecast, 12-step horizon |
| sim → model → rule → action → log | ✅ | rule fired, log written |
| record → replay through same pipeline | ✅ | 120 records at 50× |
| Web UI + websocket live push | ✅ | HTTP 200, live stream confirmed |

Hardware: Intel Arc 130V iGPU (no CUDA), 15.7 GB RAM. **Everything runs on CPU.**
This rules out OpenVLA (7B, needs ~16 GB VRAM + a robot arm we don't have) and
makes ImageBind painful. Audio and time-series are the viable lanes.

## Layout

```
run.py                            CLI entrypoint
sundai/sources.py                 sim | serial | replay | audio
sundai/models.py                  passthrough | threshold | clap | chronos
sundai/pipeline.py                the spine: window, rule, recorder, sinks
sundai/server.py + ui.html        live dashboard
firmware/arduino_stream/*.ino     Uno Rev3 / Nano 33 IoT / Uno Q sensor streamer
firmware/circuitpython/code.py    PyKit Ruler streamer
logs/                             every run auto-recorded as .jsonl
```

## Adding a model

Subclass `Model` in `sundai/models.py`, implement `predict(record, window) -> dict`
returning at least `{"label": str, "score": float}`. Add it to `build()` and `MODELS`.
If it returns an `all` list it gets score bars; a `forecast` list gets a dashed
plot tail. If the model fails to load the pipeline falls back to passthrough
rather than dying.

## Demo-day checklist

- [ ] Record a clean run by 18:00 → `logs/`. That file is the fallback.
- [ ] Screen-record one good live run as a video fallback.
- [ ] Test on the actual Zoom screenshare — check the UI is legible at their resolution.
- [ ] Have `--source replay` command in the clipboard, ready to paste.
- [ ] Submit the card at `sundai.club/pitch` well before 8pm.

## Team
- Nicholas Lutta
