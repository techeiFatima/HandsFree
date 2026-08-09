"""The action registry — Fatima's half of the seam.

Nicholas's code turns the camera into a word. This package turns that word
into something happening on the laptop. The two halves only touch here.

The seven words, fixed and never renamed:

    mute_toggle      media_playpause  privacy_blank    privacy_restore
    playlist_open    led_beat_start   break_prompt

Fire one from anywhere:

    from handsfree.actions import fire
    fire("mute_toggle")

or from the terminal (this is your camera until Nicholas's works):

    python -m handsfree --fire mute_toggle
"""
from __future__ import annotations

import sys
import time


def test_ping() -> None:
    """Prove the word→action seam is alive. First thing to ever run."""
    print(f"[actions] pong @ {time.strftime('%H:%M:%S')} — the seam works")


def _lazy(module: str, name: str):
    # Actions import their heavy deps (Tk, pyautogui, librosa) only when fired,
    # so a broken optional dep can never take the whole registry down.
    def run(*args, **kwargs):
        import importlib
        fn = getattr(importlib.import_module(module), name)
        return fn(*args, **kwargs)
    run.__name__ = name
    return run


ACTIONS = {
    "test_ping":       test_ping,
    "mute_toggle":     _lazy("handsfree.actions.keys", "mute_toggle"),
    "media_playpause": _lazy("handsfree.actions.keys", "media_playpause"),
    "privacy_blank":   _lazy("handsfree.actions.privacy", "privacy_blank"),
    "privacy_restore": _lazy("handsfree.actions.privacy", "privacy_restore"),
    "playlist_open":   _lazy("handsfree.actions.playlist", "playlist_open"),
    "led_beat_start":  _lazy("handsfree.beats", "led_beat_start"),
    "break_prompt":    _lazy("handsfree.breakwatch", "break_prompt"),
}


def fire(word: str) -> bool:
    """Fire one word. Returns True if it ran, False if unknown or it raised.

    Never lets an action's exception escape — a misfiring feature must not
    kill the gesture loop mid-demo.
    """
    fn = ACTIONS.get(word)
    if fn is None:
        known = " ".join(sorted(ACTIONS))
        print(f"[actions] unknown word {word!r}. Known: {known}", file=sys.stderr)
        return False
    t0 = time.perf_counter()
    try:
        fn()
    except Exception as exc:
        print(f"[actions] {word} failed: {exc!r}", file=sys.stderr)
        return False
    print(f"[actions] {word} done in {(time.perf_counter() - t0) * 1e3:.0f} ms",
          file=sys.stderr)
    return True
