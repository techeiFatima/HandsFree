"""Data sources. Every source is an iterator of records.

A record is a plain dict: {"t": <epoch seconds, float>, ...payload}
Keys starting with "_" are transient (numpy arrays etc) and never logged/serialised.
"""
from __future__ import annotations

import json
import math
import queue
import random
import sys
import time
from pathlib import Path


def _now() -> float:
    return time.time()


# --------------------------------------------------------------------------
# sim: synthetic sensors. Works with zero hardware. Use this to build the demo
# before the board is wired, and as the emergency fallback at 8pm.
# --------------------------------------------------------------------------
def sim_source(hz: float = 10.0, **_):
    """Fake soil/temp/humidity/IMU that drifts and occasionally spikes."""
    period = 1.0 / hz
    i = 0
    soil = 620.0
    while True:
        i += 1
        phase = i * period
        # soil slowly dries out, with a watering event every ~30s
        soil -= 0.35
        if i % int(30 * hz) == 0:
            soil = 640.0
        drift = math.sin(phase / 7.0) * 8
        yield {
            "t": _now(),
            "soil": round(soil + drift + random.gauss(0, 1.5), 2),
            "temp_c": round(22.0 + math.sin(phase / 11.0) * 1.8 + random.gauss(0, 0.08), 2),
            "humidity": round(48.0 + math.cos(phase / 13.0) * 6 + random.gauss(0, 0.3), 2),
            "lux": round(max(0.0, 400 + math.sin(phase / 5.0) * 300 + random.gauss(0, 20)), 1),
            "accel_x": round(random.gauss(0, 0.02), 4),
            "accel_y": round(random.gauss(0, 0.02), 4),
            "accel_z": round(1.0 + random.gauss(0, 0.02), 4),
        }
        time.sleep(period)


# --------------------------------------------------------------------------
# serial: the board streams newline-delimited JSON over USB.
# --------------------------------------------------------------------------
def serial_source(port: str, baud: int = 115200, **_):
    import serial  # pyserial

    ser = serial.Serial(port, baud, timeout=1.0)
    time.sleep(2.0)  # Arduino auto-resets on open; wait for the bootloader
    ser.reset_input_buffer()
    print(f"[serial] listening on {port} @ {baud}", file=sys.stderr)
    while True:
        raw = ser.readline()
        if not raw:
            continue
        try:
            line = raw.decode("utf-8", "replace").strip()
        except Exception:
            continue
        if not line or line[0] != "{":
            if line:
                print(f"[serial:board] {line}", file=sys.stderr)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rec.setdefault("t", _now())
        yield rec


def list_serial_ports() -> list[tuple[str, str]]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [(p.device, p.description) for p in list_ports.comports()]


# --------------------------------------------------------------------------
# replay: feed a recorded .jsonl back through the identical pipeline.
# This is the demo insurance policy.
# --------------------------------------------------------------------------
def replay_source(file: str, speed: float = 1.0, loop: bool = True, **_):
    path = Path(file)
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not records:
        raise SystemExit(f"[replay] no records in {path}")
    print(f"[replay] {len(records)} records from {path} at {speed}x", file=sys.stderr)

    while True:
        t0 = records[0].get("t", 0.0)
        wall0 = _now()
        for rec in records:
            target = (rec.get("t", t0) - t0) / max(speed, 1e-6)
            lag = target - (_now() - wall0)
            if lag > 0:
                time.sleep(min(lag, 1.0))
            out = dict(rec)
            out["t"] = _now()
            out["_replay"] = True
            yield out
        if not loop:
            return


# --------------------------------------------------------------------------
# audio: microphone capture for CLAP. Yields overlapping windows at 48 kHz
# (CLAP's native rate) plus an RMS level so the UI has something to draw.
# --------------------------------------------------------------------------
def audio_source(window_s: float = 3.0, hop_s: float = 0.5, device=None, samplerate: int = 48000, **_):
    import numpy as np
    import sounddevice as sd

    blocksize = int(samplerate * hop_s)
    win_samples = int(samplerate * window_s)
    q: queue.Queue = queue.Queue(maxsize=32)

    def cb(indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        try:
            q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    ring = np.zeros(win_samples, dtype=np.float32)
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32",
                        blocksize=blocksize, device=device, callback=cb):
        print(f"[audio] capturing {window_s}s windows every {hop_s}s @ {samplerate} Hz",
              file=sys.stderr)
        while True:
            block = q.get()
            n = len(block)
            ring = np.roll(ring, -n)
            ring[-n:] = block
            rms = float(np.sqrt(np.mean(ring[-blocksize * 2:] ** 2)))
            yield {
                "t": _now(),
                "rms": round(rms, 5),
                "db": round(20 * math.log10(max(rms, 1e-6)), 1),
                "_audio": ring.copy(),
                "_samplerate": samplerate,
            }


def list_audio_devices() -> list[str]:
    try:
        import sounddevice as sd
    except ImportError:
        return []
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(f"{i}: {d['name']} ({d['max_input_channels']}ch)")
    return out


SOURCES = {
    "sim": sim_source,
    "serial": serial_source,
    "replay": replay_source,
    "audio": audio_source,
}
