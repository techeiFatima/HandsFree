"""LED on the beat — pre-analysed, never live.

Beat times come out of the song file ahead of time with librosa and are cached
next to it as JSON. The scheduler then fires pulses on the wall clock, anchored
to the moment playback started. No live audio capture anywhere: WASAPI loopback
on Windows is fiddly, eats an hour, and can fail on stage. Offline beat times
are deterministic, which is the whole point.

Three sinks, layered so the demo survives missing hardware:

  screen dot   always — a small always-on-top window whose dot flashes on each
               beat. Built FIRST: if no Arduino turns up, this IS the demo.
  Arduino LED  optional — LED_ON / LED_OFF over serial, which the firmware in
               firmware/arduino_stream/ already understands.
  console      headless fallback, so the timing is still verifiable with no
               display and no board.

Nothing here blocks the caller: led_beat_start returns immediately and the
scheduler runs on its own thread, so Nicholas's gesture loop keeps recognising
words while the music plays.

    python -m handsfree.actions --fire led_beat_start
    python -m handsfree.actions --fire led_beat_stop
    python -m handsfree.beats media/beat_track.wav        # finds the board itself
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from handsfree import ui

SONG = Path(__file__).resolve().parents[1] / "media" / "beat_track.wav"
PULSE_S = 0.10          # LED / dot on-time per beat
ON_COLOR = "#FF3B1F"
OFF_COLOR = "#181818"


def extract_beats(song: Path = SONG, force: bool = False) -> list[float]:
    """Beat timestamps (seconds) for the song, cached as <song>.beats.json.

    Cached because librosa's first import plus the analysis costs a few seconds,
    and at 19:59 that is a few seconds you do not have.
    """
    song = Path(song)
    cache = song.with_suffix(song.suffix + ".beats.json")
    if cache.exists() and not force:
        return json.loads(cache.read_text())["beats"]

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
    """Fire a callback at each pre-extracted beat time, anchored to t0.

    Sleeps toward each ABSOLUTE timestamp (t0 + beat) instead of sleeping by
    intervals. Interval sleeping accumulates every scheduling error it ever
    makes, which is exactly the drift the film-it-back test is looking for;
    absolute anchoring cannot drift by more than one wakeup's slop.
    """

    def __init__(self, beats: list[float], on_pulse, pulse_s: float = PULSE_S):
        self.beats = beats
        self.on_pulse = on_pulse
        self.pulse_s = pulse_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, t0: float | None = None) -> None:
        t0 = time.monotonic() if t0 is None else t0
        self._thread = threading.Thread(target=self._run, args=(t0,),
                                        daemon=True, name="beat-scheduler")
        self._thread.start()

    def _run(self, t0: float) -> None:
        for b in self.beats:
            delay = (t0 + b) - time.monotonic()
            if delay > 0 and self._stop.wait(delay):
                return
            if delay > -self.pulse_s:      # don't machine-gun beats already past
                try:
                    self.on_pulse()
                except Exception as exc:
                    print(f"[beats] pulse sink failed: {exc!r}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


# ── sinks ────────────────────────────────────────────────────────────────────

def find_board() -> str | None:
    """First serial port that looks like a real board, or None.

    Saves knowing what the port is called on the machine you happen to be on:
    COM4 on Windows, /dev/cu.usbmodem1401 on macOS, /dev/ttyACM0 on Linux.
    Only considers ports reporting a USB vendor ID, so it cannot latch onto a
    Bluetooth or debug console and start writing LED_ON at it.
    """
    try:
        from serial.tools import list_ports
    except Exception:
        return None
    for p in list_ports.comports():
        if getattr(p, "vid", None) is not None:
            return p.device
    return None


def _serial_sink(port: str, baud: int = 115200):
    """LED_ON now, LED_OFF a pulse later. The firmware already speaks both."""
    import serial
    ser = serial.Serial(port, baud, timeout=0.1)

    def pulse() -> None:
        ser.write(b"LED_ON\n")
        t = threading.Timer(PULSE_S, lambda: ser.write(b"LED_OFF\n"))
        t.daemon = True
        t.start()
    pulse.close = ser.close
    return pulse


class _DotWindow:
    """Small always-on-top window with a dot that flashes on the beat."""

    def __init__(self) -> None:
        self._canvas = None
        self._dot = None
        self._win = None

    def open(self) -> bool:
        def build(root) -> None:
            import tkinter as tk
            win = tk.Toplevel(root)
            win.title("beat")
            win.attributes("-topmost", True)
            win.geometry("200x200+40+40")
            win.configure(background="black")
            canvas = tk.Canvas(win, width=200, height=200, bg="black",
                               highlightthickness=0)
            canvas.pack()
            self._dot = canvas.create_oval(25, 25, 175, 175, fill=OFF_COLOR, outline="")
            self._canvas = canvas
            self._win = win
        return ui.submit(build)

    def pulse(self) -> None:
        def flash(root) -> None:
            if self._canvas is None:
                return
            self._canvas.itemconfig(self._dot, fill=ON_COLOR)
            root.after(int(PULSE_S * 1000),
                       lambda: self._canvas and self._canvas.itemconfig(self._dot,
                                                                       fill=OFF_COLOR))
        ui.submit(flash)

    def close(self) -> None:
        def kill(root) -> None:
            if self._win is not None:
                self._win.destroy()
            self._win = self._canvas = self._dot = None
        ui.submit(kill)


# ── the words ────────────────────────────────────────────────────────────────

_scheduler: BeatScheduler | None = None
_dot: _DotWindow | None = None
_serial_close = None
_lock = threading.Lock()


def led_beat_start(song: Path | str = SONG, port: str | None = None) -> None:
    """Start the song and pulse the dot (and the LED, if a board is present).

    Returns immediately. Fire led_beat_stop to end it.
    """
    global _scheduler, _dot, _serial_close

    with _lock:
        if _scheduler is not None and _scheduler.running:
            print("[beats] already running", file=sys.stderr)
            return

        beats = extract_beats(Path(song))
        sinks = []

        port = port or os.environ.get("HANDSFREE_LED_PORT") or find_board()
        if port:
            try:
                sink = _serial_sink(port)
                _serial_close = sink.close
                sinks.append(sink)
                print(f"[beats] Arduino on {port}", file=sys.stderr)
            except Exception as exc:
                # Board missing is the EXPECTED case, not an error. Degrade.
                print(f"[beats] no board on {port} ({exc!r}) — screen dot only",
                      file=sys.stderr)
        else:
            print("[beats] no board found — screen dot only", file=sys.stderr)

        _dot = _DotWindow()
        if _dot.open():
            sinks.append(_dot.pulse)
        else:
            _dot = None

        n = [0]
        def console(total=len(beats)) -> None:
            n[0] += 1
            print(f"\r[beats] {n[0]}/{total}", end="", file=sys.stderr, flush=True)
        sinks.append(console)

        from handsfree.actions.playlist import playlist_open
        playlist_open(song)
        _scheduler = BeatScheduler(beats, lambda: [s() for s in sinks])
        _scheduler.start()      # anchored to now, i.e. playback start


def led_beat_stop() -> None:
    """Stop the pulses and take the dot down. Music keeps playing (media_playpause stops that)."""
    global _scheduler, _dot, _serial_close

    with _lock:
        if _scheduler is not None:
            _scheduler.stop()
            _scheduler = None
        if _dot is not None:
            _dot.close()
            _dot = None
        if _serial_close is not None:
            try:
                _serial_close()
            except Exception:
                pass
            _serial_close = None
        print("\n[beats] stopped", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Pulse an LED and a screen dot on the beat.")
    ap.add_argument("song", nargs="?", default=str(SONG))
    ap.add_argument("--port", help="serial port; omit to auto-detect the board")
    ap.add_argument("--reextract", action="store_true", help="ignore the cached beat times")
    ap.add_argument("--seconds", type=float, default=None, help="stop after N seconds")
    args = ap.parse_args(argv)

    if args.reextract:
        extract_beats(Path(args.song), force=True)
    led_beat_start(args.song, args.port)

    try:
        if args.seconds:
            time.sleep(args.seconds)
        elif _scheduler:
            _scheduler.join()
    except KeyboardInterrupt:
        pass
    finally:
        led_beat_stop()


if __name__ == "__main__":
    main()
