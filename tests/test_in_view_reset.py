import unittest
from auraflow.handsfree import HandsFree
from auraflow.gestures import Pose

class InViewResetTests(unittest.TestCase):
    def setUp(self):
        self.r=HandsFree(); self.t=0

    def frames(self,kind,n=40,hands=('Right',),swipe=False):
        actions=[]
        for i in range(n):
            poses=[Pose(kind,.7,palm=(.2+i*.015 if swipe else .5,.5),hand=h) for h in hands]
            actions+=self.r.update(poses,self.t)
            self.t+=1/30
        return [a.name for a in actions]

    def test_multiple_swipes_without_missing_hand(self):
        self.assertEqual(self.frames('four',swipe=True),['app_next'])
        self.assertEqual(self.frames('fist'),[])
        self.assertEqual(self.frames('three',swipe=True),['tab_next'])
        self.assertEqual(self.frames('fist'),[])
        self.assertEqual(self.frames('four',swipe=True),['app_next'])

    def test_long_reset_fist_does_not_mute(self):
        self.frames('four',swipe=True)
        self.assertEqual(self.frames('fist',n=180),[])

    def test_brief_reset_not_enough(self):
        self.frames('four',swipe=True)
        self.assertEqual(self.frames('fist',n=3),[])
        self.assertEqual(self.frames('four',swipe=True),[])

    def test_flickering_fist_cannot_mute(self):
        self.frames('four',swipe=True); self.frames('fist')
        self.frames('neutral',n=1)
        self.assertEqual(self.frames('fist',n=60),[])

    def test_two_hand_reset_not_zoom_reset(self):
        self.assertEqual(self.frames('peace',hands=('Left','Right')),['screenshot'])
        self.assertEqual(self.frames('fist',hands=('Left','Right')),[])
        self.assertEqual(self.frames('palm',n=50,hands=('Left','Right')),['desktop'])

    def test_music_swipes_can_repeat_in_view(self):
        self.assertEqual(self.frames('palm',swipe=True),['next_track'])
        self.assertEqual(self.frames('fist'),[])
        self.assertEqual(self.frames('palm',swipe=True),['next_track'])

    def test_pause_resume_can_rearm_in_view(self):
        self.assertEqual(self.frames('thumb_up',hands=('Left',)),['toggle_pause'])
        self.assertEqual(self.frames('fist',hands=('Left',)),[])
        self.assertEqual(self.frames('thumb_up',hands=('Left',)),['toggle_pause'])
        self.assertFalse(self.r.paused)

    def test_gap_cannot_turn_reset_fist_into_command(self):
        self.frames('four',swipe=True); self.frames('fist')
        self.t+=1
        self.assertEqual(self.frames('fist'),[])
