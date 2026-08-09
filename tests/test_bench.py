"""Bench tests for Track B — the pass numbers from bench-plan.html.

"A feature without a passing bench test is not built."

Everything here runs headless: no camera, no Arduino, no display, no Zoom. The
parts that genuinely need hardware or a human (does the phone show muted? is
the LED on the beat when you film it?) are listed in BENCH_MANUAL below and
printed by `python -m pytest -s`, so they can't be quietly forgotten.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from handsfree.actions import ACTIONS, WORDS, fire            # noqa: E402
from handsfree.beats import BeatScheduler, extract_beats      # noqa: E402
from handsfree.breakwatch import StillnessTracker             # noqa: E402

BENCH_MANUAL = """
Still needs a human, a phone, or hardware — bench-plan.html:
  F2  join a test meeting from your phone, fire mute_toggle 5x each way with
      Zoom minimised, watch the phone indicator          PASS <500 ms, 5/5
  F3  fire privacy_blank on the real desktop             PASS covers <1 s, Esc dismisses,
                                                              Ctrl+Alt+Q still works
  F5  film 20 s of the LED with the music playing        PASS no visible drift
  N1  Ctrl+Alt+Q against handsfree.runaway, 3 of 3       PASS stops <=200 ms
"""


# ── F1 · the action registry ────────────────────────────────────────────────

def test_every_contracted_word_is_registered():
    """The seam with Nicholas. A missing word = a gesture that fires nothing."""
    for word in WORDS:
        assert word in ACTIONS, f"contracted word not registered: {word}"


def test_word_list_matches_the_plan():
    """Fixed at 15:45 and never renamed — bench-plan.html."""
    assert set(WORDS) == {
        "mute_toggle", "media_playpause", "privacy_blank", "privacy_restore",
        "playlist_open", "led_beat_start", "led_beat_stop", "break_prompt",
    }


def test_fire_test_ping_runs():
    """The step-1 check: --fire test_ping prints something."""
    assert fire("test_ping") is True


def test_fire_unknown_word_is_survivable():
    """A typo from the gesture side must not raise into the caller."""
    assert fire("no_such_word") is False


def test_fire_never_propagates_an_action_exception():
    """A misfiring feature must not take down the gesture loop."""
    ACTIONS["_boom"] = lambda: 1 / 0
    try:
        assert fire("_boom") is False
    finally:
        del ACTIONS["_boom"]


@pytest.mark.parametrize("cmd", [
    [sys.executable, "-m", "handsfree.actions", "--fire", "test_ping"],
    [sys.executable, "-m", "handsfree", "--fire", "test_ping"],
])
def test_cli_entrypoints(cmd):
    """Both spellings in the plan docs must work."""
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert "pong" in r.stdout


def test_cli_list_shows_every_word():
    r = subprocess.run([sys.executable, "-m", "handsfree.actions", "--list"],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    for word in WORDS:
        assert word in r.stdout


def test_cli_unknown_word_exits_nonzero():
    r = subprocess.run([sys.executable, "-m", "handsfree.actions", "--fire", "nope"],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1


# ── F2 · mute and play/pause ────────────────────────────────────────────────

def test_mute_dispatch_latency_is_well_under_the_budget(monkeypatch):
    """PASS <500 ms gesture→silence. The registry's share must be negligible.

    pyautogui is stubbed — this measures our dispatch overhead, not the OS.
    """
    import handsfree.actions.keys as keys
    sent = []
    monkeypatch.setattr(keys, "_press", lambda *k: sent.append(k))

    t0 = time.perf_counter()
    fire("mute_toggle")
    elapsed_ms = (time.perf_counter() - t0) * 1e3

    assert elapsed_ms < 50, f"dispatch overhead {elapsed_ms:.1f} ms eats the 500 ms budget"
    assert ("volumemute",) in sent, "OS mute key not sent"
    assert ("alt", "a") in sent, "Zoom global mute (Alt+A) not sent"


def test_media_playpause_sends_the_media_key(monkeypatch):
    import handsfree.actions.keys as keys
    sent = []
    monkeypatch.setattr(keys, "_press", lambda *k: sent.append(k))
    fire("media_playpause")
    assert sent == [("playpause",)]


def test_key_names_are_real_pyautogui_keys(monkeypatch):
    """A typo here is a silent no-op on stage — nothing raises, nothing mutes.

    Verified against pyautogui 0.9.54's KEY_NAMES table when it's installed;
    otherwise checked against the names confirmed present in that table.
    """
    import handsfree.actions.keys as keys
    used = set()
    monkeypatch.setattr(keys, "_press", lambda *k: used.update(k))
    keys.mute_toggle()
    keys.media_playpause()

    try:
        import pyautogui
        valid = set(pyautogui.KEY_NAMES)
    except Exception:
        valid = {"volumemute", "volumeup", "volumedown", "playpause",
                 "nexttrack", "prevtrack", "alt", "a", "esc"}
    bad = used - valid
    assert not bad, f"not real pyautogui key names: {bad}"


def test_mute_still_sends_os_key_when_zoom_shortcut_fails(monkeypatch):
    """Alt+A failing must not swallow the OS mute — degrade, don't die."""
    import handsfree.actions.keys as keys
    sent = []

    def flaky(*keys_):
        if keys_ == ("alt", "a"):
            raise RuntimeError("no Zoom")
        sent.append(keys_)
    monkeypatch.setattr(keys, "_press", flaky)
    keys.mute_toggle()
    assert ("volumemute",) in sent


# ── F5 · beats ──────────────────────────────────────────────────────────────

def test_extracted_tempo_matches_the_song():
    """The track is authored at 120 BPM; librosa must agree within 2 BPM."""
    song = REPO / "media" / "beat_track.wav"
    assert song.exists(), "demo song missing — run python -m handsfree.make_demo_track"
    extract_beats(song)
    cached = json.loads((song.parent / (song.name + ".beats.json")).read_text())
    assert abs(cached["tempo_bpm"] - 120.0) < 2.0
    assert len(cached["beats"]) > 50


def test_beat_cache_is_reused():
    """Re-extraction at 19:59 is seconds you don't have."""
    song = REPO / "media" / "beat_track.wav"
    extract_beats(song)
    t0 = time.perf_counter()
    extract_beats(song)
    assert (time.perf_counter() - t0) < 0.25, "cache not being used"


def test_scheduler_does_not_drift():
    """PASS: no visible drift over 20 s.

    Compressed 20x so the suite stays fast: 40 beats at 25 ms is the same
    number of scheduling decisions as 20 s of 120 BPM music. Absolute anchoring
    means the LAST pulse must be as accurate as the first — that is the
    property the film-it-back test is really checking.
    """
    target = [i * 0.025 for i in range(40)]
    fired: list[float] = []
    t0 = time.monotonic()
    s = BeatScheduler(target, lambda: fired.append(time.monotonic() - t0))
    s.start(t0)
    s.join(timeout=10)

    assert len(fired) == len(target), f"dropped pulses: {len(fired)}/{len(target)}"
    errors = [abs(f - b) for f, b in zip(fired, target)]
    assert max(errors) < 0.030, f"max error {max(errors)*1e3:.1f} ms"
    # the drift signature: late pulses no worse than early ones
    assert errors[-1] < 0.030, f"final pulse drifted {errors[-1]*1e3:.1f} ms"


def test_scheduler_stops_cleanly():
    fired = []
    s = BeatScheduler([i * 0.05 for i in range(100)], lambda: fired.append(1))
    s.start()
    time.sleep(0.12)
    s.stop()
    s.join(timeout=5)
    assert not s.running
    n = len(fired)
    time.sleep(0.15)
    assert len(fired) == n, "still pulsing after stop()"


def test_scheduler_survives_a_failing_sink():
    """Unplugging the Arduino mid-song must not kill the screen dot."""
    good = []

    def sinks():
        raise IOError("board yanked")
    s = BeatScheduler([0.0, 0.01, 0.02], lambda: (good.append(1), sinks()))
    s.start()
    s.join(timeout=5)
    assert len(good) == 3, "a broken sink stopped the scheduler"


def test_led_beat_start_does_not_block_the_caller():
    """Fired from the gesture loop, it must return immediately.

    This is the bug that would freeze gesture recognition at the first
    thumbs-up: a Tk mainloop running on the caller's thread.
    """
    import handsfree.beats as beats
    t0 = time.perf_counter()
    try:
        beats.led_beat_start()
        elapsed = time.perf_counter() - t0
    finally:
        beats.led_beat_stop()
    assert elapsed < 2.0, f"led_beat_start blocked for {elapsed:.1f}s"


def test_led_beat_start_is_idempotent():
    """A second thumbs-up must not stack two schedulers on one song."""
    import handsfree.beats as beats
    try:
        beats.led_beat_start()
        first = beats._scheduler
        beats.led_beat_start()
        assert beats._scheduler is first
    finally:
        beats.led_beat_stop()


# ── F6 · break reminder ─────────────────────────────────────────────────────

def _sit(tracker, *, seconds, jitter, t, fps=15.0, base=None):
    """Feed synthetic shoulder/hip landmarks. Returns (fire_time|None, t)."""
    import random
    base = base or [(0.40, 0.30), (0.60, 0.30), (0.45, 0.60), (0.55, 0.60)]
    step = 1.0 / fps
    end = t + seconds
    while t < end:
        pts = [(x + random.uniform(-jitter, jitter), y + random.uniform(-jitter, jitter))
               for x, y in base]
        if tracker.update(pts, t):
            return t, t
        t += step
    return None, t


def test_break_fires_at_thirty_seconds_of_stillness():
    """PASS: fires at 30 s of stillness."""
    import random
    random.seed(7)
    tr = StillnessTracker()
    _, t = _sit(tr, seconds=5, jitter=0.02, t=0.0)       # moving about
    still_from = t
    fired, t = _sit(tr, seconds=60, jitter=0.0004, t=t)  # sitting still
    assert fired is not None, "never fired"
    window = fired - still_from
    assert 29.0 <= window <= 33.0, f"fired after {window:.1f}s of stillness"


def test_landmark_noise_alone_does_not_reset_the_timer():
    """The rolling energy window exists for exactly this.

    Per-frame thresholding resets on a single noisy frame and the reminder
    never fires at all.
    """
    import random
    random.seed(11)
    tr = StillnessTracker()
    fired, _ = _sit(tr, seconds=45, jitter=0.0008, t=0.0)
    assert fired is not None, "noise floor prevented it from ever firing"


def test_standing_up_resets_within_three_seconds():
    """PASS: resets within 3 s of real movement.

    Frames run continuously from sitting into standing — no gap — because a
    gap is a different case (see the pose-lost test below).
    """
    import random
    random.seed(13)
    tr = StillnessTracker()
    fired, t = _sit(tr, seconds=45, jitter=0.0004, t=0.0)
    assert fired is not None and tr.is_still

    stood_at = t
    sitting = [(0.40, 0.30), (0.60, 0.30), (0.45, 0.60), (0.55, 0.60)]
    reset_at = None
    step = 1 / 15
    while t < stood_at + 3.0:
        # rise smoothly over ~0.5 s, then stay standing
        lift = min(0.25, 0.25 * (t - stood_at) / 0.5)
        pts = [(x + random.uniform(-0.002, 0.002), y - lift + random.uniform(-0.002, 0.002))
               for x, y in sitting]
        tr.update(pts, t)
        if not tr.is_still and reset_at is None:
            reset_at = t
        t += step
    assert reset_at is not None, "standing up never reset the timer"
    assert reset_at - stood_at < 3.0, f"reset took {reset_at - stood_at:.2f}s"


def test_a_gap_in_the_feed_is_not_counted_as_stillness():
    """Pose lost for 5 s, then reacquired: unobserved time is not stillness.

    Otherwise a dropped camera frame run would count toward the 30 s and the
    reminder fires at someone who has been moving the whole time.
    """
    import random
    random.seed(19)
    tr = StillnessTracker()
    _, t = _sit(tr, seconds=25, jitter=0.0004, t=0.0)     # 25 s still, not yet fired
    assert tr.is_still
    fired, _ = _sit(tr, seconds=8, jitter=0.0004, t=t + 5.0)   # 5 s blackout
    assert fired is None, "counted unobserved time toward the stillness window"


def test_break_fires_only_once_per_still_period():
    """One nag, not one per frame for the rest of the demo."""
    import random
    random.seed(17)
    tr = StillnessTracker()
    t, fires = 0.0, 0
    while t < 90.0:
        pts = [(x + random.uniform(-0.0004, 0.0004), y + random.uniform(-0.0004, 0.0004))
               for x, y in [(0.4, 0.3), (0.6, 0.3), (0.45, 0.6), (0.55, 0.6)]]
        if tr.update(pts, t):
            fires += 1
        t += 1 / 15
    assert fires == 1, f"fired {fires} times in one still period"


def test_manual_bench_items_are_visible():
    """Not a real assertion — prints what still needs a human."""
    print(BENCH_MANUAL)
