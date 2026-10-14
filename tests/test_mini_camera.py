import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from auraflow.app import MainWindow
from auraflow.demo import landmarks
from auraflow.gestures import Pose

APP=QApplication.instance() or QApplication([])

class MiniCameraTests(unittest.TestCase):
    def setUp(self):
        self.window=MainWindow(demo=True); self.window.timer.stop(); self.window.poll.stop()
        self.window.show(); APP.processEvents()

    def tearDown(self):
        self.window.closing=True
        if self.window.mini: self.window.mini.close()
        self.window.close(); APP.processEvents()

    def test_open_hides_dashboard_and_is_always_on_top(self):
        self.window.open_mini(); APP.processEvents()
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.mini.isVisible())
        self.assertTrue(self.window.mini.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_preview_and_feedback_are_mirrored(self):
        image=QImage(16,12,QImage.Format.Format_RGB32)
        self.window.vision.image=image
        self.window.vision.hands=[landmarks('three')]
        self.window.hands.setText('Right hand')
        self.window.feedback.setText('Next tab')
        self.window.state.setText('LIVE')
        self.window.open_mini()
        self.assertEqual(self.window.mini.vision.image.size(),image.size())
        self.assertEqual(self.window.mini.vision.hands,self.window.vision.hands)
        self.assertEqual(self.window.mini.feedback.text(),'Next tab')
        self.assertEqual(self.window.mini.live.text(),'LIVE')

    def test_restore_button_path_returns_dashboard(self):
        self.window.open_mini(); self.window.restore_dashboard(); APP.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.mini.isVisible())

    def test_closing_mini_restores_dashboard(self):
        self.window.open_mini(); self.window.mini.close(); APP.processEvents()
        self.assertTrue(self.window.isVisible())

    def test_main_close_also_hides_mini(self):
        self.window.open_mini(); self.window.closing=True; self.window.close(); APP.processEvents()
        self.assertFalse(self.window.mini.isVisible())

    def test_close_gesture_demo_only_acknowledges(self):
        self.window.router.paused=False
        for i in range(50):
            self.window.process([Pose('middle_only', hand='Right')], i/30)
        self.assertIn('Demo · Close request', self.window.action_message)
        self.assertTrue(self.window.isVisible())
        self.assertIsNone(self.window.worker)

    def test_unknown_hand_blocks_close_and_clears_queued_actions(self):
        self.window.demo=False
        self.window.verification_enabled=True
        self.window.identity.profiles={}
        worker=Mock(); self.window.worker=worker
        try:
            for i in range(60):
                self.window.process([Pose('middle_only',hand='Right')],i/30)
            worker.submit.assert_not_called()
            self.assertTrue(worker.invalidate.called)
            self.assertEqual(self.window.state.text(),'LOCKED')
        finally:
            self.window.worker=None
            self.window.demo=True

    def test_enrollment_buttons_and_cancel(self):
        self.window.demo=False; self.window.camera_live=True
        observed=[]
        def interact():
            dialog=APP.activeModalWidget()
            for btn in dialog.findChildren(QPushButton):
                if btn.text()=='Enroll / replace right hand': btn.click()
            observed.append(self.window.identity.pending)
            dialog.reject()
        QTimer.singleShot(0,interact)
        next(b for b in self.window.findChildren(QPushButton) if b.text()=='My hands').click()
        self.assertEqual(observed,['Right'])
        self.assertIsNone(self.window.identity.pending)
        self.window.demo=True
