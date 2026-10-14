# Source and dependency acknowledgements

AuraFlow is built from the user's supplied `volume_controller(1).py` concept and
palm-normalized geometry. The original code is included unchanged under
`reference/`. New code separates tracking, gestures, system adapters, and a Qt UI.

Runtime dependencies are downloaded from PyPI on the first launch and remain
under their respective licenses. If distributing an EXE, include applicable
upstream license notices, including Qt/PySide6's LGPL requirements.

- [MediaPipe](https://github.com/google-ai-edge/mediapipe) — hand tracking (Apache-2.0).
- [OpenCV](https://github.com/opencv/opencv) — camera frames (Apache-2.0).
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) — native UI;
  see its licensing options and obligations.
- [pycaw](https://github.com/AndreMiras/pycaw) — Windows audio (MIT).
- [screen_brightness_control](https://github.com/Crozzers/screen_brightness_control)
  — supported display brightness (MIT).
- [comtypes](https://github.com/enthought/comtypes) — Windows COM (MIT).
- [NumPy](https://numpy.org/), [JAX](https://github.com/jax-ml/jax),
  [SciPy](https://scipy.org/), and [Matplotlib](https://matplotlib.org/) are direct
  or transitive dependencies; see their distributions for notices.

## Bundled model

Google MediaPipe Hand Landmarker, float16, model version 1.

- [Official model overview](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)
- [Original model file](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task)
- SHA-256: `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`

The application verifies the model hash before opening the camera.

## Implementation references

- [MediaPipe Python Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [Pycaw examples](https://andremiras.github.io/pycaw/examples/index.html)
- [Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- [Windows INPUT structure](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-input)

The app's hand illustration and icons are code-drawn vectors. No third-party
photos, fonts, audio files, or generated bitmap assets are needed.
