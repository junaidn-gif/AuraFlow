import unittest
from auraflow.gestures import analyze,Pose
from auraflow.handsfree import HandsFree
from auraflow.demo import landmarks

class PauseClickTests(unittest.TestCase):
    def hold(self,r,poses,start=0):
        actions=[]
        for i in range(40): actions+=r.update(poses,start+i/30)
        return [a.name for a in actions]

    def test_right_thumb_never_toggles(self):
        for paused in (False,True):
            r=HandsFree(); r.paused=paused
            self.assertEqual(self.hold(r,[Pose('thumb_up',hand='Right')]),[])
            self.assertEqual(r.paused,paused)

    def test_unlabelled_thumb_cannot_toggle(self):
        self.assertEqual(self.hold(HandsFree(),[Pose('thumb_up')]),[])

    def test_left_thumb_must_be_only_hand(self):
        self.assertEqual(self.hold(HandsFree(),[Pose('thumb_up',hand='Left'),Pose('point',hand='Right')]),[])

    def test_thumb_geometry_and_closed_pinch_are_distinct(self):
        points=landmarks('thumb_up')
        self.assertEqual(analyze(points,hand='Left').kind,'thumb_up')
        # Keep the thumb pointing upward, but move the curled index close to it.
        # This used to satisfy thumbs-up before the pinch was considered.
        points[4]=(.39,.64)
        points[3]=(.35,.67)
        self.assertEqual(analyze(points,hand='Right').kind,'point')

    def test_click_stays_pointer_as_index_curls(self):
        r=HandsFree()
        self.hold(r,[analyze(landmarks('point',.7),hand='Right')])
        closed=landmarks('fist'); closed[4]=(closed[8][0]+.02,closed[8][1])
        p=analyze(closed,hand='Right')
        self.assertEqual(p.kind,'point')
        self.assertEqual(self.hold(r,[p],1.34),['click'])
        self.assertFalse(r.paused)
