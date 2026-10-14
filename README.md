# AuraFlow 2.7.1 — Hands-free command center

One workspace, no mode selection, no presentation feature. Camera opens automatically
and controls become available after settling and hand verification. The app has no camera consent
dialog. Windows privacy settings can still block camera access; permit desktop camera
access in Windows if necessary. Camera video stays on your computer.

## Install
Extract the complete ZIP into a NEW folder. Install 64-bit Python 3.12 alongside
3.13 if necessary, then double-click Start_AuraFlow.bat. The existing pinned
MediaPipe dependency still requires Python 3.11/3.12. First launch installs dependencies.
The title must read AuraFlow 2.7.1. Try_Demo.bat is an optional simulation with no webcam
or system actions. Build_EXE.bat optionally builds a Windows executable locally.

## Enroll your hands first
The local hand geometry filter starts enabled. Click My hands, then Enroll / replace
right hand. Show only that hand, palm toward the camera with all fingers spread,
and hold steady for about four seconds (60 accepted frames). Repeat for the left
hand to use brightness, pause/resume and two-hand gestures. The preview stays live;
controls are paused throughout enrollment. Correct swapped labels in Settings first.

Profiles contain normalized 3D joint-length ratios, not photos or video, and are
stored in hand_profile.json inside the local application data folder shown by Qt
for AuraFlow. They persist across app launches. My hands lets you replace either
profile or forget both. Canceling enrollment preserves existing profiles.

Show each enrolled open palm for at least 0.6 seconds to unlock gestures. After
verification, palm geometry and position continuity keep that hand active through
pinches, fists and other poses; curled fingers are not compared to the open-palm
finger profile. Existing 2.7 profiles remain compatible; no re-enrollment is needed.
All visible hands must be verified. Unmatched, ambiguous or missing data blocks the
entire frame and clears pending controls. Tracking gaps, position jumps, or an
incompatible palm require open-palm verification again. This gate also
applies to pause/resume gestures and Alt+F4. Mouse Settings remain available.

Settings offers Strict, Balanced and Tolerant matching, plus an explicit filter
disable switch. Start with Balanced; re-enroll in good lighting if your own hand
is often rejected. Tolerant matching increases the chance of accepting other hands.
This is an experimental geometry filter, not reliable personal identification:
similar proportions or a close hand substitution may pass. Occlusion can interrupt tracking.
No measured biometric accuracy or guarantee of owner-only control is claimed.
The demo bypasses verification and never saves profiles or sends system commands.

## Cleaner dashboard and tab switching
The main window shows the camera, current action, volume/brightness bars, and a
visible browser-tab hint. The full guide is under View all gestures; it pauses
controls while open and restores the previous pause state when closed.

To switch tabs, focus your browser, raise index + middle + ring fingers on one
hand, and swipe horizontally as seen in the camera preview. Right selects the
next tab; left selects the previous tab. Briefly make a loose fist in view, then open your hand for the next swipe. You can hold the pose before swiping; there is no initial 0.8-second deadline.
The gesture uses Ctrl+Tab / Ctrl+Shift+Tab and changes tabs in the focused app,
not between separate application windows. A shortcut-sent message confirms
Windows accepted the shortcut, not that an unsupported app changed its tab.

## Switch desktop apps
Raise all four fingers and tuck your thumb across your palm, then swipe as shown
in the preview: right sends Alt+Tab; left sends Alt+Shift+Tab. Briefly make a loose fist in view before repeating. Each swipe sends and releases one shortcut; it does
not keep the app switcher open. Windows determines its usual recent-app order.

This is separate from three-finger browser-tab swipes and five-finger music swipes.
A partly folded thumb is neutral, and two four-finger hands do not trigger Show Desktop.
Only a left-hand thumbs-up held alone controls pause/resume. Live tracking can still misclassify a pose, so
check the gesture feedback while learning it.

## Gesture guide
Close the focused app: show only your middle finger on either hand, tuck your thumb
and other fingers, and hold steady for 1.2 seconds. Keep the other hand out of view.
Progress appears in the camera preview. Moving or changing pose cancels the countdown.
This sends Alt+F4 once to the focused window; it does not force-quit or dismiss save
prompts. Focus the intended window first (the desktop may show its shutdown dialog).
Briefly make a fist and reopen to reset without leaving the camera view.
Try the Close app demo to practice without closing anything.

Keep your palm facing the camera and your whole hand visible.

| Gesture | Action |
|---|---|
| Right index only; move whole hand | Move cursor using the index knuckle |
| Right thumb/index pinch after opening | Left click; pointer freezes during pinch |
| Right thumb/index pinch with pinky extended, middle/ring folded | Volume |
| Left thumb/index pinch with pinky extended, middle/ring folded | Brightness |
| Fold pinky | Stop changing volume/brightness |
| Right fist, hold | Mute/unmute |
| Left fist, hold | Play/pause media |
| One five-finger open-palm horizontal swipe | Previous/next track |
| One V sign, move vertically | Scroll |
| Four fingers extended, thumb tucked, swipe horizontally | Switch desktop apps (Alt+Tab / Alt+Shift+Tab) |
| Index+middle+ring extended, swipe horizontally | Previous/next browser tab |
| Pinch both hands, then spread apart / bring together | Zoom in / out |
| Both fists, hold 0.9 seconds | Reset zoom |
| Two V signs, hold 1.2 seconds | Windows screenshot shortcut |
| Two open palms, hold 1.2 seconds | Show/hide desktop |
| LEFT thumbs-up alone, hold 0.9 seconds | Pause/resume all actions |
| Middle finger only, thumb tucked, one steady hand for 1.2 seconds | Close focused window (Alt+F4) |

After a confirmed hold action, briefly close your visible hands into loose fists, then open them for the next gesture. Two-hand gestures
suppress single-hand commands. Do not keep another hand in frame while using single-hand
controls. Zoom uses Ctrl+plus/minus and reset uses Ctrl+0: support depends on the
focused app (for example a browser). Tab switching uses Ctrl+Tab / Ctrl+Shift+Tab.
Screenshots use Win+PrintScreen; Windows controls their destination (normally Pictures/Screenshots).
Show desktop uses Win+D. No files are deleted and no messages are sent.

## Hand labels and settings
Inference receives the original camera frame. Preview mirroring is applied separately,
so it does not flip anatomical labels. Raise your RIGHT hand and check the live label.
If your camera driver already mirrors frames, enable Settings > Swap anatomical left/right
labels. Settings also includes camera index, display index, pinch range and smoothing.
Controls pause while Settings is open. Saving settings reconnects the camera automatically.

## Pause and recovery
Hold LEFT thumbs-up alone to pause/resume; Ctrl+Alt+P pauses globally. Escape pauses while this app
has focus. Moving your physical mouse into the top-left corner also pauses controls.
Move it away before resuming. Tracking stalls pause controls; after tracking returns,
left thumbs-up alone resumes. Reconnect camera is available if another app or unplugging interrupts it.

## Verification limits
Automated gestures, Qt startup/lifecycle and rendered UI were checked in Linux.
Live Windows camera labels, gestures and hardware effects still need testing on your laptop.

## Pinch-click correction in 2.3
A closed thumb/index pinch takes priority over fist or thumbs-up recognition.
The index may curl without changing a click into a pause. Thumbs-up recognition
also requires the thumb to be clearly separated from the index and extended upward.
Right-hand and unlabelled thumbs-up detections cannot pause or resume.

## Repeat gestures without leaving the camera (2.4)
After an app/tab/music swipe or a confirmed hold action, close your visible hand(s)
into a loose fist for about 0.25 seconds. Once feedback says Ready, open your hand
and make the next gesture. You can keep your hands in frame the whole time.
The reset fist is consumed: holding it cannot mute, play/pause, or reset zoom.
Brief fist flickers are ignored. Opening must also be stable for about 0.15 seconds.
To intentionally mute after a reset, first open your hand, then make a fresh fist.
Continuous movement, level adjustments, zoom and scrolling do not require this
reset between updates. Clicking still uses opening/reclosing the pinch.

## Mini camera window (2.5)
Click Mini camera on the main dashboard. AuraFlow hides the full dashboard and opens
a small always-on-top window showing the live camera, tracked hand landmarks,
detected hand, current action and live/paused state. Gesture controls continue normally.
Drag or resize the standard window; AuraFlow remembers its last position and size.
Click Dashboard or close the mini window to return to the full interface. Closing the
full dashboard exits AuraFlow and also closes the mini view. The mini view uses the
same already-open camera and does not start a second camera connection.
