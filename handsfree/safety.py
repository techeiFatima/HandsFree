"""N1 — the kill switch.

Nothing else in this project may touch the mouse until this works.

Once the app is driving the cursor and a gesture misfires, you cannot click
"stop" — you have handed away the only input device you had. This module is the
way back.

    from handsfree.safety import arm
    arm()          # Ctrl+Alt+Q now kills the process from anywhere

Three independent layers, because one is not enough:

  1. Global hotkey   Ctrl+Alt+Q  — works even when this app has no focus.
  2. Corner failsafe slam the cursor into a screen corner — pyautogui aborts.
  3. Dead-man switch control is only live while a pose is held (see Armed).
"""
from __future__ import annotations

import os
import sys
import threading

HOTKEY = "<ctrl>+<alt>+q"

_listener = None
_armed_once = False


def _panic(reason: str = "hotkey") -> None:
    """Terminate immediately, leaving the machine usable."""
    print(f"\n[KILL] {reason} — exiting now", file=sys.stderr, flush=True)
    try:
        import pyautogui
        # If a drag was in progress the button is still down; releasing it first
        # stops the desktop being left in a selection drag after we die.
        pyautogui.mouseUp()
    except Exception:
        pass
    # os._exit, not sys.exit: sys.exit only raises SystemExit in the calling
    # thread. From the hotkey listener thread that would be swallowed and the
    # process would keep driving the mouse — the exact failure this exists to
    # prevent.
    os._exit(1)


# Virtual key codes, matched directly.
#
# pynput's GlobalHotKeys cannot do this for us: while Ctrl is held Windows never
# emits the character "q", only the raw vk 81, and pynput's canonical() does not
# map it back. Both '<ctrl>+<alt>+q' and '<ctrl>+<alt>+<81>' silently never fire.
# Matching vks ourselves is shorter than debugging that, and it is deterministic.
VK_CTRL = {17, 162, 163}
VK_ALT = {18, 164, 165}
VK_Q = 81


def _vk_of(key) -> int | None:
    vk = getattr(key, "vk", None)
    if vk is not None:
        return vk
    val = getattr(key, "value", None)
    return getattr(val, "vk", None)


def arm(on_kill=None) -> None:
    """Install the global kill hotkey. Call once, early, before anything moves the mouse."""
    global _listener, _armed_once

    if _armed_once:
        return

    try:
        import pyautogui
        pyautogui.FAILSAFE = True   # corner slam aborts
        pyautogui.PAUSE = 0.0       # we do our own pacing
    except Exception as exc:
        print(f"[safety] pyautogui unavailable: {exc}", file=sys.stderr)

    from pynput import keyboard

    down: set[int] = set()

    def on_press(key):
        vk = _vk_of(key)
        if vk is None:
            return
        down.add(vk)
        if vk == VK_Q and (down & VK_CTRL) and (down & VK_ALT):
            if on_kill:
                try:
                    on_kill()
                except Exception:
                    pass
            _panic("hotkey Ctrl+Alt+Q")

    def on_release(key):
        vk = _vk_of(key)
        if vk is not None:
            down.discard(vk)

    _listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    _listener.daemon = True
    _listener.start()
    _armed_once = True
    print("[safety] armed — press CTRL+ALT+Q to kill, "
          "or slam the cursor into a screen corner", file=sys.stderr)


class Armed:
    """Dead-man's switch. Cursor control is live only while a pose is held.

    Drop your hand and control stops — which also means waving your hands while
    you talk during the pitch does not move the cursor.
    """

    def __init__(self, release_after_s: float = 0.4):
        self.release_after_s = release_after_s
        self._last_true = 0.0
        self._live = False
        self._lock = threading.Lock()

    def update(self, pose_held: bool, now: float) -> bool:
        with self._lock:
            if pose_held:
                self._last_true = now
                self._live = True
            elif now - self._last_true > self.release_after_s:
                self._live = False
            return self._live

    @property
    def live(self) -> bool:
        return self._live
