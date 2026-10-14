"""Tab gesture regressions: patient holds, repeats, and shortcut directions."""
import unittest
from unittest.mock import Mock
from auraflow.handsfree import HandsFree
from auraflow.gestures import Pose,Action
from auraflow.system import SystemController


def frame(x=.5,y=.5,kind='three'):
    return Pose(kind,palm=(x,y),hand='Right')


def swipe(router,start,direction=1,y_delta=0):
    actions=[]
    for i in range(21):
        actions+=router.update([frame(.5+direction*i*.012,.5+i*y_delta)],start+i/30)
    return actions


class TabSwipeTests(unittest.TestCase):
    def test_swipe_still_works_after_waiting_three_seconds(self):
        r=HandsFree()
        for i in range(90): self.assertEqual(r.update([frame()],i/30),[])
        self.assertEqual([a.name for a in swipe(r,3)],['tab_next'])

    def test_left_swipe_is_previous(self):
        self.assertEqual([a.name for a in swipe(HandsFree(),0,-1)],['tab_previous'])

    def test_stationary_jitter_is_not_a_tab_change(self):
        r=HandsFree(); actions=[]
        for i in range(120): actions+=r.update([frame(.5+(.02 if i%2 else -.02))],i/30)
        self.assertEqual(actions,[])

    def test_diagonal_swipe_is_rejected(self):
        self.assertEqual(swipe(HandsFree(),0,y_delta=.013),[])

    def test_flicker_cannot_repeat_then_real_release_can(self):
        r=HandsFree(); self.assertEqual(len(swipe(r,0)),1)
        # One missing detection must not arm another shortcut.
        r.update([], .71)
        self.assertEqual(swipe(r,.74,-1),[])
        for i in range(10): r.update([],1.44+i/30)
        self.assertEqual([a.name for a in swipe(r,1.79,-1)],['tab_previous'])

    def test_shortcuts_match_both_directions(self):
        controller=object.__new__(SystemController); controller.input=Mock()
        controller.perform(Action('tab_next')); controller.input.chord.assert_called_with(0x11,0x09)
        controller.perform(Action('tab_previous')); controller.input.chord.assert_called_with(0x11,0x10,0x09)
