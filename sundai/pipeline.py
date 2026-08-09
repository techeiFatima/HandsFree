"""The spine: source -> rolling window -> model -> rule -> sinks.

Runs on a background thread so the web UI stays responsive. Everything that
comes out of here is a plain JSON-safe dict, broadcast to the UI and appended
to a .jsonl log that `--source replay` can play back later.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path


def json_safe(rec: dict) -> dict:
    """Drop transient underscore keys (numpy arrays) and coerce the rest."""
    out = {}
    for k, v in rec.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (str, int, float, bool, type(None), list, dict)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


class Recorder:
    """Append every record to logs/run-<timestamp>.jsonl. Demo insurance."""

    def __init__(self, enabled: bool = True, directory: str = "logs"):
        self.path = None
        self.fh = None
        if not enabled:
            return
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = d / f"run-{stamp}.jsonl"
        self.fh = self.path.open("w", encoding="utf-8")
        print(f"[record] -> {self.path}", file=sys.stderr)

    def write(self, rec: dict):
        if self.fh:
            self.fh.write(json.dumps(rec) + "\n")
            self.fh.flush()

    def close(self):
        if self.fh:
            self.fh.close()


class Rule:
    """Fires an action when the model's label matches, with a cooldown so a
    demo doesn't machine-gun the relay."""

    def __init__(self, when: str | None, action: str | None, cooldown: float = 5.0,
                 min_score: float = 0.5):
        self.when, self.action = when, action
        self.cooldown, self.min_score = cooldown, min_score
        self.last_fired = 0.0
        self.fire_count = 0

    def check(self, pred: dict) -> str | None:
        if not self.when or not self.action:
            return None
        if pred.get("label") != self.when:
            return None
        if pred.get("score", 0.0) < self.min_score:
            return None
        now = time.time()
        if now - self.last_fired < self.cooldown:
            return None
        self.last_fired = now
        self.fire_count += 1
        return self.action


class Pipeline:
    def __init__(self, source, model, rule: Rule, recorder: Recorder,
                 sink=None, window_size: int = 512, on_record=None,
                 max_records: int | None = None):
        self.source, self.model, self.rule = source, model, rule
        self.recorder, self.sink = recorder, sink
        self.window = deque(maxlen=window_size)
        self.on_record = on_record
        self.max_records = max_records
        self.latest: dict = {}
        self.count = 0
        self.errors = 0
        self.started = time.time()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            self.model.load()
        except Exception:
            print("[pipeline] MODEL FAILED TO LOAD — falling back to passthrough",
                  file=sys.stderr)
            traceback.print_exc()
            from .models import Passthrough
            self.model = Passthrough()

        for rec in self.source:
            if self._stop.is_set():
                break
            self.count += 1
            self.window.append({k: v for k, v in rec.items() if not k.startswith("_")})

            t0 = time.perf_counter()
            try:
                pred = self.model.predict(rec, self.window)
            except Exception as exc:
                self.errors += 1
                pred = {"label": "error", "score": 0.0, "detail": str(exc)[:200]}
                if self.errors <= 3:
                    traceback.print_exc()
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            out = json_safe(rec)
            out["pred"] = pred
            out["latency_ms"] = latency_ms
            out["n"] = self.count

            action = self.rule.check(pred)
            if action:
                out["action"] = action
                print(f"[rule] {pred.get('label')} -> {action}", file=sys.stderr)
                if self.sink:
                    try:
                        self.sink(action)
                    except Exception as exc:
                        print(f"[sink] failed: {exc}", file=sys.stderr)

            self.latest = out
            self.recorder.write(out)
            if self.on_record:
                self.on_record(out)

            if self.max_records and self.count >= self.max_records:
                print(f"[pipeline] reached --max-records {self.max_records}", file=sys.stderr)
                break

        self.recorder.close()

    def status(self) -> dict:
        return {
            "model": getattr(self.model, "name", "?"),
            "records": self.count,
            "errors": self.errors,
            "uptime_s": round(time.time() - self.started, 1),
            "fires": self.rule.fire_count,
            "log": str(self.recorder.path) if self.recorder.path else None,
        }


def serial_sink(port: str, baud: int = 115200):
    """Send a command line back to the board to drive a relay/buzzer/LED."""
    import serial

    ser = serial.Serial(port, baud, timeout=1.0)
    time.sleep(2.0)

    def send(action: str):
        ser.write((action.strip() + "\n").encode("utf-8"))
        ser.flush()

    return send


def print_sink(action: str):
    print(f"\n  *** ACTION: {action} ***\n", file=sys.stderr)
