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


# Matching the hotkey ourselves, because pynput's GlobalHotKeys cannot do it:
# while Ctrl is held Windows never emits the character "q", only the raw vk 81,
# and pynput's canonical() does not map it back, so both '<ctrl>+<alt>+q' and
# '<ctrl>+<alt>+<81>' silently never fire.
#
# Two halves, matched differently on purpose:
#
#   modifiers  compared against pynput's Key members. Those are the same objects
#              on every platform, so nothing here needs a per-OS number.
#   the letter matched by raw key code, since the character is unavailable while
#              Ctrl is down (see above) -- and key codes are NOT portable. Q is
#              81 on Windows, 12 on macOS, 113 under X11. A hardcoded 81 is a
#              kill switch that silently does not exist on a Mac, which is worse
#              than having none at all: you would trust it and it would not be
#              there. Hence a table, and a char check as a belt-and-braces
#              second route for anything not listed.
_Q_VK_BY_PLATFORM = {
    "win32": {81},      # VK_Q
    "darwin": {12},     # kVK_ANSI_Q
    "linux": {113},     # X11 keysym 'q' (0x71)
}


def q_vks(platform: str | None = None) -> set[int]:
    """Raw key codes that mean 'q' on this platform."""
    platform = platform or sys.platform
    for prefix, vks in _Q_VK_BY_PLATFORM.items():
        if platform.startswith(prefix):
            return vks
    # Unknown platform: accept every code we know rather than none. A false
    # positive costs you a keystroke; a false negative costs you the machine.
    return set().union(*_Q_VK_BY_PLATFORM.values())


def _vk_of(key) -> int | None:
    vk = getattr(key, "vk", None)
    if vk is not None:
        return vk
    val = getattr(key, "value", None)
    return getattr(val, "vk", None)


def _modifier_keys(keyboard):
    """(ctrl-ish, alt-ish) Key members that exist on this platform."""
    def members(*names):
        return {getattr(keyboard.Key, n) for n in names if hasattr(keyboard.Key, n)}
    return (members("ctrl", "ctrl_l", "ctrl_r"),
            members("alt", "alt_l", "alt_r", "alt_gr"))


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

    CTRL, ALT = _modifier_keys(keyboard)
    Q_VKS = q_vks()
    held: set = set()

    def _is_q(key) -> bool:
        return _vk_of(key) in Q_VKS or getattr(key, "char", None) == "q"

    def on_press(key):
        if key in CTRL or key in ALT:
            held.add(key)
            return
        if _is_q(key) and (held & CTRL) and (held & ALT):
            if on_kill:
                try:
                    on_kill()
                except Exception:
                    pass
            _panic("hotkey Ctrl+Alt+Q")

    def on_release(key):
        held.discard(key)

    _listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    _listener.daemon = True
    _listener.start()
    _armed_once = True
    if sys.platform == "darwin":
        # On macOS both halves of this are gated behind Privacy & Security, and
        # neither library complains when the grant is missing — pynput just
        # never sees a key and pyautogui never moves the mouse. Say it out loud,
        # because "armed" above would otherwise be a lie you find out about
        # while the cursor is running away from you.
        print("[safety] macOS: this only works once your terminal is ticked "
              "under System Settings → Privacy & Security → Accessibility AND "
              "→ Input Monitoring. Without both, the kill switch is silent.",
              file=sys.stderr)
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
