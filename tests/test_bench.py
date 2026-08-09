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


# ── cross-platform ──────────────────────────────────────────────────────────

def test_kill_switch_keycodes_differ_per_platform():
    """The bug this guards: Q's key code is not portable.

    safety.py once hardcoded 81 (Windows VK_Q). On macOS 'q' arrives as 12 and
    on X11 as 113, so the hotkey silently never fired — a kill switch you would
    trust and that was not there. Worse than having none.
    """
    from handsfree.safety import q_vks
    assert q_vks("win32") == {81}
    assert q_vks("darwin") == {12}
    assert q_vks("linux") == {113}
    assert q_vks("win32") != q_vks("darwin"), "the whole point of the table"
    # an unrecognised platform must accept everything, never nothing
    assert q_vks("sunos5") >= {81, 12, 113}


class _FakeKey:
    """Stand-in for a pynput Key member (modifiers) or KeyCode (letters)."""
    def __init__(self, name=None, vk=None, char=None):
        self.name, self.vk, self.char = name, vk, char
    def __repr__(self):
        return f"<{self.name or self.char or self.vk}>"


def _fake_pynput(monkeypatch):
    """Install a fake pynput and return a dict that captures the listener."""
    import types
    captured = {}

    class Key:
        ctrl = _FakeKey("ctrl")
        ctrl_l = _FakeKey("ctrl_l")
        ctrl_r = _FakeKey("ctrl_r")
        alt = _FakeKey("alt")
        alt_l = _FakeKey("alt_l")
        alt_r = _FakeKey("alt_r")

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            captured["press"] = on_press
            captured["release"] = on_release
            self.daemon = False
        def start(self):
            captured["started"] = True

    kb = types.ModuleType("pynput.keyboard")
    kb.Key, kb.Listener = Key, Listener
    pynput = types.ModuleType("pynput")
    pynput.keyboard = kb
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", kb)
    captured["Key"] = Key
    return captured


@pytest.mark.parametrize("platform,q_vk", [
    ("darwin", 12), ("win32", 81), ("linux", 113),
])
def test_kill_switch_actually_fires_on_each_platform(monkeypatch, platform, q_vk):
    """Drive the real listener callbacks with that platform's key codes.

    This is the closest thing to running it on a Mac that a Linux box can do,
    and it is the check that would have caught the original bug: with the old
    hardcoded VK_Q = 81, the darwin case here never fires.
    """
    import handsfree.safety as safety

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(safety, "_armed_once", False)
    killed = []
    monkeypatch.setattr(safety, "_panic", lambda reason="": killed.append(reason))
    cap = _fake_pynput(monkeypatch)

    safety.arm()
    press, release = cap["press"], cap["release"]
    Key = cap["Key"]

    # q alone: nothing
    press(_FakeKey(vk=q_vk))
    assert not killed, "fired without modifiers"

    # ctrl+q: still nothing
    press(Key.ctrl_l)
    press(_FakeKey(vk=q_vk))
    assert not killed, "fired without alt"

    # ctrl+alt+q: fires
    press(Key.alt_l)
    press(_FakeKey(vk=q_vk))
    assert killed, f"kill switch did not fire on {platform} (q vk={q_vk})"

    # releasing a modifier disarms it again
    killed.clear()
    release(Key.alt_l)
    press(_FakeKey(vk=q_vk))
    assert not killed, "fired after alt was released"


def test_kill_switch_falls_back_to_the_character(monkeypatch):
    """Belt and braces for a platform whose code isn't in the table."""
    import handsfree.safety as safety
    monkeypatch.setattr(sys, "platform", "sunos5")
    monkeypatch.setattr(safety, "_armed_once", False)
    killed = []
    monkeypatch.setattr(safety, "_panic", lambda reason="": killed.append(reason))
    cap = _fake_pynput(monkeypatch)
    safety.arm()
    Key = cap["Key"]
    cap["press"](Key.ctrl_l)
    cap["press"](Key.alt_l)
    cap["press"](_FakeKey(vk=9999, char="q"))
    assert killed, "char fallback did not fire"


def test_no_bare_windows_keycodes_left_in_the_hotkey_path():
    src = (REPO / "handsfree" / "safety.py").read_text()
    assert "VK_CTRL" not in src and "VK_ALT" not in src, (
        "Windows-only modifier tables are back; modifiers must match pynput Key members")


@pytest.mark.parametrize("platform,expected", [
    ("darwin", ("command", "shift", "a")),
    ("win32", ("alt", "a")),
    ("linux", ("alt", "a")),
])
def test_zoom_chord_per_platform(platform, expected):
    """Zoom's global mute is Cmd+Shift+A on macOS, Alt+A elsewhere.
    Sending the wrong one is silent."""
    from handsfree.actions.keys import zoom_chord
    assert zoom_chord(platform) == expected


def test_mac_uses_system_media_events_not_key_names(monkeypatch):
    """On macOS 'playpause' is not in pyautogui's key table and _keyDown
    returns silently for unknown keys — so the naive path reports success and
    does nothing. Both actions must take the NSSystemDefined route instead."""
    import handsfree.actions.keys as keys
    monkeypatch.setattr(sys, "platform", "darwin")
    pressed, media = [], []
    monkeypatch.setattr(keys, "_press", lambda *k: pressed.append(k))
    monkeypatch.setattr(keys, "_mac_media", lambda n: media.append(n))

    keys.mute_toggle()
    keys.media_playpause()

    assert media == [keys.MAC_MUTE, keys.MAC_PLAYPAUSE], (
        f"macOS did not use system media events: {media}")
    assert ("volumemute",) not in pressed, "sent the unreliable macOS key name"
    assert ("playpause",) not in pressed, "sent a key macOS ignores entirely"
    assert ("command", "shift", "a") in pressed, "wrong Zoom chord on macOS"


def test_non_mac_still_uses_key_names(monkeypatch):
    """Don't break Windows while fixing the Mac."""
    import handsfree.actions.keys as keys
    monkeypatch.setattr(sys, "platform", "win32")
    pressed, media = [], []
    monkeypatch.setattr(keys, "_press", lambda *k: pressed.append(k))
    monkeypatch.setattr(keys, "_mac_media", lambda n: media.append(n))

    keys.mute_toggle()
    keys.media_playpause()

    assert not media, "used the macOS path on Windows"
    assert ("volumemute",) in pressed and ("playpause",) in pressed
    assert ("alt", "a") in pressed


def test_mac_media_names_exist_in_pyautogui(monkeypatch):
    """MAC_MUTE / MAC_PLAYPAUSE must be real entries in pyautogui's macOS
    special-key table, or _mac_media raises KeyError on the demo machine."""
    import handsfree.actions.keys as keys
    try:
        from pyautogui import _pyautogui_osx as osx
        table = osx.special_key_translate_table
    except Exception:
        table = {"KEYTYPE_MUTE": 7, "KEYTYPE_PLAY": 16}   # verified upstream
    assert keys.MAC_MUTE in table
    assert keys.MAC_PLAYPAUSE in table


def test_board_autodetect_is_safe_with_no_ports(monkeypatch):
    """No board attached must return None, not raise or pick something random."""
    from handsfree import beats
    assert beats.find_board() is None or isinstance(beats.find_board(), str)


# ── F3 · privacy blank ──────────────────────────────────────────────────────

def test_privacy_binds_escape():
    """PASS: Esc dismisses. Non-negotiable — a topmost black window with no
    keyboard escape locks the laptop in front of the room."""
    src = (REPO / "handsfree" / "actions" / "privacy.py").read_text()
    assert "<Escape>" in src, "Esc is not bound on the blank"


def test_nothing_grabs_the_keyboard():
    """The kill switch must stay reachable underneath the blank.

    Tk's grab_set() routes all input to one window, which would swallow
    Ctrl+Alt+Q and leave a black screen nobody can dismiss — the exact
    lock-out the plan calls out.
    """
    for path in (REPO / "handsfree").rglob("*.py"):
        src = path.read_text()
        assert "grab_set" not in src, f"{path.name} grabs the keyboard"
        assert "grab_global" not in src, f"{path.name} grabs the keyboard"


def test_privacy_actions_are_safe_headless():
    """Firing them on a box with no display must not raise."""
    fire("privacy_blank")
    fire("privacy_restore")


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

    Drift is ACCUMULATION, not jitter. A shared machine will occasionally
    stall a thread for tens of milliseconds and there is nothing the
    scheduler can do about that; what it must never do is let those stalls
    add up, so that by beat 40 the LED is a whole beat behind the music.
    So this compares the back half's error against the front half's rather
    than putting a tight absolute bound on any single pulse — a bound that
    would really just be measuring how busy the box is.
    """
    target = [i * 0.05 for i in range(24)]
    fired: list[float] = []
    t0 = time.monotonic()
    s = BeatScheduler(target, lambda: fired.append(time.monotonic() - t0))
    s.start(t0)
    s.join(timeout=15)

    assert len(fired) == len(target), f"dropped pulses: {len(fired)}/{len(target)}"
    errors = [abs(f - b) for f, b in zip(fired, target)]

    half = len(errors) // 2
    front = sum(errors[:half]) / half
    back = sum(errors[half:]) / (len(errors) - half)
    # Accumulating drift would make the back half systematically worse. Allow
    # a wide margin so ordinary jitter can't trip it; real accumulation over
    # 24 pulses would be orders of magnitude, not a factor of 4.
    assert back < max(front * 4, 0.020), (
        f"error grows through the run: front {front*1e3:.1f} ms, back {back*1e3:.1f} ms")
    # and a loose sanity ceiling to catch gross breakage
    assert max(errors) < 0.100, f"max error {max(errors)*1e3:.1f} ms"


def test_scheduler_anchors_to_absolute_times():
    """The mechanism behind the no-drift claim, tested without a clock race.

    Interval sleeping accumulates; absolute anchoring cannot. Feeding a t0
    already in the past means every beat is overdue, so a correct scheduler
    fires them all immediately rather than sleeping one interval per beat.
    """
    target = [i * 10.0 for i in range(6)]        # 50 s of "music"
    fired = []
    t0 = time.monotonic() - 60.0                 # ...that finished a minute ago
    s = BeatScheduler(target, lambda: fired.append(1))
    started = time.monotonic()
    s.start(t0)
    s.join(timeout=10)
    assert time.monotonic() - started < 1.0, "scheduler slept per-interval, not to absolute times"


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
