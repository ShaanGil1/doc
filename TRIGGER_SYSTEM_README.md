# Suggestion Trigger System — Design Recommendations

## Overview

This document outlines the recommended approach for triggering the backend suggestion pipeline in a real-time text suggestion system. The core design principle is that **any single trigger condition firing is sufficient to send a payload to the backend**. The backend (the "meaningful change function") decides whether the change warrants a new suggestion — the frontend's job is just to know *when* to ask.

All triggers share a reset contract: when any trigger fires, the timer resets and the edit distance counter resets to zero.

---

## Recommended Trigger Set

### 1. Debounced Timer

Fire after `DEBOUNCE_MS` of continuous typing activity, but only if the user is not in the idle state (see Idle Detection below). The timer resets on every keystroke. This is the baseline trigger — it catches the case where the user is typing steadily but no other threshold has been crossed.

**Suggested starting value:** `DEBOUNCE_MS = 800` (needs tuning)

```python
DEBOUNCE_MS = 800  # guess, tune this

timer = None
is_idle = False

def on_keystroke():
    global timer
    if is_idle:
        return  # idle state suppresses the timer entirely

    if timer:
        timer.cancel()

    timer = set_timeout(fire_trigger, DEBOUNCE_MS)

def fire_trigger():
    send_to_backend(get_current_text())
    reset_all_triggers()
```

**Key asterisk:** the timer only matters when the user is *actively typing*. If idle detection has kicked in, the timer should not fire even if it somehow wasn't cancelled. Guard both places.

---

### 2. Edit Distance Threshold

Track a running cumulative edit distance between the current text and a stored snapshot of what the text looked like at the last trigger. When that delta crosses `EDIT_DISTANCE_THRESHOLD`, fire immediately without waiting for the timer.

This handles the case where someone makes a lot of small edits that individually feel minor but cumulatively represent a meaningful change — like rewriting a sentence word by word.

**Suggested starting value:** `EDIT_DISTANCE_THRESHOLD = 20` (guess, tune this based on typical input length in your app)

```python
EDIT_DISTANCE_THRESHOLD = 20  # guess, tune this

last_snapshot = ""

def levenshtein(a, b):
    # standard dynamic programming implementation
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[m][n]

def on_text_change(current_text):
    distance = levenshtein(last_snapshot, current_text)
    if distance >= EDIT_DISTANCE_THRESHOLD:
        fire_trigger(current_text)

def fire_trigger(text):
    send_to_backend(text)
    reset_all_triggers()

def reset_all_triggers():
    global last_snapshot
    last_snapshot = get_current_text()
    cancel_debounce_timer()
    reset_edit_distance()  # implicitly done by updating the snapshot
```

**Note on performance:** Levenshtein is O(m*n) which is fine for short inputs but can get slow for large documents. If you're dealing with long text, consider a cheaper approximation — character count delta, token count delta, or just diffing the last N characters around the cursor. The point is to detect meaningful change, not to compute a precise edit distance.

---

### 3. Paste Event

A paste is almost always a semantically meaningful change and should trigger immediately. Rather than running it as a fully independent trigger though, route it through the edit distance checker first — this gives you a consistent "meaningful change" gate and also resets the edit distance counter appropriately.

```python
def on_paste(pasted_content):
    # Don't wait for the debounce timer — paste is a clear signal
    # But route through edit distance check to keep reset logic consistent
    current_text = get_text_after_paste(pasted_content)
    distance = levenshtein(last_snapshot, current_text)

    if distance >= EDIT_DISTANCE_THRESHOLD:
        fire_trigger(current_text)
    else:
        # Even a small paste should probably fire — you can choose to
        # lower the threshold here or just fire unconditionally
        fire_trigger(current_text)
```

**Practical note:** You could argue paste should always fire unconditionally (skip the threshold check entirely) since the user's intent is clear. Both approaches are reasonable. The value of routing through edit distance is just that it keeps your reset logic centralized and avoids having a separate special-case branch for paste state.

---

### 4. Idle Detection

Idle is not a trigger — it is a gate that suppresses all other triggers. If the user stops typing for `IDLE_TIMEOUT_MS`, the system stops watching for changes and enters a dormant state. It wakes up again the moment typing resumes.

**Suggested starting value:** `IDLE_TIMEOUT_MS = 5000` (guess, tune this — the right value depends heavily on your use case)

```python
IDLE_TIMEOUT_MS = 5000  # guess, tune this

idle_timer = None
is_idle = False

def on_keystroke():
    global idle_timer, is_idle

    # Any keystroke wakes the system from idle
    if is_idle:
        is_idle = False
        on_wake_from_idle()

    # Reset the idle countdown on every keystroke
    if idle_timer:
        idle_timer.cancel()
    idle_timer = set_timeout(enter_idle, IDLE_TIMEOUT_MS)

    # Now run normal trigger logic
    run_trigger_checks()

def enter_idle():
    global is_idle
    is_idle = True
    # Optionally: cancel any pending debounce timer here too

def on_wake_from_idle():
    # Reset snapshot on wake so the first keystroke doesn't
    # immediately fire based on stale distance
    global last_snapshot
    last_snapshot = get_current_text()
```

**Important:** when waking from idle, reset the edit distance snapshot. Otherwise the system might immediately fire because the text changed a lot while idle detection was suppressing triggers — which isn't the behavior you want.

---

### 5. Explicit Hotkey

A manual trigger the user fires intentionally — e.g. `Ctrl+Space` or `Tab` — that bypasses all conditions and requests suggestions immediately, including while idle. This is the one trigger that should never be suppressed.

There are two reasons this earns a spot in the recommended set rather than just living in the considerations section. First, it is trivially cheap to implement relative to the value it provides. Second, and more importantly, it produces clean unambiguous signal: when a user hits the hotkey they are explicitly telling you they want a suggestion right now, which is qualitatively different from any of the automatic triggers. Over time that signal is useful for calibrating your other thresholds.

The hotkey should also wake the system from idle — a user consciously requesting a suggestion is a clear intent signal regardless of how long they've been inactive.

```python
HOTKEY = "ctrl+space"  # pick whatever fits your app's keybinding conventions

def on_hotkey():
    global is_idle

    # Wake from idle if needed — explicit intent overrides dormant state
    if is_idle:
        is_idle = False
        on_wake_from_idle()

    # Fire immediately, no conditions checked
    fire_trigger(get_current_text())
```

**Note on key choice:** `Ctrl+Space` is a common autocomplete convention (IDEs use it) so it has reasonable discoverability. `Tab` is tempting but likely conflicts with existing behavior in your input. Whatever you pick, make sure it doesn't swallow a key the user actually needs for text entry.

---

## Trigger Interaction Summary

The triggers are independent conditions, but they share a reset contract. The table below summarizes what each trigger does and when it fires.

| Trigger | Condition | Fires immediately? | Suppressed by idle? |
|---|---|---|---|
| Debounced timer | `DEBOUNCE_MS` since last keystroke | No — waits for debounce | Yes |
| Edit distance | Cumulative delta >= `EDIT_DISTANCE_THRESHOLD` | Yes | No (still fires) |
| Paste event | Any paste event | Yes | No (paste is explicit intent) |
| Explicit hotkey | User presses hotkey | Yes | No (wakes from idle) |
| Idle detection | No keystroke for `IDLE_TIMEOUT_MS` | n/a — this is a gate | n/a |

**Reset contract:** when any trigger fires, cancel the debounce timer and update the snapshot (which zeroes the edit distance counter). This prevents double-firing.

---

## Tuneable Constants

All thresholds in this system are guesses and need empirical tuning against real usage data. The right values depend on your users' typing speed, average input length, and how often false positives (unnecessary backend calls) are tolerable.

```python
# All values are starting guesses — tune against real data
DEBOUNCE_MS = 800           # time to wait after last keystroke before firing timer trigger
IDLE_TIMEOUT_MS = 5000      # time before system goes dormant
EDIT_DISTANCE_THRESHOLD = 20  # cumulative edit distance since last trigger before firing
```

---

## Additional Considerations

The following mechanisms are worth knowing about but were intentionally left out of the recommended set. They add complexity that is likely premature for the current stage, but could be revisited if the simpler system proves insufficient.

**Word boundary detection.** Only trigger when the cursor sits at a word boundary (after a space, punctuation, or newline). This eliminates mid-word noise almost entirely, but means suggestions are delayed until the user finishes a word. Worth considering if the edit distance threshold is producing too many false positives mid-word.

**Cursor position heuristic.** Distinguish between the user editing in the middle of existing text vs. appending at the end. Mid-document edits might not warrant suggestions at the same threshold as append-mode edits. Adds meaningful complexity to the trigger logic.

**Explicit hotkey (manual request).** Let the user ask for a suggestion on demand with a keybinding. This is low-effort to implement and gives you clean signal about when users actually want suggestions — useful for calibrating your automatic thresholds over time.
