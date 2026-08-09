"""One Tk thread for the whole app.

Every on-screen thing Fatima owns — the privacy blank, the beat dot, the break
prompt — needs a window, and all of them get fired from someone else's thread
(Nicholas's gesture loop, or the beat scheduler). Two rules follow:

  1. Tk is not thread-safe and does not like two roots in one process. So there
     is exactly ONE root, owned by ONE thread, created here.
  2. An action must never block its caller. If led_beat_start ran a mainloop on
     the calling thread, the gesture loop would stop dead at the first thumbs-up
     and no further word would ever be recognised.

So: the root lives on a daemon thread, and other threads post callables to it.

    from handsfree import ui
    ui.submit(lambda: my_window.deiconify())     # fire-and-forget
    ok = ui.available()                          # False when headless

Headless (CI, a box with no display) is a supported mode, not an error — every
caller falls back to console output so the timing can still be verified.
"""
from __future__ import annotations

import queue
import sys
import threading

_q: "queue.Queue" = queue.Queue()
_thread: threading.Thread | None = None
_lock = threading.Lock()
_root = None
_ready = threading.Event()
_ok = False


def _pump() -> None:
    global _root, _ok
    try:
        import tkinter as tk
        _root = tk.Tk()
        _root.withdraw()          # the root itself is never shown
        _ok = True
    except Exception as exc:
        print(f"[ui] no display ({exc!r}) — windows disabled, console only",
              file=sys.stderr)
        _ok = False
        _ready.set()
        return

    _ready.set()

    def drain() -> None:
        try:
            while True:
                fn = _q.get_nowait()
                try:
                    fn(_root)
                except Exception as exc:
                    print(f"[ui] {getattr(fn, '__name__', fn)!r} failed: {exc!r}",
                          file=sys.stderr)
        except queue.Empty:
            pass
        _root.after(20, drain)

    drain()
    _root.mainloop()


def start() -> bool:
    """Boot the UI thread once. Returns False if this box has no display."""
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _ready.clear()
            _thread = threading.Thread(target=_pump, daemon=True, name="handsfree-ui")
            _thread.start()
    _ready.wait(timeout=5.0)
    return _ok


def available() -> bool:
    return _ok


def submit(fn) -> bool:
    """Run fn(root) on the UI thread. Never blocks. False if headless."""
    if not start():
        return False
    _q.put(fn)
    return True
