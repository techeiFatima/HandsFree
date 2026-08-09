"""privacy_blank / privacy_restore — a fullscreen, always-on-top black window.

Second-monitor decision (made now, not on stage): the blank covers the MAIN
monitor only. Tk's -fullscreen maps to the screen the window appears on, and
the demo laptop drives the projector mirrored — covering the primary covers
what the room sees. If an extended second display is ever the demo setup,
mirror the displays instead (Win+P → Duplicate); that's a settings toggle,
not code.

Safety, non-negotiable: Esc closes the blank. A black always-on-top window
with no keyboard escape locks the laptop in front of the whole room. The
Ctrl+Alt+Q kill switch also still works while blanked — safety.arm() listens
to raw keyboard events via pynput, which sees keys regardless of which window
has focus.

The window runs in its own thread with its own Tk mainloop, so the gesture
loop keeps running while the screen is black (otherwise you could never fire
privacy_restore).
"""
from __future__ import annotations

import queue
import sys
import threading

_cmd: "queue.Queue[str]" = queue.Queue()
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ui_thread() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    win: list[tk.Toplevel | None] = [None]

    def show() -> None:
        if win[0] is not None:
            return
        w = tk.Toplevel(root)
        w.configure(background="black")
        w.attributes("-fullscreen", True)
        w.attributes("-topmost", True)
        # Esc restores — mandatory escape hatch.
        w.bind("<Escape>", lambda e: hide())
        w.focus_force()
        win[0] = w

    def hide() -> None:
        w, win[0] = win[0], None
        if w is not None:
            w.destroy()

    def poll() -> None:
        try:
            while True:
                cmd = _cmd.get_nowait()
                show() if cmd == "blank" else hide()
        except queue.Empty:
            pass
        root.after(50, poll)

    poll()
    root.mainloop()


def _ensure_thread() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_ui_thread, daemon=True, name="privacy-ui")
            _thread.start()


def privacy_blank() -> None:
    """Cover the main screen with black. Esc or privacy_restore brings it back."""
    _ensure_thread()
    _cmd.put("blank")


def privacy_restore() -> None:
    """Take the black cover down."""
    if _thread is None or not _thread.is_alive():
        print("[privacy] nothing to restore — screen was never blanked", file=sys.stderr)
        return
    _cmd.put("restore")
