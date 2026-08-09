"""LED on the beat — pre-analysed, never live.

Beat times are extracted from the song file ahead of time with librosa and
cached next to it as JSON. The scheduler then fires pulses on the wall clock,
anchored to the moment playback started. No live audio capture anywhere —
that path eats an hour on Windows and can fail on stage.

Three sinks, layered so the demo survives missing hardware:

  screen dot   always — a Tk window with a dot that flashes on each beat.
               Built FIRST: if no Arduino turns up, this IS the demo.
  Arduino LED  optional — LED_ON / LED_OFF over serial (the firmware in
               firmware/arduino_stream/ already understands both).
  console      headless fallback so --fire led_beat_start proves the timing
               even with no display.

Usage:
    python -m handsfree --fire led_beat_start          # song + dot (+ LED if HANDSFREE_LED_PORT set)
    python -m handsfree.beats media/beat_track.wav --port COM4
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

SONG = Path(__file__).resolve().parents[1] / "media" / "beat_track.wav"
PULSE_S = 0.10  # LED/dot on-time per beat


def extract_beats(song: Path = SONG, force: bool = False) -> list[float]:
    """Beat timestamps (seconds) for the song, cached as <song>.beats.json."""
    cache = song.with_suffix(song.suffix + ".beats.json")
    if cache.exists() and not force:
        data = json.loads(cache.read_text())
        return data["beats"]

    import librosa
    y, sr = librosa.load(song, sr=None, mono=True)
    tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
    beats = [float(t) for t in librosa.frames_to_time(frames, sr=sr)]
    tempo_f = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
    cache.write_text(json.dumps({"tempo_bpm": tempo_f, "beats": beats}))
    print(f"[beats] {song.name}: {tempo_f:.1f} BPM, {len(beats)} beats "
          f"(cached to {cache.name})", file=sys.stderr)
    return beats


class BeatScheduler:
    """Fire callbacks at each pre-extracted beat time, anchored to t0.

    Sleeps toward each absolute timestamp (t0 + beat) rather than by
    intervals, so error never accumulates — the film-it-back test cares
    about drift at 20 s, and absolute scheduling makes drift impossible
    beyond one sleep quantum.
    """

    def __init__(self, beats: list[float], on_pulse, pulse_s: float = PULSE_S):
        self.beats = beats
        self.on_pulse = on_pulse
        self.pulse_s = pulse_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, t0: float | None = None) -> None:
        t0 = time.monotonic() if t0 is None else t0
        self._thread = threading.Thread(target=self._run, args=(t0,), daemon=True)
        self._thread.start()

    def _run(self, t0: float) -> None:
        for b in self.beats:
            delay = (t0 + b) - time.monotonic()
            if delay > 0 and self._stop.wait(delay):
                return
            if delay > -self.pulse_s:  # skip beats we're already past
                self.on_pulse()

    def stop(self) -> None:
        self._stop.set()

    def join(self) -> None:
        if self._thread:
            self._thread.join()


# ── sinks ────────────────────────────────────────────────────────────────────

def _serial_sink(port: str):
    import serial
    ser = serial.Serial(port, 115200, timeout=0.1)

    def pulse() -> None:
        ser.write(b"LED_ON\n")
        threading.Timer(PULSE_S, lambda: ser.write(b"LED_OFF\n")).start()
    return pulse


def _dot_window():
    """On-screen pulsing dot. Returns (pulse_fn, run_mainloop_fn) or None headless."""
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as exc:
        print(f"[beats] no display for the dot ({exc!r}) — console pulses only",
              file=sys.stderr)
        return None

    root.title("beat")
    root.attributes("-topmost", True)
    root.geometry("220x220+40+40")
    canvas = tk.Canvas(root, width=220, height=220, bg="black", highlightthickness=0)
    canvas.pack()
    dot = canvas.create_oval(30, 30, 190, 190, fill="#181818", outline="")

    def pulse() -> None:
        canvas.itemconfig(dot, fill="#FF3B1F")
        root.after(int(PULSE_S * 1000), lambda: canvas.itemconfig(dot, fill="#181818"))

    def on_pulse() -> None:  # scheduler thread → Tk thread
        root.after(0, pulse)

    return on_pulse, root.mainloop


def led_beat_start() -> None:
    """The led_beat_start word: start the song, dot, and (if present) the LED."""
    import os
    beats = extract_beats()

    sinks = []
    port = os.environ.get("HANDSFREE_LED_PORT")
    if port:
        try:
            sinks.append(_serial_sink(port))
        except Exception as exc:
            print(f"[beats] Arduino on {port} unavailable: {exc!r} — dot only",
                  file=sys.stderr)

    dot = _dot_window()
    mainloop = None
    if dot:
        pulse_dot, mainloop = dot
        sinks.append(pulse_dot)

    n = [0]
    def console_pulse() -> None:
        n[0] += 1
        print(f"\r[beats] ♪ {n[0]}/{len(beats)}", end="", file=sys.stderr, flush=True)
    sinks.append(console_pulse)

    from handsfree.actions.playlist import playlist_open
    scheduler = BeatScheduler(beats, lambda: [s() for s in sinks])
    playlist_open()
    scheduler.start()   # anchored to now = playback start

    if mainloop:
        mainloop()      # blocks until the dot window is closed
        scheduler.stop()
    else:
        scheduler.join()
        print(file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("song", nargs="?", default=str(SONG))
    ap.add_argument("--port", help="Arduino serial port (e.g. COM4)")
    ap.add_argument("--reextract", action="store_true")
    args = ap.parse_args(argv)

    import os
    if args.port:
        os.environ["HANDSFREE_LED_PORT"] = args.port
    if args.reextract:
        extract_beats(Path(args.song), force=True)
    led_beat_start()


if __name__ == "__main__":
    main()
