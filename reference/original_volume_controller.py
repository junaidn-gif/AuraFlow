"""
AuraSound AI • Precision Gesture Audio Studio
=============================================
A professional, presentable desktop application for hand-gesture audio control.

Precision Control & Pinky Lock Criteria:
- Pinky OUT (Extended): ACTIVE MODE. Moving Thumb & Index dynamically scales volume (0% to 100%).
- Pinky FOLDED (Curled): LOCKED MODE. Volume is completely frozen at the exact current level!
  Moving Thumb, Index, or taking your hand away will NOT change the volume.
- Touching Pinch = 0% Volume: Bringing Thumb and Index together smoothly reduces volume to 0%,
  never muting.
- Open Hand / Neutral Hand: Explicitly classified as IDLE / NO GESTURE and completely ignored.
- Scale-Invariant Tracking: Pinch distance is normalized to palm anatomy (Wrist-to-Knuckle scale),
  guaranteeing exact volume mapping regardless of camera distance.
- Adaptive Deadband Filtering: Eliminates micro-jitter when holding fingers still while
  providing instant zero-lag tracking during fast motions.

Presentation & UI:
- Modern Obsidian / Frosted Slate Studio Dashboard with high-DPI typography.
- Real-time Audio Device display and decibel (dB) readout.
- Dynamic Animated Audio Equalizer visualizer responding to master volume.
- Circular glowing HUD volume gauge with dynamic multi-color gradient.
- Anti-aliased AR hand skeleton with active pinch laser beam and measurement reticle.
- Clear status badges explaining Pinky Lock/Unlock state and gesture recognition.
"""

import cv2
import mediapipe as mp
import math
import numpy as np
import time
import os
import urllib.request
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ==============================================================================
# 1. Hand Geometry & Equalizer State
# ==============================================================================
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),    # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17)                                # Palm Base
]

# Equalizer state (14 frequency bands)
eq_bands = [0.2] * 14


def get_dist(p1, p2):
    """Calculate Euclidean distance between two points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def analyze_hand_pose(pts, enable_fist_mute=False):
    """
    Robust anatomical classification with Pinky Lock/Unlock Criteria:
      1. DELIBERATE VOLUME POSE (Middle & Ring Curled, Thumb Active):
         - Pinky is OUT (Extended): -> 'PINCH_ACTIVE' (Unlocks volume adjustment).
         - Pinky is FOLDED (Curled): -> 'PINCH_LOCKED' (Freezes / locks volume).
      2. OPEN PALM / NEUTRAL HAND:
         Middle & Ring fingers extended -> 'OPEN_HAND' (Completely ignored).
      3. TRUE CLOSED FIST (Mute Gesture):
         Only if enabled AND all 5 fingers including Thumb are tightly tucked into a ball.
      4. RELAXED / OTHER:
         Ignored (volume locked).
    """
    wrist = pts[0]
    middle_mcp = pts[9]

    # Anatomical palm reference: Wrist (0) to Middle Knuckle (9)
    palm_len = get_dist(wrist, middle_mcp)
    if palm_len < 15:
        return 'UNKNOWN', False, 0.0, 0.0, False

    def check_finger_curled(tip_idx, pip_idx, mcp_idx):
        tip = pts[tip_idx]
        pip = pts[pip_idx]
        mcp = pts[mcp_idx]
        d_tip_wrist = get_dist(tip, wrist)
        d_pip_wrist = get_dist(pip, wrist)
        d_tip_mcp = get_dist(tip, mcp)
        d_pip_mcp = get_dist(pip, mcp)
        # Curled when tip is closer to wrist than PIP or folded to MCP
        return (d_tip_wrist < d_pip_wrist * 1.05) or (d_tip_mcp < d_pip_mcp * 0.95)

    def check_finger_extended(tip_idx, pip_idx, mcp_idx):
        tip = pts[tip_idx]
        pip = pts[pip_idx]
        mcp = pts[mcp_idx]
        d_tip_wrist = get_dist(tip, wrist)
        d_pip_wrist = get_dist(pip, wrist)
        d_tip_mcp = get_dist(tip, mcp)
        d_pip_mcp = get_dist(pip, mcp)
        return (d_tip_wrist > d_pip_wrist * 1.12) and (d_tip_mcp > d_pip_mcp * 1.15)

    # Check finger states
    middle_curled = check_finger_curled(12, 10, 9)
    ring_curled = check_finger_curled(16, 14, 13)
    pinky_curled = check_finger_curled(20, 18, 17)

    middle_ext = check_finger_extended(12, 10, 9)
    ring_ext = check_finger_extended(16, 14, 13)
    pinky_is_out = check_finger_extended(20, 18, 17)

    thumb_tip = pts[4]
    index_tip = pts[8]
    index_mcp = pts[5]
    index_pip = pts[6]

    pinch_dist = get_dist(thumb_tip, index_tip)
    pinch_ratio = pinch_dist / palm_len

    # Thumb is extended from palm base
    thumb_dist_wrist = get_dist(thumb_tip, wrist)
    thumb_is_extended = thumb_dist_wrist > (palm_len * 0.55)

    # =========================================================================
    # 1. DELIBERATE VOLUME CONTROL WITH PINKY CRITERIA (Top Priority!)
    # =========================================================================
    # When other fingers (middle & ring) are curled, and thumb is active:
    if middle_curled and ring_curled and thumb_is_extended:
        if 0.10 <= pinch_ratio <= 1.50:
            if pinky_is_out:
                # Pinky is OUT -> Actively adjusting volume!
                return 'PINCH_ACTIVE', True, pinch_dist, pinch_ratio, True
            else:
                # Pinky is FOLDED -> Locked! Holds current volume steady!
                return 'PINCH_LOCKED', False, pinch_dist, pinch_ratio, False

    # =========================================================================
    # 2. OPEN PALM / NEUTRAL HAND (Explicitly Ignored)
    # =========================================================================
    if middle_ext and ring_ext:
        return 'OPEN_HAND', False, pinch_dist, pinch_ratio, pinky_is_out

    # =========================================================================
    # 3. TRUE CLOSED FIST (Mute Gesture - Optional)
    # =========================================================================
    if enable_fist_mute:
        index_curled_deep = (get_dist(index_tip, wrist) < get_dist(index_pip, wrist) * 0.95) and \
                            (get_dist(index_tip, index_mcp) < palm_len * 0.45)
        thumb_tucked = (not thumb_is_extended) or (get_dist(thumb_tip, index_pip) < palm_len * 0.35)

        if index_curled_deep and middle_curled and ring_curled and pinky_curled and thumb_tucked:
            return 'FIST', False, pinch_dist, pinch_ratio, False

    # =========================================================================
    # 4. ANY OTHER RELAXED / AMBIGUOUS POSE (Ignored)
    # =========================================================================
    return 'NEUTRAL', False, pinch_dist, pinch_ratio, pinky_is_out


# ==============================================================================
# 2. Modern Presentable UI Rendering Engine
# ==============================================================================
def draw_rounded_rect(img, pt1, pt2, color, radius=12, thickness=-1):
    """Draw a rounded rectangle with clean anti-aliasing."""
    x1, y1 = int(pt1[0]), int(pt1[1])
    x2, y2 = int(pt2[0]), int(pt2[1])
    radius = min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2)

    if thickness == -1:
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
        cv2.circle(img, (x1 + radius, y1 + radius), radius, color, -1, cv2.LINE_AA)
        cv2.circle(img, (x2 - radius, y1 + radius), radius, color, -1, cv2.LINE_AA)
        cv2.circle(img, (x1 + radius, y2 - radius), radius, color, -1, cv2.LINE_AA)
        cv2.circle(img, (x2 - radius, y2 - radius), radius, color, -1, cv2.LINE_AA)
    else:
        cv2.line(img, (x1 + radius, y1), (x2 - radius, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + radius, y2), (x2 - radius, y2), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + radius), (x1, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + radius), (x2, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)


def render_dashboard(canvas, volume_pct, is_adjusting, is_muted, fps, handedness, gesture_name, dev_name, anim_phase, min_vol_db, max_vol_db, enable_fist_mute, pinky_is_out):
    """
    Renders the modern left studio dock:
    Includes branding, output device card, circular HUD gauge, animated equalizer, and status.
    """
    dock_w = 340
    h_canvas, _, _ = canvas.shape

    # 1. Dock Background: Dark Obsidian Slate with subtle border
    canvas[:, :dock_w] = (20, 22, 28)
    cv2.line(canvas, (dock_w, 0), (dock_w, h_canvas), (38, 42, 54), 2)

    # 2. Header Branding
    cv2.circle(canvas, (42, 45), 10, (0, 230, 160), -1, cv2.LINE_AA)
    cv2.circle(canvas, (42, 45), 14, (0, 230, 160), 1, cv2.LINE_AA)
    cv2.putText(canvas, "AURASOUND", (65, 52), cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, "AI SPATIAL GESTURE AUDIO", (66, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 130, 150), 1, cv2.LINE_AA)

    # 3. Audio Device Card
    draw_rounded_rect(canvas, (25, 95), (dock_w - 25, 160), (28, 32, 40), radius=10, thickness=-1)
    draw_rounded_rect(canvas, (25, 95), (dock_w - 25, 160), (45, 50, 65), radius=10, thickness=1)

    cv2.circle(canvas, (45, 118), 5, (0, 255, 120), -1, cv2.LINE_AA)
    cv2.putText(canvas, "ACTIVE OUTPUT", (60, 121), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 150, 170), 1, cv2.LINE_AA)
    cv2.putText(canvas, dev_name, (43, 145), cv2.FONT_HERSHEY_DUPLEX, 0.48, (230, 235, 245), 1, cv2.LINE_AA)

    # 4. Central Circular / Arc HUD Volume Meter
    center_x, center_y = dock_w // 2, 280
    gauge_radius = 80

    # Background Ring
    cv2.circle(canvas, (center_x, center_y), gauge_radius, (35, 38, 48), 10, cv2.LINE_AA)

    # Dynamic Gauge Color
    if is_muted:
        accent_color = (60, 60, 240)    # Crimson Red
    elif is_adjusting:
        accent_color = (0, 230, 140)    # Neon Emerald (Unlocked)
    elif gesture_name == 'PINCH_LOCKED':
        accent_color = (255, 160, 20)   # Warm Amber (Locked)
    else:
        accent_color = (140, 150, 170)  # Slate Gray (Idle)

    # Draw Active Arc (from -220 deg to +40 deg = 260 deg total sweep)
    sweep_angle = int((volume_pct / 100.0) * 260)
    if sweep_angle > 0 and not is_muted:
        cv2.ellipse(canvas, (center_x, center_y), (gauge_radius, gauge_radius),
                    140, 0, sweep_angle, accent_color, 10, cv2.LINE_AA)

    # Center Volume Percentage Text
    vol_str = f"{int(volume_pct)}%" if not is_muted else "MUTE"
    font_scale = 1.3 if not is_muted else 0.95
    t_size = cv2.getTextSize(vol_str, cv2.FONT_HERSHEY_DUPLEX, font_scale, 2)[0]
    cv2.putText(canvas, vol_str, (center_x - t_size[0] // 2, center_y + 12),
                cv2.FONT_HERSHEY_DUPLEX, font_scale, (255, 255, 255) if not is_muted else (80, 80, 255), 2, cv2.LINE_AA)

    # Decibel (dB) readout
    db_val = min_vol_db + (volume_pct / 100.0) * (max_vol_db - min_vol_db)
    db_str = f"{db_val:.1f} dB" if not is_muted else "MUTED"
    db_size = cv2.getTextSize(db_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0]
    cv2.putText(canvas, db_str, (center_x - db_size[0] // 2, center_y + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 160, 175), 1, cv2.LINE_AA)

    # 5. Live Equalizer / Audio Waveform Visualizer
    eq_y = 390
    draw_rounded_rect(canvas, (25, eq_y), (dock_w - 25, eq_y + 90), (26, 30, 38), radius=10, thickness=-1)
    draw_rounded_rect(canvas, (25, eq_y), (dock_w - 25, eq_y + 90), (45, 50, 65), radius=10, thickness=1)

    cv2.putText(canvas, "REAL-TIME SPECTRUM", (38, eq_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130, 140, 160), 1, cv2.LINE_AA)

    num_bars = 14
    bar_w = 12
    gap = 6
    start_bx = 38
    base_by = eq_y + 75

    for i in range(num_bars):
        if is_muted:
            target_h = 4
        else:
            freq = (i + 1) * 0.7
            wave = (math.sin(anim_phase * 2.5 + freq) + 1.0) * 0.5
            target_h = int(6 + (volume_pct / 100.0) * wave * 42)

        eq_bands[i] = eq_bands[i] * 0.7 + target_h * 0.3
        bh = int(eq_bands[i])

        bx = start_bx + i * (bar_w + gap)
        by = base_by - bh

        if i < 5:
            b_col = (255, 190, 0)
        elif i < 10:
            b_col = (0, 230, 130)
        else:
            b_col = (30, 160, 255)

        if is_muted:
            b_col = (70, 70, 90)

        cv2.rectangle(canvas, (bx, by), (bx + bar_w, base_by), b_col, -1)

    # 6. Gesture & Tracking Status Card
    st_y = 500
    draw_rounded_rect(canvas, (25, st_y), (dock_w - 25, st_y + 115), (26, 30, 38), radius=10, thickness=-1)
    draw_rounded_rect(canvas, (25, st_y), (dock_w - 25, st_y + 115), (45, 50, 65), radius=10, thickness=1)

    cv2.putText(canvas, "GESTURE ENGINE", (38, st_y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130, 140, 160), 1, cv2.LINE_AA)

    # Lock / Unlock Status Pill
    if is_adjusting:
        pill_text = "● UNLOCKED (PINKY OUT)"
        pill_bg = (0, 90, 45)
        pill_fg = (0, 255, 140)
    elif gesture_name == 'PINCH_LOCKED':
        pill_text = "🔒 LOCKED (PINKY FOLDED)"
        pill_bg = (90, 55, 15)
        pill_fg = (255, 180, 50)
    elif gesture_name == 'OPEN_HAND':
        pill_text = "OPEN PALM (IGNORED)"
        pill_bg = (40, 45, 55)
        pill_fg = (180, 185, 200)
    elif gesture_name == 'FIST':
        pill_text = "HOLD TO MUTE"
        pill_bg = (30, 30, 100)
        pill_fg = (80, 120, 255)
    else:
        pill_text = "IDLE (NO GESTURE)"
        pill_bg = (35, 38, 48)
        pill_fg = (140, 150, 165)

    draw_rounded_rect(canvas, (38, st_y + 36), (dock_w - 38, st_y + 68), pill_bg, radius=6, thickness=-1)
    cv2.putText(canvas, pill_text, (50, st_y + 57), cv2.FONT_HERSHEY_DUPLEX, 0.40, pill_fg, 1, cv2.LINE_AA)

    pinky_desc = "Pinky: OUT" if pinky_is_out else "Pinky: FOLDED"
    cv2.putText(canvas, f"{handedness}  •  {pinky_desc}", (38, st_y + 92), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (170, 180, 195), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"{int(fps)} FPS", (dock_w - 85, st_y + 92), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 230, 140), 1, cv2.LINE_AA)

    # 7. Keyboard Shortcuts Footer
    foot_y = h_canvas - 45
    cv2.putText(canvas, "Pinky OUT: Adjust Vol  |  Pinky FOLDED: Lock Vol", (25, foot_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 220, 150), 1, cv2.LINE_AA)
    cv2.putText(canvas, "[Q] Quit  |  [M] Mute  |  [C] Calibrate", (25, foot_y + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (110, 120, 135), 1, cv2.LINE_AA)


def draw_hud_badges(view_frame, gesture_name, is_adjusting, is_muted, pinch_ratio):
    """Draw sleek floating glassmorphic badge over the video feed."""
    h, w, _ = view_frame.shape

    if is_muted:
        badge_text = "AUDIO MUTED (Press 'M' to Unmute)"
        badge_fg = (80, 80, 255)
        badge_bg = (20, 20, 35)
        border_col = (50, 50, 180)
    elif is_adjusting:
        badge_text = f"🟢 UNLOCKED: PINKY OUT • ADJUSTING VOLUME [{pinch_ratio:.2f}x]"
        badge_fg = (0, 255, 140)
        badge_bg = (18, 30, 25)
        border_col = (0, 200, 100)
    elif gesture_name == 'PINCH_LOCKED':
        badge_text = "🔒 LOCKED: PINKY FOLDED • VOLUME FIXED (Extend pinky to adjust)"
        badge_fg = (255, 185, 60)
        badge_bg = (30, 24, 18)
        border_col = (180, 120, 30)
    elif gesture_name == 'OPEN_HAND':
        badge_text = "NEUTRAL HAND (No Gesture • Ignored)"
        badge_fg = (180, 190, 205)
        badge_bg = (22, 25, 32)
        border_col = (60, 65, 80)
    elif gesture_name == 'FIST':
        badge_text = "CLOSED FIST DETECTED"
        badge_fg = (70, 160, 255)
        badge_bg = (30, 25, 20)
        border_col = (70, 140, 220)
    else:
        badge_text = "IDLE • NO DELIBERATE GESTURE"
        badge_fg = (140, 150, 165)
        badge_bg = (20, 22, 28)
        border_col = (45, 50, 60)

    t_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_DUPLEX, 0.48, 1)[0]
    bx1 = (w - t_size[0]) // 2 - 20
    by1 = 20
    bx2 = bx1 + t_size[0] + 40
    by2 = by1 + 42

    overlay = view_frame.copy()
    draw_rounded_rect(overlay, (bx1, by1), (bx2, by2), badge_bg, radius=10, thickness=-1)
    cv2.addWeighted(overlay, 0.85, view_frame, 0.15, 0, view_frame)
    draw_rounded_rect(view_frame, (bx1, by1), (bx2, by2), border_col, radius=10, thickness=1)

    cv2.putText(view_frame, badge_text, (bx1 + 20, by1 + 27),
                cv2.FONT_HERSHEY_DUPLEX, 0.48, badge_fg, 1, cv2.LINE_AA)


# ==============================================================================
# 3. Application Entry Point
# ==============================================================================
def main():
    # Audio Setup
    devices = AudioUtilities.GetSpeakers()
    if hasattr(devices, 'EndpointVolume'):
        volume_ctrl = devices.EndpointVolume
    else:
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))

    vol_range = volume_ctrl.GetVolumeRange()
    min_vol_db, max_vol_db = vol_range[0], vol_range[1]

    device_name = "System Audio"
    try:
        dev_str = str(devices)
        if "AudioDevice:" in dev_str:
            device_name = dev_str.replace("AudioDevice:", "").strip()
        if len(device_name) > 28:
            device_name = device_name[:25] + "..."
    except Exception:
        device_name = "Default Speakers"

    try:
        current_vol_scalar = volume_ctrl.GetMasterVolumeLevelScalar()
        current_mute = bool(volume_ctrl.GetMute())
    except Exception:
        current_vol_scalar = 0.5
        current_mute = False

    # MediaPipe Detector
    use_legacy = hasattr(mp, 'solutions') and hasattr(mp.solutions, 'hands')

    if use_legacy:
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        detector = None
    else:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        model_path = os.path.join(os.path.dirname(__file__), 'hand_landmarker.task')
        if not os.path.exists(model_path):
            print("Downloading hand_landmarker.task model...")
            urllib.request.urlretrieve(
                'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
                model_path
            )

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        detector = vision.HandLandmarker.create_from_options(options)
        hands = None

    # Camera Capture
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    cv2.namedWindow("AuraSound • Precision Gesture Studio", cv2.WINDOW_NORMAL)

    # Calibration & Engine State
    min_pinch_ratio = 0.20
    max_pinch_ratio = 1.15
    confirmation_frames = 2
    pinch_confirm_counter = 0
    is_gesture_engaged = False

    # Fist Mute Setting (Disabled by default)
    enable_fist_mute = False
    fist_start_time = None
    fist_hold_duration = 0.8
    fist_triggered = False

    smoothed_vol = current_vol_scalar * 100.0
    last_applied_vol = int(round(smoothed_vol))
    deadzone_pct = 0.8

    prev_time = time.time()
    last_timestamp_ms = 0
    anim_phase = 0.0

    CANVAS_W = 1280
    CANVAS_H = 720
    DOCK_W = 340
    VIEW_W = CANVAS_W - DOCK_W
    VIEW_H = CANVAS_H

    print("\n" + "=" * 60)
    print("  AURASOUND AI • PRECISION GESTURE AUDIO STUDIO")
    print("=" * 60)
    print("  Pinky Lock Criteria:")
    print("  - Pinky OUT: UNLOCKED -> Move Index & Thumb to adjust volume.")
    print("  - Pinky FOLDED: LOCKED -> Volume is completely frozen!")
    print("  - Neutral / Open Hand is completely ignored.")
    print("  - Press 'M': Toggle Mute")
    print("  - Press 'C': Calibrate pinch reach")
    print("  - Press 'Q': Quit")
    print("=" * 60 + "\n")

    while True:
        success, raw_frame = cap.read()
        if not success:
            print("Camera stream disconnected.")
            break

        raw_frame = cv2.flip(raw_frame, 1)
        view_frame = cv2.resize(raw_frame, (VIEW_W, VIEW_H), interpolation=cv2.INTER_LINEAR)
        rgb_frame = cv2.cvtColor(view_frame, cv2.COLOR_BGR2RGB)

        pts = None
        handedness_label = "None"

        # Landmark Detection
        if use_legacy:
            result = hands.process(rgb_frame)
            if result.multi_hand_landmarks:
                hand_landmarks = result.multi_hand_landmarks[0]
                pts = [(int(lm.x * VIEW_W), int(lm.y * VIEW_H)) for lm in hand_landmarks.landmark]
                if result.multi_handedness:
                    handedness_label = result.multi_handedness[0].classification[0].label
        else:
            frame_timestamp_ms = int(time.time() * 1000)
            if frame_timestamp_ms <= last_timestamp_ms:
                frame_timestamp_ms = last_timestamp_ms + 1
            last_timestamp_ms = frame_timestamp_ms

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            result = detector.detect_for_video(mp_image, frame_timestamp_ms)

            if result.hand_landmarks and len(result.hand_landmarks) > 0:
                hand_landmarks = result.hand_landmarks[0]
                pts = [(int(lm.x * VIEW_W), int(lm.y * VIEW_H)) for lm in hand_landmarks]
                if result.handedness and len(result.handedness) > 0:
                    handedness_label = result.handedness[0][0].category_name

        # Gesture Analysis
        gesture_name = 'IDLE'
        is_pinch_candidate = False
        pinch_dist = 0.0
        pinch_ratio = 0.0
        pinky_is_out = False

        if pts and len(pts) >= 21:
            gesture_name, is_pinch_candidate, pinch_dist, pinch_ratio, pinky_is_out = analyze_hand_pose(
                pts, enable_fist_mute=enable_fist_mute
            )

            # Skeletal overlay
            for start_idx, end_idx in HAND_CONNECTIONS:
                cv2.line(view_frame, pts[start_idx], pts[end_idx], (55, 60, 75), 1, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(view_frame, pt, 2, (150, 160, 180), -1, cv2.LINE_AA)

            thumb_tip = pts[4]
            index_tip = pts[8]
            pinky_tip = pts[20]
            wrist = pts[0]

            # Visual indicator on Pinky: Green ring when OUT (unlocked), Amber when FOLDED (locked)
            pinky_ring_col = (0, 255, 140) if pinky_is_out else (240, 160, 40)
            cv2.circle(view_frame, pinky_tip, 6, pinky_ring_col, 2, cv2.LINE_AA)

            # Multi-frame Confirmation for Pinch Engagement (only if Pinky is OUT)
            if is_pinch_candidate and pinky_is_out:
                pinch_confirm_counter += 1
                if pinch_confirm_counter >= confirmation_frames:
                    is_gesture_engaged = True
            else:
                pinch_confirm_counter = 0
                is_gesture_engaged = False

            # Volume Adjustment (ONLY when Pinky is OUT and gesture is engaged)
            if is_gesture_engaged:
                target_vol = float(np.interp(pinch_ratio, [min_pinch_ratio, max_pinch_ratio], [0.0, 100.0]))
                target_vol = float(np.clip(target_vol, 0.0, 100.0))

                mid_x = (thumb_tip[0] + index_tip[0]) // 2
                mid_y = (thumb_tip[1] + index_tip[1]) // 2

                if target_vol < 35:
                    beam_col = (255, 200, 0)
                elif target_vol < 75:
                    beam_col = (0, 240, 130)
                else:
                    beam_col = (40, 130, 255)

                cv2.line(view_frame, thumb_tip, index_tip, beam_col, 3, cv2.LINE_AA)
                cv2.circle(view_frame, thumb_tip, 7, beam_col, -1, cv2.LINE_AA)
                cv2.circle(view_frame, index_tip, 7, beam_col, -1, cv2.LINE_AA)
                cv2.circle(view_frame, (mid_x, mid_y), 5, (255, 255, 255), -1, cv2.LINE_AA)

                tag_text = f"{int(target_vol)}%"
                cv2.putText(view_frame, tag_text, (mid_x + 12, mid_y + 5),
                            cv2.FONT_HERSHEY_DUPLEX, 0.5, beam_col, 1, cv2.LINE_AA)

                if not current_mute:
                    vol_delta = abs(target_vol - smoothed_vol)
                    if vol_delta > deadzone_pct:
                        alpha = 0.18 + 0.52 * min(1.0, vol_delta / 30.0)
                        smoothed_vol = (alpha * target_vol) + ((1.0 - alpha) * smoothed_vol)

                        target_int = int(round(smoothed_vol))
                        if target_int != last_applied_vol:
                            scalar_val = float(np.clip(smoothed_vol / 100.0, 0.0, 1.0))
                            try:
                                volume_ctrl.SetMasterVolumeLevelScalar(scalar_val, None)
                                last_applied_vol = target_int
                            except Exception:
                                pass
            elif gesture_name == 'PINCH_LOCKED':
                # Pinky is FOLDED: Draw subtle dashed/thin lock line and lock icon
                mid_x = (thumb_tip[0] + index_tip[0]) // 2
                mid_y = (thumb_tip[1] + index_tip[1]) // 2
                cv2.line(view_frame, thumb_tip, index_tip, (100, 120, 140), 1, cv2.LINE_AA)
                cv2.circle(view_frame, thumb_tip, 5, (100, 120, 140), -1, cv2.LINE_AA)
                cv2.circle(view_frame, index_tip, 5, (100, 120, 140), -1, cv2.LINE_AA)
                cv2.putText(view_frame, "LOCKED", (mid_x + 10, mid_y + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 160, 180), 1, cv2.LINE_AA)
        else:
            pinch_confirm_counter = 0
            is_gesture_engaged = False
            fist_start_time = None
            fist_triggered = False

        # Live Volume Query
        try:
            current_vol_scalar = volume_ctrl.GetMasterVolumeLevelScalar()
            actual_sys_vol = int(round(current_vol_scalar * 100.0))
            current_mute = bool(volume_ctrl.GetMute())
        except Exception:
            actual_sys_vol = int(round(smoothed_vol))

        # FPS & Animations
        curr_time = time.time()
        dt = curr_time - prev_time
        fps = 1.0 / dt if dt > 0 else 0
        prev_time = curr_time
        anim_phase += dt * 3.0

        # Badges on Viewport
        draw_hud_badges(
            view_frame=view_frame,
            gesture_name=gesture_name,
            is_adjusting=is_gesture_engaged,
            is_muted=current_mute,
            pinch_ratio=pinch_ratio
        )

        # Final Composite Canvas
        final_canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        final_canvas[:, DOCK_W:] = view_frame

        render_dashboard(
            canvas=final_canvas,
            volume_pct=actual_sys_vol,
            is_adjusting=is_gesture_engaged,
            is_muted=current_mute,
            fps=fps,
            handedness=handedness_label,
            gesture_name=gesture_name,
            dev_name=device_name,
            anim_phase=anim_phase,
            min_vol_db=min_vol_db,
            max_vol_db=max_vol_db,
            enable_fist_mute=enable_fist_mute,
            pinky_is_out=pinky_is_out
        )

        cv2.imshow("AuraSound • Precision Gesture Studio", final_canvas)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            try:
                current_mute = not volume_ctrl.GetMute()
                volume_ctrl.SetMute(int(current_mute), None)
                print(f"[AUDIO] Mute manually toggled: {'MUTED' if current_mute else 'UNMUTED'}")
            except Exception as e:
                print("Mute toggle failed:", e)
        elif key == ord('c'):
            if pts and len(pts) >= 21 and pinch_ratio > 0.05:
                if pinch_ratio < 0.4:
                    min_pinch_ratio = max(0.12, pinch_ratio)
                    print(f"[CALIBRATION] Calibrated Minimum Pinch Reach to: {min_pinch_ratio:.2f}")
                else:
                    max_pinch_ratio = min(1.6, pinch_ratio)
                    print(f"[CALIBRATION] Calibrated Maximum Pinch Reach to: {max_pinch_ratio:.2f}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()