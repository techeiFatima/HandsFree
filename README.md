# HandsFree

Turning a gesture into something that actually happens on your laptop — mute a
call, blank the screen, pulse an LED on the beat — without touching the
keyboard.

Built at [Sundai](https://sundai.club) with [Nicholas Lutta](https://github.com/Nicohlutta).
The system splits in half at a single string: his half turns the webcam into a
**word**, this half turns that word into an **action**. Because the two sides
only meet at that string, either half can be built, tested and benchmarked
without the other existing.

```
webcam ──▶ hand landmarks ──▶ gesture ──▶ "mute_toggle" ──▶ action registry ──▶ OS
           └────────── Nicholas's half ─────────┘   └──────── this repo ────────┘
```

## Status

**This repo is the actuation half.** Fire `mute_toggle` and the microphone
really mutes; fire `privacy_blank` and every monitor really goes black. The
camera half lives in Nicholas's repo and is not here — so you cannot currently
wave at the laptop and watch it mute. That is the point of splitting at the
string: this side was finished and benchmarked while the other was still being
built, and joining them requires no change here.

```bash
python -m pytest tests/ -v      # 43 passed
```

Every bench test runs headless — no camera, no Arduino, no display, no Zoom.
The checks that genuinely need a human or hardware (does the phone show muted?
is the LED on the beat when you film it?) are listed in the test file and
printed by `pytest -s`, so they can't be quietly skipped.

## The eight words

Fixed at design time and never renamed, because renaming one silently breaks
the other half of the system.

| Word | Does |
|---|---|
| `mute_toggle` | system mute + Zoom's own chord (Alt+A; Cmd+Shift+A on macOS) |
| `media_playpause` | media play/pause key |
| `privacy_blank` / `privacy_restore` | black fullscreen cover on every monitor; **Esc dismisses** |
| `playlist_open` | plays `media/beat_track.wav` |
| `led_beat_start` / `led_beat_stop` | pulses a screen dot and an Arduino LED on the beat |
| `break_prompt` | "you haven't moved" reminder |

Drive them from the terminal — this *is* the camera until the real one is
wired in:

```bash
python -m handsfree.actions --list
python -m handsfree.actions --fire test_ping
python -m handsfree.actions --fire mute_toggle --repeat 5 --interval 1
python -m handsfree.actions --fire privacy_blank --hold 10
python -m handsfree.beats --seconds 20
```

## Two rules everything else depends on

**`Ctrl+Alt+Q` kills the process from anywhere.** Once software is driving your
mouse and covering your screen, this is how you take the machine back. To prove
it works before you need it, run `python -m handsfree.runaway` — which hijacks
the cursor on purpose — and stop it.

**No action ever blocks its caller.** Every window lives on one shared Tk
thread (`handsfree/ui.py`), so firing a word never stalls the gesture loop.

Two smaller decisions follow from demo reality: beat times are extracted offline
with librosa and cached, because live audio capture is fragile on Windows and
can fail on stage; and missing hardware degrades instead of failing — no Arduino
falls back to the screen dot, no display falls back to console pulses.

## Install

```bash
git clone https://github.com/techeiFatima/HandsFree && cd HandsFree
uv venv --python 3.11 .venv
```

`requirements.txt` also pins torch and transformers for the sensor spine below,
which is a slow download you do not need for the hands-free half. These six are
the whole of it:

```bash
uv pip install --python .venv/bin/python \
  pyautogui pynput librosa soundfile pyserial screeninfo
```

On Windows use `--python .venv/Scripts/python.exe`. Then walk every action —
it says what should happen, fires it, and asks whether it did:

```bash
.venv/bin/python -m handsfree.selftest
```

Runs on Windows and macOS, and on Linux for the non-GUI parts.

### macOS: grant permissions first, or everything fails silently

macOS gates synthetic input behind two switches, and **neither library raises
when the grant is missing** — pynput simply never sees a key, pyautogui never
moves the mouse. That looks exactly like a bug in this code. In **System
Settings → Privacy & Security**, add your terminal to:

- **Accessibility** — lets pyautogui move the cursor and send keys
- **Input Monitoring** — lets pynput see `Ctrl+Alt+Q`

Fully quit and reopen the terminal afterwards; the grant is read at launch.

## The sensor spine

The repo also carries a second, separate experiment from the same event: a
generic pipeline that reads sensors, runs a foundation model over a rolling
window, and fires a rule.

```
board (dumb)                     laptop (smart)
  sensors ──NDJSON over serial──▶ rolling window ──▶ foundation model
                                                          │
  relay/buzzer/LED ◀───command──────────── rule ◀─────────┘
                                             └──▶ .jsonl log + live web UI
```

The model never runs on the microcontroller — the board only reads sensors and
prints JSON. No hardware is needed to see it work:

```bash
python run.py                # synthetic sensors + UI, proves the whole chain
python run.py --list         # what hardware can I see?
```

Zero-shot audio events, where you write the classes in plain English:

```bash
python run.py --source audio --model clap \
  --labels "a kettle boiling,glass breaking,a vacuum cleaner,silence" \
  --when "glass breaking" --action ALERT
```

Measured on the development machine — an Intel Arc 130V iGPU with no CUDA and
15.7 GB RAM, so everything below is **CPU-only**:

| Piece | Numbers |
|---|---|
| CLAP zero-shot audio | 2.4 s cached load, 0.36 s per 3 s window |
| Chronos-Bolt-small forecasting | 0.22 s per forecast, 12-step horizon |
| record → replay through the same pipeline | 120 records at 50× |

Those constraints are why this lane exists at all: OpenVLA needs ~16 GB of VRAM
and a robot arm, neither of which was available, so audio and time-series were
the viable options.

Adding a model means subclassing `Model` in `sundai/models.py` and implementing
`predict(record, window) -> dict` returning at least `{"label", "score"}`. If it
fails to load, the pipeline falls back to passthrough rather than dying.

## Layout

```
handsfree/actions/       word → action registry, and the --fire CLI
handsfree/safety.py      Ctrl+Alt+Q kill switch + dead-man switch
handsfree/ui.py          the one Tk thread every window runs on
handsfree/beats.py       cached beat times → screen dot + Arduino LED
handsfree/breakwatch.py  stillness tracker + break prompt
handsfree/selftest.py    walks every action, asks whether it worked
tests/test_bench.py      43 headless bench tests
sundai/sources.py        sim | serial | replay | audio
sundai/models.py         passthrough | threshold | clap | chronos
sundai/pipeline.py       window, rule, recorder, sinks
sundai/server.py         live dashboard (http://127.0.0.1:8000)
firmware/                Arduino + CircuitPython sensor streamers
run.py                   CLI entrypoint for the sensor spine
```

See [PLAN.md](PLAN.md) for why the control loop is Python rather than a browser,
and [COLLABORATING.md](COLLABORATING.md) for how the two repos stay in sync.
