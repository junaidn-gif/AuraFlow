# AuraFlow 2.7.1 verification — October 6, 2026

98 automated tests passed. Six new regression tests cover curled-finger changes
after open-palm verification, brightness/volume and two-hand zoom through the gate,
blocking closed-pose initial verification, invalid or changed palms, and tracking
gaps/position jumps. This fixes full-finger profile checks blocking non-palm poses.
Existing profiles remain compatible. Live webcam testing is still required.

Hand-filter tests cover normalized 3D geometry,
enrollment persistence/cancel/interruption, invalid profiles, consecutive matching,
tracking gaps, rejection of an unmatched second hand, two enrolled hands and forgetting.
Qt tests verify enrollment button wiring, cancel behavior, and blocked Alt+F4 dispatch
with pending-command invalidation. Synthetic comparisons test logic, not biometric
accuracy. Real-person false-accept and false-reject rates have not been measured.

Existing close-app tests cover exclusive middle-finger
geometry, 1.2-second confirmation, single triggering, either hand, paused/two-hand
suppression, movement/pose/tracking interruption, in-view reset, and mocked Alt+F4.
A Qt integration test confirms demo closing only displays an acknowledgement.
Five mini-camera tests cover hiding the dashboard,
always-on-top behavior, immediate preview/landmark/status synchronization,
dashboard restoration, mini-window close and full-app close. Existing gesture,
repeat-reset, system-shortcut and audio tests continue to pass.

Python compilation and Qt offscreen tests passed. Live Windows Alt+F4 behavior,
webcam recognition, and always-on-top behavior remain unverified on the laptop.
