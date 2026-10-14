"""Camera-independent hand geometry and gesture state machine.

The palm-normalized pinch and pinky lock come from the supplied controller.
Only this module decides when a gesture becomes a command. It has no OS effects.
"""
from dataclasses import dataclass
from collections import deque
import math

CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6),
               (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
               (9, 13), (13, 14), (14, 15), (15, 16), (13, 17),
               (17, 18), (18, 19), (19, 20), (0, 17)]
MODES = ("Auto", "Audio", "Display", "Media", "Slides", "Pointer")


def clamp(value, lower=0.0, upper=1.0):
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class Pose:
    kind: str
    ratio: float = 0.0
    pointer: tuple = (0.5, 0.5)
    palm: tuple = (0.5, 0.5)
    hand: str = ""
    geometry: tuple = ()


@dataclass(frozen=True)
class Action:
    name: str
    value: object = None


def analyze(points, width=640, height=480, hand=""):
    """Accept 21 normalized (x,y) coordinates; correct for frame aspect ratio."""
    if len(points) != 21 or any(not math.isfinite(v) for p in points for v in p[:2]):
        return None
    pts = [(p[0] * width, p[1] * height) for p in points]
    distance = lambda a, b: math.dist(pts[a], pts[b])
    palm_len = distance(0, 9)
    if palm_len < 25:
        return None

    def state(mcp):
        pip, tip = mcp + 1, mcp + 3
        if (distance(tip, 0) > distance(pip, 0) * 1.12 and
                distance(tip, mcp) > distance(pip, mcp) * 1.15):
            return "out"
        if (distance(tip, 0) < distance(pip, 0) * 1.05 or
                distance(tip, mcp) < distance(pip, mcp) * .95):
            return "in"
        return "unknown"

    index, middle, ring, pinky = [state(m) for m in (5, 9, 13, 17)]
    ratio = distance(4, 8) / palm_len
    thumb_distance = distance(4, 9) / palm_len
    thumb_tucked = thumb_distance < .55
    # A closed pointer pinch remains a pointer even if the index curls. Give
    # it priority over fist/ thumbs-up so clicking cannot become a hold action.
    if middle == ring == pinky == "in" and ratio < .38:
        kind = "point"
    elif (all(s == "in" for s in (index, middle, ring, pinky))
          and not thumb_tucked and ratio > .65
          and pts[4][1] < pts[3][1] < pts[2][1]
          and pts[2][1] - pts[4][1] > palm_len * .30):
        kind = "thumb_up"
    elif all(s == "in" for s in (index, middle, ring, pinky)) and thumb_tucked:
        kind = "fist"
    elif all(s == "out" for s in (index, middle, ring, pinky)):
        # Explicitly separate desktop-app swipes from open-palm media swipes.
        # A partly folded thumb is neutral instead of guessing either action.
        kind = "four" if thumb_tucked else "palm" if thumb_distance > .80 else "neutral"
    elif index == middle == ring == "out" and pinky == "in":
        kind = "three"
    elif index == middle == "out" and ring == pinky == "in":
        kind = "peace"
    elif middle == "out" and index == ring == pinky == "in" and thumb_tucked:
        kind = "middle_only"
    elif middle == ring == "in" and pinky == "out":
        kind = "adjust"
    elif middle == ring == pinky == "in" and (index == "out" or ratio < .4):
        kind = "point"
    else:
        kind = "neutral"
    palm = tuple(sum(points[i][axis] for i in (0, 5, 9, 13, 17)) / 5 for axis in (0, 1))
    # The index knuckle is much steadier than the fingertip while the thumb
    # closes for a click. Moving the whole hand still moves the pointer.
    return Pose(kind, ratio, tuple(points[5][:2]), palm, hand)


class GestureEngine:
    def __init__(self, mode="Audio", low=.18, high=1.15, smooth=.10, hold=.70):
        self.mode, self.low, self.high = mode, low, high
        self.smooth, self.hold = smooth, hold
        self.fist_mute = True
        self.value = 50.0
        self.auto_values = {"Audio": 50.0, "Display": 60.0}
        self.reset()

    def reset(self):
        self.kind = None
        self.since = None
        self.last_time = None
        self.last_emit = -math.inf
        self.latched = False
        self.release_since = None
        self.history = deque()
        self.cursor = None
        self.scroll_y = None
        self.click_down = False
        self.click_since = None
        self.click_ready = False
        self.progress = 0.0
        self.status = "Waiting for your hand"

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Unknown control mode")
        self.mode = mode
        self.reset()

    def _once(self, name, now, duration):
        self.progress = clamp((now - self.since) / duration)
        if self.progress >= 1 and not self.latched:
            self.latched = True
            return [Action(name)]
        return []

    def update(self, pose, now):
        # A tracking gap interrupts confirmation; stale frames cannot finish a hold.
        if self.last_time is not None and now - self.last_time > .35:
            self.reset()
        dt = .033 if self.last_time is None else clamp(now - self.last_time, .001, .1)
        self.last_time = now
        kind = pose.kind if pose else "missing"
        if kind != self.kind:
            self.kind, self.since = kind, now
            self.history.clear()
            self.scroll_y = None
            self.cursor = None
            self.click_since = None
            self.click_ready = False
        self.progress = 0.0
        self.status = {"missing": "Waiting for your hand", "neutral": "Ready · relaxed hand",
                       "thumb_up": "Thumb up · hold to pause", "four": "Four fingers · thumb tucked", "palm": "Open palm", "fist": "Hold your fist", "peace": "Hold the V sign",
                       "three": "Three fingers · presentation", "middle_only": "Middle finger only",
                       "point": "Pinky folded · level locked", "adjust": "Pinky out · adjusting"}[kind]
        # Every discrete action needs a deliberate neutral release before it can repeat.
        if kind in ("missing", "neutral", "point", "adjust"):
            if self.release_since is None:
                self.release_since = now
            if now - self.release_since >= .25:
                self.latched = False
        else:
            self.release_since = None
        if pose is None:
            return []

        if self.mode == "Auto":
            # The hand selects continuous controls; pose selects discrete tools.
            if kind == "adjust":
                selected = "Display" if pose.hand.lower().startswith("left") else "Audio"
                self.status = ("Left hand · brightness" if selected == "Display" else
                               "Right hand · volume")
                self.progress = clamp((now - self.since) / .18)
                if self.progress < 1:
                    return []
                fraction = clamp((pose.ratio - self.low) / max(.25, self.high - self.low))
                target = (10 + fraction * 90) if selected == "Display" else fraction * 100
                alpha = 1 - math.exp(-dt / max(.03, self.smooth))
                current = self.auto_values[selected]
                current += (target - current) * alpha
                if abs(target - current) < 1:
                    current = target
                self.auto_values[selected] = current
                period = .18 if selected == "Display" else .055
                if now - self.last_emit >= period:
                    self.last_emit = now
                    return [Action("brightness" if selected == "Display" else "volume", round(current))]
                return []
            if kind == "fist" and self.fist_mute:
                self.status = "Fist · hold to mute"
                return self._once("mute", now, self.hold)
            if kind in ("palm", "three"):
                self.status = ("Open palm · swipe for tracks" if kind == "palm" else
                               "Three fingers · swipe for slides")
                self.history.append((now, *pose.palm))
                while self.history and now - self.history[0][0] > .60:
                    self.history.popleft()
                if len(self.history) > 2 and not self.latched:
                    t0, x0, y0 = self.history[0]
                    dx, dy = pose.palm[0] - x0, pose.palm[1] - y0
                    if .12 <= now - t0 <= .60 and abs(dx) > .22 and abs(dy) < .14:
                        self.latched = True
                        if kind == "palm":
                            return [Action("next_track" if dx > 0 else "previous_track")]
                        return [Action("next_slide" if dx > 0 else "previous_slide")]
                if kind == "three":
                    self.status = "Three fingers · swipe for slides or hold to blank"
                    return self._once("blank", now, self.hold + .2)
                return []
            if kind == "peace":
                self.status = "V sign · hold for playback or move vertically to scroll"
                self.history.append((now, *pose.palm))
                while self.history and now - self.history[0][0] > .60:
                    self.history.popleft()
                if len(self.history) > 2:
                    _, x0, y0 = self.history[0]
                    dx, dy = pose.palm[0] - x0, pose.palm[1] - y0
                    if abs(dy) > .10 and abs(dx) < .14 and now - self.last_emit > .15:
                        self.history.clear()
                        self.history.append((now, *pose.palm))
                        self.last_emit = now
                        self.since = now
                        return [Action("scroll", -1 if dy > 0 else 1)]
                return self._once("play_pause", now, self.hold)
            # Pointing routes directly into the existing pointer behavior below.

        if self.mode in ("Audio", "Display"):
            if kind == "adjust":
                self.progress = clamp((now - self.since) / .18)
                if self.progress < 1:
                    self.status = "Hold to unlock"
                    return []
                fraction = clamp((pose.ratio - self.low) / max(.25, self.high - self.low))
                target = fraction * 100 if self.mode == "Audio" else 10 + fraction * 90
                alpha = 1 - math.exp(-dt / max(.03, self.smooth))
                self.value += (target - self.value) * alpha
                # Endpoints settle exactly at 0/100 without an endless filter tail.
                if abs(target - self.value) < 1:
                    self.value = target
                period = .055 if self.mode == "Audio" else .18
                if now - self.last_emit >= period:
                    self.last_emit = now
                    return [Action("volume" if self.mode == "Audio" else "brightness", round(self.value))]
            elif kind == "fist" and self.mode == "Audio" and self.fist_mute:
                return self._once("mute", now, self.hold)
            return []

        if self.mode in ("Media", "Slides"):
            if kind == "peace" and self.mode == "Media":
                return self._once("play_pause", now, self.hold)
            if kind == "fist" and self.mode == "Slides":
                return self._once("blank", now, self.hold)
            if kind == "palm":
                self.status = "Swipe across · release between swipes"
                self.history.append((now, *pose.palm))
                while self.history and now - self.history[0][0] > .60:
                    self.history.popleft()
                if len(self.history) > 2 and not self.latched:
                    t0, x0, y0 = self.history[0]
                    dx, dy = pose.palm[0] - x0, pose.palm[1] - y0
                    if .12 <= now - t0 <= .60 and abs(dx) > .22 and abs(dy) < .14:
                        self.latched = True
                        return [Action(("next_track" if dx > 0 else "previous_track")
                                       if self.mode == "Media" else
                                       ("next_slide" if dx > 0 else "previous_slide"))]
            return []

        if self.mode in ("Pointer", "Auto"):
            if kind == "point":
                # Open pinch must be observed before a click: entering with closed
                # fingers, or losing the hand mid-click, cannot create a click.
                arm_threshold = max(.38, self.low + .20)
                click_threshold = min(.32, max(.24, self.low + .10))
                if pose.ratio > arm_threshold:
                    self.click_ready, self.click_down = True, False
                    self.click_since = None
                elif pose.ratio < click_threshold:
                    self.status = "Pinch held · click"
                    if not self.click_ready or self.click_down:
                        return []
                    if self.click_since is None:
                        self.click_since = now
                    self.progress = clamp((now - self.click_since) / .18)
                    if self.progress >= 1:
                        self.click_down = True
                        return [Action("click")]
                    return []
                else:
                    # Freeze through the approach zone. Closing the thumb can
                    # slightly pull the index finger and should not drag the cursor.
                    self.status = "Pinch starting · pointer frozen"
                    self.click_since = None
                    return []
                self.click_since = None
                self.status = "Point to move · pinch to click"
                # Map the comfortable central camera region to the primary screen.
                target = (clamp((pose.pointer[0] - .18) / .64, .005, .995),
                          clamp((pose.pointer[1] - .15) / .65, .005, .995))
                if self.cursor is None:
                    self.cursor = target
                else:
                    alpha = 1 - math.exp(-dt / max(.03, self.smooth))
                    self.cursor = tuple(a + (b - a) * alpha for a, b in zip(self.cursor, target))
                if now - self.since >= .18:
                    return [Action("move", self.cursor)]
            elif kind == "peace":
                self.status = "Two fingers · move up or down to scroll"
                y = pose.pointer[1]
                if self.scroll_y is None:
                    self.scroll_y = y
                delta = self.scroll_y - y
                if abs(delta) > .055 and now - self.last_emit > .15:
                    self.scroll_y, self.last_emit = y, now
                    return [Action("scroll", 1 if delta > 0 else -1)]
            return []
        return []
