# Hands-free HCI — build plan for 2026-08-09

**Deliverable: working demo by 19:30. Pitch 20:00. No slides.**

---

## 1. How Ankit's cursor works

Source: `github.com/ankittejyadav/physicsGames`, `src/App.svelte` (~500 lines, Svelte + Vite).
Only real dependency: `@mediapipe/tasks-vision@0.10.34`.

```
getUserMedia → HandLandmarker.detectForVideo(video, ts)
  → landmarks[0]                         // first hand only
  → indexPos = {x: 1 - lm[8].x, ...}     // landmark 8 = index tip, X mirrored
  → cursorX = indexPos.x * canvasWidth   // normalized 0-1 → canvas pixels
  → smoothedX += (cursorX - smoothedX) * 0.15    // LERP smoothing
  → pinch = dist3D(lm[4], lm[8]) < 0.045  with 400ms cooldown
  → drawCursor(smoothedX, smoothedY)     // star pointer painted on <canvas>
```

**The critical difference from what we're building:** his cursor is *painted on a
canvas inside his own web app*. It never touches the operating system. We want to
move the **real OS cursor** and click **real windows**. Browsers cannot do that —
so our control loop has to be Python, not the browser.

### Reuse directly (proven, don't re-derive)
- Landmark **8** (index tip) as the pointer
- **LERP 0.15** smoothing constant — good starting value
- **Pinch (4↔8 distance) as click** — better than dwell-click: faster, intentional,
  no false fires from resting
- **400 ms cooldown** on the click
- Mirror X so the cursor follows the hand the way a mirror does

### Must change
| His | Ours | Why |
|---|---|---|
| Canvas cursor | `pyautogui` OS cursor | we control real apps |
| Maps 0–1 → full canvas | maps **0.25–0.75 → full screen** | hands are unreliable at frame edges; you physically can't reach screen corners otherwise |
| Fixed pinch threshold `0.045` | **ratio** `dist(4,8) / dist(0,9)` | his threshold breaks when you lean closer to the camera — normalising by hand size makes it depth-invariant |
| LERP | One Euro Filter (if time) | LERP either lags or jitters; One Euro adapts — smooth when still, responsive when fast |
| No kill switch | **mandatory** | see §5 |

---

## 2. The gaze question — read this before committing

The brief says the camera "watches where you are looking". Honest numbers:

| Signal | Precision | Stability | Fatigue | Use it for |
|---|---|---|---|---|
| Iris gaze (webcam) | ±3–8° ≈ **100–300 px** | poor — saccades, micro-jitter | none | ✗ cannot click a button |
| Head pose (yaw/pitch) | good | high | neck strain ~2 min | ✓ fallback pointer |
| Index fingertip | high | high | "gorilla arm" ~3 min | ✓ **primary** |

A laptop webcam cannot do gaze-to-cursor precisely enough to hit a Zoom mute button.
Anyone promising that on stage will miss and lose the room.

**Design that uses each signal where it's strong — gaze warps, hand refines.**
Gaze picks the *region* (±200 px is plenty to choose a quadrant or a window), the
fingertip does fine positioning inside it. This is MAGIC pointing (Zhai et al., 1999) —
a real, citable HCI technique, and a much better pitch than "we did gaze tracking":

> "We didn't fight gaze's imprecision. We used it for the thing it's actually good at."

Build the hand cursor first. Add gaze-warp only if you're ahead at 15:30.

---

## 3. Where the *foundation model* actually is

**This matters for judging.** MediaPipe is not a foundation model — it's a 2020-era
landmark detector. Today's theme is *FM for the Physical World*. A pure-MediaPipe
demo invites "so it's a hand tracker?"

Fix: put a **zero-shot open-vocabulary gesture layer** on top. SigLIP/CLIP over the
cropped hand region, classes supplied as plain English at runtime — exactly the
pattern already proven working with CLAP in this repo (0.36 s/window on CPU).

```
MediaPipe   → fast, reliable rails: is there a hand, where, which landmarks (30 fps)
SigLIP      → open-vocabulary meaning: "finger over lips", "palm facing camera",
              "thumbs up", "peace sign"          (2–4 Hz is plenty)
```

**The winning demo moment:** a judge invents a gesture. You type the sentence. It
works, live, with no retraining. That is a foundation-model story no amount of
MediaPipe gets you.

Architecturally this drops straight into the existing spine — `source → model → rule
→ action` — and the dashboard we already built renders the confidence bars, so the
audience *sees* the model thinking.

---

## 4. Scope triage — 6 features will not fit in 8 hours

| # | Feature | Effort | Demo impact | Call |
|---|---|---|---|---|
| 4 | Finger-to-lips → mute / pause | 45 m | ★★★★★ | **Build 1st** — most relatable pain |
| 2 | Cursor + pinch click + scroll | 2 h | ★★★★★ | **Build 2nd** — the headline claim |
| 6 | Palm flash → privacy blank | 20 m | ★★★★ | **Build 3rd** — near-free once gestures work |
| 5 | Thumbs-up → playlist + LED to beat | 1.5 h | ★★★★ | **Build 4th** — the physical tie-in judges love |
| 1 | Movement → break reminder | 30 m | ★★ | Last. Demo with a compressed timer |
| 3 | Sign → voice agent | 2–3 h | ★★ | **CUT** |

**Cut #3.** Two reasons: your own tagline is *"no hands and no voice"* — adding a
voice agent argues against your thesis on stage. And Whisper + TTS + agent wiring is
2–3 hours that buys nothing visual.

Four features, demoed cleanly, beats six demoed half-working. Every time.

---

## 5. Non-negotiable safety rails

Once `pyautogui` owns the mouse and a gesture misfires, **you cannot click "stop"** —
you have handed away the only input device you had. Build these before anything else:

1. **Global keyboard kill switch** — `pynput` hotkey `Ctrl+Alt+Q`, hard-exits. First commit.
2. `pyautogui.FAILSAFE = True` — slamming the cursor to a screen corner aborts.
3. **Dead-man's switch** — the cursor only moves while a specific pose is held
   (e.g. index extended). Drop your hand, control stops. This also solves the
   "I was just gesturing while I talked" problem during the pitch.
4. Cursor control **off by default**, armed by an explicit gesture.

---

## 6. Timeline (now → 19:30)

| Time | Work | Milestone |
|---|---|---|
| 11:40–12:15 | Kill switch **first**. Webcam source + hand landmarks into the spine, HUD draws them | rails safe |
| 12:15–13:00 | Gesture layer: MediaPipe canned (Thumb_Up, Open_Palm, Victory, Fist) → rule → action | **A: gestures recognised** |
| 13:00–13:45 | Action sinks: mute / play-pause, privacy blank (fullscreen always-on-top Tk window) | **B: 2 features demo-able** |
| 13:45–15:30 | Cursor: fingertip → OS cursor, pinch click, two-finger scroll | **C: headline claim works** |
| 15:30–16:15 | SigLIP zero-shot layer + "type a new gesture" | **D: the FM story** |
| 16:15–17:00 | Thumbs-up → playlist, Arduino LED to the beat | needs the board |
| 17:00–17:30 | Break reminder (compressed timer for demo) | |
| 17:30–18:15 | Integration, threshold tuning **under venue lighting** | |
| 18:15–19:00 | **Record fallback video. Capture replay log. Freeze code.** | insurance |
| 19:00–19:30 | Zoom rehearsal. Submit card at `sundai.club/pitch` | |

**Cut lines** — if you are behind at that time, drop the feature and move on:
15:30 → drop SigLIP. 16:15 → drop the LED. 17:00 → drop the break reminder.
Never cut the 18:15 recording block. That block is why you have a demo at all.

---

## 7. Risks, ranked

1. **Webcam contention with Zoom.** Zoom wants the camera for your pitch; so does the
   app. Windows often allows sharing, but not always. **Test this at 12:00, not 19:00.**
   Mitigations: keep Zoom video off during the demo, pitch from a second device, or
   route through OBS virtual camera.
2. **Runaway cursor** — see §5.
3. **Venue lighting** — MediaPipe degrades in backlight. Tune at the venue, and keep a
   lamp handy.
4. **Gorilla arm** — hold the demo under ~90 seconds of continuous hand-in-air, or your
   hand shakes on stage.
5. **CPU budget** — MediaPipe 30 fps and SigLIP 2–4 Hz coexist fine on this machine
   (no CUDA: Intel Arc 130V, 15.7 GB RAM). Do not try to run SigLIP per frame.

---

## 8. Pitch structure (5 min, no slides)

1. Sit down, hands on the desk. "Someone walks up to my desk." Finger to lips —
   **audio mutes, screen blurs.** No hands on keyboard. *(~30 s, the hook)*
2. Thumbs up — playlist opens, the LED on the desk pulses to the beat. *(the physical world)*
3. Move the cursor by hand, pinch to click something real. *(the headline)*
4. **Judge invents a gesture. You type the sentence. It works.** *(the foundation model)*
5. One line on why gaze warps and hand refines — you know the literature. *(credibility)*
