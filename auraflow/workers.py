"""Camera inference and slow device operations stay outside the UI thread."""
from pathlib import Path
from dataclasses import replace
from collections import deque
import hashlib
import sys
import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from .gestures import analyze, Action
from .handsfree import hand_label
from .identity import features

MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def model_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "models" / "hand_landmarker.task"


class CameraWorker(QThread):
    ready = Signal()
    error = Signal(str)

    def __init__(self, camera=0, mirror=True, swap=False):
        super().__init__()
        self.camera, self.mirror, self.swap = camera, mirror, swap
        self.lock = threading.Lock()
        self.latest = None

    def take_frame(self):
        # A single-slot mailbox prevents stale frames piling up in Qt's event queue.
        with self.lock:
            frame, self.latest = self.latest, None
        return frame

    def run(self):
        cap, detector = None, None
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            path = model_path()
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
                raise RuntimeError("The hand model is missing or damaged. Extract the complete app ZIP again.")
            if self.isInterruptionRequested():
                return
            options = vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=.65, min_hand_presence_confidence=.65,
                min_tracking_confidence=.65)
            detector = vision.HandLandmarker.create_from_options(options)
            cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(self.camera)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.camera)
            if not cap.isOpened():
                raise RuntimeError("Cannot open the camera. Close other camera apps, check Windows camera permissions, or select another camera in Settings.")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.ready.emit()
            last_stamp, previous, fps, failures = 0, time.monotonic(), 0.0, 0
            while not self.isInterruptionRequested():
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures >= 5:
                        raise RuntimeError("Camera disconnected. Reconnect it and start the camera again.")
                    self.msleep(40)
                    continue
                failures = 0
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                stamp = max(last_stamp + 1, int(time.monotonic() * 1000))
                last_stamp = stamp
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                height, width = rgb.shape[:2]
                hands, poses = [], []
                for landmarks, categories, world in zip(result.hand_landmarks, result.handedness, result.hand_world_landmarks):
                    # Inference always uses the original camera image. Mirroring is
                    # only a display transform and never changes anatomical labels.
                    hand = hand_label(categories[0].category_name, self.swap)
                    points = [(1-lm.x if self.mirror else lm.x, lm.y) for lm in landmarks]
                    hands.append(points)
                    pose = analyze(points, width, height, hand)
                    geometry = features([(p.x,p.y,p.z) for p in world]) if categories[0].score >= .85 else ()
                    poses.append(replace(pose, geometry=geometry) if pose else None)
                if self.mirror:
                    rgb = cv2.flip(rgb, 1)
                image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
                now = time.monotonic()
                fps = .85 * fps + .15 / max(.001, now - previous)
                previous = now
                packet = (image, hands, poses, fps, now)
                with self.lock:
                    self.latest = packet
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if cap is not None:
                cap.release()
            if detector is not None:
                detector.close()


class ControlWorker(QThread):
    result = Signal(str, object, int)
    error = Signal(str, str, int)

    def __init__(self):
        super().__init__()
        self.condition = threading.Condition()
        self.queue = deque()
        self.stopping = False
        self.epoch = 0

    def invalidate(self):
        with self.condition:
            self.epoch += 1
            self.queue.clear()
        return self.epoch

    def submit(self, action, display=0):
        with self.condition:
            if action.name in ("volume", "brightness", "move", "read_audio", "read_display"):
                self.queue = deque(item for item in self.queue if item[0].name != action.name)
            if len(self.queue) < 12:
                self.queue.append((action, display, self.epoch))
            self.condition.notify()

    def stop(self):
        with self.condition:
            self.stopping = True
            self.queue.clear()
            self.condition.notify()

    def run(self):
        com = None
        try:
            import comtypes
            com = comtypes
            com.CoInitialize()
            from .system import SystemController
            controller = SystemController()
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopping or bool(self.queue))
                    if self.stopping:
                        return
                    action, display, epoch = self.queue.popleft()
                if epoch != self.epoch:
                    continue
                try:
                    data = controller.perform(action, display)
                    self.result.emit(action.name, data, epoch)
                except Exception as exc:
                    self.error.emit(action.name, str(exc), epoch)
        except Exception as exc:
            self.error.emit("startup", str(exc), self.epoch)
        finally:
            if com is not None:
                com.CoUninitialize()
