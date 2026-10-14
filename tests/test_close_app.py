import unittest
from unittest.mock import Mock

from auraflow.demo import landmarks
from auraflow.gestures import Action, Pose, analyze
from auraflow.handsfree import HandsFree
from auraflow.system import SystemController


def feed(router, poses, start=0, frames=61):
    return [a.name for i in range(frames)
            for a in router.update(poses, start+i/30)]


class CloseAppTests(unittest.TestCase):
    def test_geometry_is_exclusive(self):
        for hand in ('Left', 'Right'):
            self.assertEqual(analyze(landmarks('middle_only'), hand=hand).kind, 'middle_only')
        for kind in ('point', 'adjust', 'peace', 'three', 'four', 'palm', 'fist', 'thumb_up', 'neutral'):
            self.assertNotEqual(analyze(landmarks(kind)).kind, 'middle_only')
        self.assertNotEqual(analyze(landmarks('point', .1)).kind, 'middle_only')

    def test_hold_once_on_either_hand(self):
        for hand in ('Left', 'Right'):
            r = HandsFree()
            p = [Pose('middle_only', hand=hand)]
            self.assertEqual(feed(r, p, frames=36), [])
            self.assertGreater(r.progress, .9)
            self.assertEqual(feed(r, p, start=1.2), ['close_app'])

    def test_paused_and_two_hands_cannot_close(self):
        r = HandsFree(); r.paused = True
        self.assertEqual(feed(r, [Pose('middle_only')]), [])
        for second in ('middle_only', 'point', 'fist', 'peace'):
            self.assertEqual(feed(HandsFree(), [Pose('middle_only', hand='Left'),
                                               Pose(second, hand='Right')]), [])

    def test_tracking_gap_restarts_hold(self):
        r = HandsFree(); p = [Pose('middle_only')]
        self.assertEqual(feed(r, p, frames=30), [])
        self.assertEqual(feed(r, p, start=2, frames=30), [])

    def test_pose_change_restarts_hold(self):
        r = HandsFree(); p = [Pose('middle_only')]
        self.assertEqual(feed(r, p, frames=30), [])
        r.update([Pose('neutral')], 1)
        self.assertEqual(feed(r, p, start=1.1, frames=30), [])

    def test_motion_restarts_hold(self):
        r = HandsFree()
        self.assertEqual(feed(r, [Pose('middle_only')], frames=30), [])
        self.assertEqual(feed(r, [Pose('middle_only', palm=(.6, .5))], start=1, frames=30), [])

    def test_in_view_reset_allows_next_close(self):
        r = HandsFree(); p = [Pose('middle_only')]
        self.assertEqual(feed(r, p), ['close_app'])
        self.assertEqual(feed(r, [Pose('fist')], start=2.1, frames=12), [])
        self.assertEqual(feed(r, [Pose('neutral')], start=2.5, frames=8), [])
        self.assertEqual(feed(r, p, start=2.8), ['close_app'])

    def test_shortcut_is_alt_f4(self):
        c = object.__new__(SystemController); c.input = Mock()
        c.perform(Action('close_app'))
        c.input.chord.assert_called_once_with(0x12, 0x73)


if __name__ == '__main__':
    unittest.main()
