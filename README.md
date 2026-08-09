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
handsfree/safety.py               kill switch (Ctrl+Alt+Q) + dead-man switch
handsfree/ui.py                   the one Tk thread every window runs on
handsfree/actions/                word → action registry + the --fire CLI
handsfree/beats.py                pre-analysed beat times → screen dot + Arduino LED
handsfree/breakwatch.py           stillness tracker + break prompt
media/beat_track.wav              demo song (regenerate: python -m handsfree.make_demo_track)
tests/test_bench.py               the Track B pass numbers from bench-plan.html
firmware/arduino_stream/*.ino     Uno Rev3 / Nano 33 IoT / Uno Q sensor streamer
firmware/circuitpython/code.py    PyKit Ruler streamer
logs/                             every run auto-recorded as .jsonl
```

## Hands-free HCI (the 9 Aug demo)

The camera turns your gesture into a **word**; the word turns into something
happening on the laptop. The two halves only meet at that string, so neither
side blocks the other — and the machine side is testable with no webcam at all:

```bash
python -m handsfree.actions --list                 # every word
python -m handsfree.actions --fire test_ping       # prove the seam
python -m handsfree.actions --fire mute_toggle --repeat 5 --interval 1
python -m handsfree.actions --fire privacy_blank --hold 10   # Esc dismisses
python -m handsfree.beats --seconds 20                        # LED on the beat
```

The eight contracted words, fixed and never renamed:

| Word | Does |
|---|---|
| `mute_toggle` | system mute + Zoom's own chord (Alt+A; Cmd+Shift+A on macOS) |
| `media_playpause` | media play/pause key |
| `privacy_blank` / `privacy_restore` | black fullscreen cover on every monitor; **Esc dismisses** |
| `playlist_open` | plays `media/beat_track.wav` |
| `led_beat_start` / `led_beat_stop` | pulses a screen dot and the Arduino LED on the beat |
| `break_prompt` | "you haven't moved" reminder |

Two rules that everything else depends on:

- **`Ctrl+Alt+Q` kills the process from anywhere.** Once the app is driving the
  mouse, this is how you take the machine back. Learn it before running anything.
- **No action ever blocks its caller.** Windows live on one shared Tk thread
  (`handsfree/ui.py`), so firing a word never stalls the gesture loop.

Beat times are extracted offline with librosa and cached; there is no live audio
capture anywhere, because that path is fiddly on Windows and can fail on stage.
Missing hardware degrades instead of failing — no Arduino falls back to the
screen dot, no display falls back to console pulses.

### Testing it for real

There is no website to try this on, and there can't be — the product moves the
real cursor, mutes Zoom while Zoom is minimised, and covers the actual screen.
A browser tab is sandboxed out of all three (that's the whole reason the control
loop is Python and not the browser — see `PLAN.md` §1). You test it by running it:

Runs on **Windows and macOS** (and Linux, for the non-GUI parts).

```bash
git clone https://github.com/Nicohlutta/handsfree-hci && cd handsfree-hci
uv venv --python 3.11 .venv
```

```bash
# Windows
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python -m handsfree.selftest

# macOS / Linux
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m handsfree.selftest
```

`python -m handsfree.selftest` walks every action in order: it says what should
happen, fires it, and asks whether it did.

#### macOS: grant permissions first, or everything fails silently

macOS gates synthetic input behind two separate switches, and **neither library
raises when the grant is missing** — pynput simply never sees a key and
pyautogui never moves the mouse. That failure looks exactly like a bug in this
code, so do this before anything else. In **System Settings → Privacy &
Security**, add your terminal (Terminal, iTerm, or your editor) to:

- **Accessibility** — lets pyautogui move the cursor and send keys
- **Input Monitoring** — lets pynput see `Ctrl+Alt+Q`

You must fully quit and reopen the terminal afterwards; the grant is read at
launch. Zoom's own mute shortcut on macOS is **Cmd+Shift+A**, not Alt+A — the
code sends the right one per platform, but check it's enabled as a *global*
shortcut in Zoom either way.

The self-test prints what should happen, fires the action, and asks whether it
did — then summarises against the bench criteria. `--auto` fires everything
without asking; `--only mute privacy` runs just those.

**Learn `Ctrl+Alt+Q` before the first run.** It kills the process from anywhere,
and it is how you get out of a black screen or a runaway cursor. To prove it
works, start `python -m handsfree.runaway` — which hijacks your mouse on
purpose — and take the machine back.

### Bench tests

`bench-plan.html` says a feature without a passing bench test is not built.
Track B's numbers are encoded as tests and run headless — no camera, board,
display or Zoom:

```bash
python -m pytest tests/ -v      # -s also prints what still needs a human
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
