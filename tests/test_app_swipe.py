import math
import unittest
from unittest.mock import Mock
from auraflow.gestures import analyze, Action
from auraflow.demo import landmarks
from auraflow.handsfree import HandsFree
from auraflow.system import SystemController


def run(kind, direction=1, router=None, start=0):
    router=router or HandsFree(); actions=[]
    for i in range(25):
        p=analyze(landmarks(kind,dx=direction*i*.015),hand='Right')
        actions+=router.update([p],start+i/30)
    return [a.name for a in actions]

class AppSwipeTests(unittest.TestCase):
    def test_both_directions(self):
        self.assertEqual(run('four'),['app_next'])
        self.assertEqual(run('four',-1),['app_previous'])

    def test_existing_swipes_remain_distinct(self):
        self.assertEqual(run('three'),['tab_next'])
        self.assertEqual(run('palm'),['next_track'])

    def test_four_fingers_cannot_pause_or_click_while_held(self):
        r=HandsFree(); result=[]
        for i in range(90): result+=r.update([analyze(landmarks('four'))],i/30)
        self.assertEqual(result,[]); self.assertFalse(r.paused)

    def test_paused_apps_do_nothing(self):
        r=HandsFree(); r.paused=True
        self.assertEqual(run('four',router=r),[])
        self.assertTrue(r.paused)

    def test_partly_folded_thumb_is_neutral(self):
        points=landmarks('palm')
        length=math.hypot((points[0][0]-points[9][0])*640,(points[0][1]-points[9][1])*480)
        points[4]=(points[9][0]-.67*length/640,points[9][1])
        self.assertEqual(analyze(points).kind,'neutral')
        self.assertEqual(analyze(landmarks('four')).kind,'four')
        self.assertEqual(analyze(landmarks('palm')).kind,'palm')

    def test_release_required(self):
        r=HandsFree(); self.assertEqual(run('four',router=r),['app_next'])
        self.assertEqual(run('four',router=r,start=.85),[])
        for i in range(10): r.update([],1.7+i/30)
        self.assertEqual(run('four',-1,r,2.05),['app_previous'])

    def test_two_four_finger_hands_do_not_show_desktop(self):
        r=HandsFree(); result=[]
        for i in range(60): result+=r.update([analyze(landmarks('four',dx=-.15)),analyze(landmarks('four',dx=.15))],i/30)
        self.assertEqual(result,[])

    def test_alt_shortcuts(self):
        c=object.__new__(SystemController); c.input=Mock()
        c.perform(Action('app_next')); c.input.chord.assert_called_with(0x12,0x09)
        c.perform(Action('app_previous')); c.input.chord.assert_called_with(0x12,0x10,0x09)
