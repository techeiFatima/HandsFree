#!/usr/bin/env python
"""Sundai physical-AI spine.

    python run.py --list                              # what hardware can I see?
    python run.py                                     # sim sensors + UI, zero hardware
    python run.py --source audio --model clap \
        --labels "a kettle boiling,glass breaking,a vacuum cleaner,silence" \
        --when "glass breaking" --action "ALERT"
    python run.py --source serial --port COM3 --model chronos --channel soil --low 480
    python run.py --source replay --file logs/run-XXXX.jsonl --model clap   # demo insurance
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from sundai import models, sources
from sundai.pipeline import Pipeline, Recorder, Rule, print_sink, serial_sink


def main():
    ap = argparse.ArgumentParser(description="Sundai physical-AI spine",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--list", action="store_true", help="list serial ports + audio devices, exit")

    g = ap.add_argument_group("source")
    g.add_argument("--source", default="sim", choices=list(sources.SOURCES))
    g.add_argument("--port", help="serial port, e.g. COM3")
    g.add_argument("--baud", type=int, default=115200)
    g.add_argument("--hz", type=float, default=10.0, help="sim sample rate")
    g.add_argument("--file", help="replay .jsonl path")
    g.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier")
    g.add_argument("--audio-device", type=int, default=None)
    g.add_argument("--window-s", type=float, default=3.0, help="audio window seconds")
    g.add_argument("--hop-s", type=float, default=0.5, help="audio hop seconds")

    g = ap.add_argument_group("model")
    g.add_argument("--model", default="passthrough", choices=models.MODELS)
    g.add_argument("--labels", default="", help="comma-separated zero-shot classes (clap)")
    g.add_argument("--channel", default="soil", help="channel for threshold/chronos")
    g.add_argument("--low", type=float, default=-1e9)
    g.add_argument("--high", type=float, default=1e9)
    g.add_argument("--horizon", type=int, default=24, help="chronos forecast steps")

    g = ap.add_argument_group("action")
    g.add_argument("--when", help="fire when the predicted label equals this")
    g.add_argument("--action", help="command string sent to the board / printed")
    g.add_argument("--cooldown", type=float, default=5.0)
    g.add_argument("--min-score", type=float, default=0.5)
    g.add_argument("--out-port", help="serial port for actuator output (default: --port)")

    g = ap.add_argument_group("output")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--web-port", type=int, default=8000)
    g.add_argument("--no-serve", action="store_true")
    g.add_argument("--no-record", action="store_true")
    g.add_argument("--no-open", action="store_true", help="don't open the browser")
    g.add_argument("--max-records", type=int, help="stop after N records (capture / testing)")
    g.add_argument("--title", default="Sundai — FM for the Physical World")

    args = ap.parse_args()

    if args.list:
        print("Serial ports:")
        ports = sources.list_serial_ports()
        print("\n".join(f"  {d}  —  {desc}" for d, desc in ports) or "  (none found)")
        print("\nAudio input devices:")
        devs = sources.list_audio_devices()
        print("\n".join(f"  {d}" for d in devs) or "  (none found)")
        return

    if args.source == "serial" and not args.port:
        ports = sources.list_serial_ports()
        raise SystemExit("--port required for --source serial. Seen: " +
                         (", ".join(d for d, _ in ports) or "none — is the board plugged in?"))
    if args.source == "replay" and not args.file:
        raise SystemExit("--file required for --source replay")

    src = sources.SOURCES[args.source](
        port=args.port, baud=args.baud, hz=args.hz, file=args.file, speed=args.speed,
        device=args.audio_device, window_s=args.window_s, hop_s=args.hop_s,
    )
    model = models.build(args.model, args)
    rule = Rule(args.when, args.action, cooldown=args.cooldown, min_score=args.min_score)

    sink = print_sink
    out_port = args.out_port or (args.port if args.source == "serial" else None)
    if out_port and args.action:
        try:
            sink = serial_sink(out_port, args.baud) if out_port != args.port else None
        except Exception as exc:
            print(f"[sink] serial out unavailable ({exc}); printing instead", file=sys.stderr)
            sink = print_sink
        if sink is None:  # same port as input: reuse the input handle path
            sink = print_sink
            print("[sink] output shares the input port; using print sink. "
                  "Pass --out-port for a second board.", file=sys.stderr)

    pipe = Pipeline(src, model, rule, Recorder(enabled=not args.no_record), sink=sink,
                    max_records=args.max_records)

    if args.no_serve:
        print(f"[run] {args.source} -> {args.model} (headless)", file=sys.stderr)
        try:
            pipe.run()
        except KeyboardInterrupt:
            pipe.recorder.close()
        return

    import uvicorn

    from sundai.server import make_app

    app = make_app(pipe, title=args.title)
    pipe.on_record = lambda rec: app.state.broadcast(rec)

    threading.Thread(target=pipe.run, daemon=True).start()

    url = f"http://{args.host}:{args.web_port}"
    print(f"\n  {args.source} -> {args.model}   UI: {url}\n", file=sys.stderr)
    if not args.no_open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.web_port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()
        pipe.recorder.close()


if __name__ == "__main__":
    main()
