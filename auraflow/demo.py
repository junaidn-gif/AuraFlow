"""Deterministic synthetic landmarks for the explicitly labelled demo."""
import math


CHOICES = {
    "Auto": ["Right pinch · volume", "Left pinch · brightness", "Fist · mute",
             "V sign · play / pause", "Open palm · next track",
             "Three fingers · next slide", "Point · mouse"],
    "Audio": ["Adjust volume", "Pinky lock", "Fist to mute"],
    "Display": ["Adjust brightness", "Pinky lock"],
    "Media": ["Play / pause", "Next track", "Previous track"],
    "Slides": ["Next slide", "Previous slide", "Blank screen"],
    "Pointer": ["Move pointer", "Pinch to click", "Two-finger scroll"],
}


def landmarks(kind="adjust", ratio=.65, dx=0.0, dy=0.0):
    pts = [(0.50, .87)] * 21
    bases = [(5, .36, .59), (9, .48, .56), (13, .59, .59), (17, .68, .65)]
    extended = {
        "adjust": (True, False, False, True),
        "point": (True, False, False, False),
        "middle_only": (False, True, False, False),
        "peace": (True, True, False, False),
        "three": (True, True, True, False),
        "palm": (True, True, True, True),
        "four": (True, True, True, True),
        "fist": (False, False, False, False),
        "thumb_up": (False, False, False, False),
        "neutral": (False, True, False, True),
    }[kind]
    for (mcp, x, y), out in zip(bases, extended):
        pts[mcp] = (x, y)
        pts[mcp + 1] = (x + .008, y - .135)
        pts[mcp + 2] = (x + .012, y - (.25 if out else .01))
        pts[mcp + 3] = (x + .016, y - (.34 if out else -.055))
    palm_px = math.hypot((pts[0][0] - pts[9][0]) * 640, (pts[0][1] - pts[9][1]) * 480)
    pts[4] = (pts[8][0] - ratio * palm_px / 640 * .8,
              pts[8][1] + ratio * palm_px / 480 * .6)
    if kind in ("fist", "three", "four", "middle_only"):
        pts[4] = (.46, .60)
    elif kind in ("palm", "peace", "neutral"):
        pts[4] = (.19, .48)
    if kind == "thumb_up":
        pts[4] = (.24, .25)
    pts[1] = (.40, .79)
    pts[2] = (.31, .69)
    pts[3] = ((pts[2][0] + pts[4][0]) / 2, (pts[2][1] + pts[4][1]) / 2)
    return [(x + dx, y + dy) for x, y in pts]


def sample(mode, choice, seconds):
    phase = seconds % 3.8
    ratio = .18 + .96 * (.5 + .5 * math.sin(seconds * .8))
    if choice == "Right pinch · volume":
        return landmarks("adjust", ratio)
    if choice == "Left pinch · brightness":
        return landmarks("adjust", ratio)
    if choice == "Fist · mute":
        return landmarks("neutral" if phase < .7 else "fist")
    if choice == "V sign · play / pause":
        return landmarks("neutral" if phase < .7 else "peace")
    if choice == "Open palm · next track":
        return landmarks("neutral") if phase < .7 or phase > 1.3 else landmarks("palm", dx=(phase - 1.0) * .8)
    if choice == "Three fingers · next slide":
        return landmarks("neutral") if phase < .7 or phase > 1.3 else landmarks("three", dx=(phase - 1.0) * .8)
    if choice == "Point · mouse":
        return landmarks("point", .65, dx=.14 * math.sin(seconds), dy=.07 * math.cos(seconds))
    if choice.startswith("Adjust"):
        return landmarks("adjust", ratio)
    if choice == "Pinky lock":
        return landmarks("point", ratio)
    if choice in ("Fist to mute", "Play / pause", "Blank screen"):
        return landmarks("neutral" if phase < .7 else ("peace" if mode == "Media" else "fist"))
    if "track" in choice or "slide" in choice:
        if phase < .7 or phase > 1.3:
            return landmarks("neutral")
        direction = 1 if choice.startswith("Next") else -1
        return landmarks("palm", dx=direction * (phase - 1.0) * .8)
    if choice == "Pinch to click":
        return landmarks("point", .65 if phase < 1.8 else .10)
    if choice == "Two-finger scroll":
        return landmarks("peace", dy=.10 * math.sin(seconds * 2))
    return landmarks("point", .65, dx=.14 * math.sin(seconds), dy=.07 * math.cos(seconds))


def hand_for(choice):
    return "Left" if choice == "Left pinch · brightness" else "Right"
