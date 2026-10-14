import json
import math
import tempfile
import unittest
from pathlib import Path

from auraflow.demo import landmarks
from auraflow.gestures import Pose
from auraflow.identity import HandIdentity, distance, features
from auraflow.handsfree import HandsFree


POINTS=[(x*.1,y*.1,.003*(i%3)) for i,(x,y) in enumerate(landmarks('palm'))]
VECTOR=features(POINTS)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'hand_profile.json'
        self.gate=HandIdentity(self.path)
        self.pose=Pose('palm',hand='Right',geometry=VECTOR)

    def tearDown(self):
        self.temp.cleanup()

    def test_feature_translation_rotation_scale_invariance(self):
        transformed=[(2*y+1,-2*x+4,2*z+3) for x,y,z in POINTS]
        self.assertLess(distance(VECTOR,features(transformed)),1e-12)

    def test_invalid_geometry_rejected(self):
        self.assertEqual(features([]),())
        self.assertEqual(features([(0,0,0)]*21),())
        self.assertEqual(features([(math.nan,0,0)]*21),())

    def test_enrollment_and_reload(self):
        self.gate.begin('Right')
        for i in range(59): self.assertFalse(self.gate.enroll([self.pose],i*.06))
        self.assertTrue(self.gate.enroll([self.pose],59*.06))
        self.assertIn('Right',HandIdentity(self.path).profiles)
        self.assertIsNone(self.gate.pending)

    def test_enrollment_rejects_other_hand_and_multiple_hands(self):
        self.gate.begin('Left')
        for i in range(70): self.gate.enroll([self.pose],i*.06)
        self.assertFalse(self.gate.samples)
        self.gate.begin('Right')
        self.gate.enroll([self.pose],5)
        self.gate.enroll([self.pose,self.pose],5.06)
        self.assertFalse(self.gate.samples)
        self.assertFalse(self.path.exists())

    def test_interrupted_enrollment_starts_again(self):
        self.gate.begin('Right')
        for i in range(20): self.gate.enroll([self.pose],i*.06)
        self.gate.enroll([self.pose],3)
        self.assertEqual(len(self.gate.samples),1)
        self.gate.cancel()
        self.assertFalse(self.path.exists())

    def test_empty_and_corrupt_profiles_fail_closed(self):
        self.assertFalse(self.gate.verify([self.pose],0))
        self.path.write_text('{invalid',encoding='utf-8')
        gate=HandIdentity(self.path)
        self.assertTrue(gate.error)
        self.assertFalse(gate.verify([self.pose],0))
        self.path.write_text(json.dumps({'version':1,'hands':{'Right':[float('nan')]*22}}))
        self.assertFalse(HandIdentity(self.path).verify([self.pose],0))

    def test_match_requires_consecutive_frames_and_rechecks(self):
        self.gate.save({'Right':VECTOR})
        for i in range(6): self.assertFalse(self.gate.verify([self.pose],i*.1))
        self.assertTrue(self.gate.verify([self.pose],.61))
        unknown=Pose('palm',hand='Right',geometry=tuple(v*1.5 for v in VECTOR))
        self.assertFalse(self.gate.verify([unknown],.7))
        self.assertFalse(self.gate.verify([self.pose],.8))

    def test_gap_and_missing_hand_require_reverification(self):
        self.gate.save({'Right':VECTOR})
        for i in range(10): self.gate.verify([self.pose],i*.1)
        self.assertFalse(self.gate.verify([self.pose],2))
        self.gate.verify([],2.1)
        self.assertFalse(self.gate.verify([self.pose],2.2))

    def test_unknown_second_hand_blocks_whole_frame(self):
        self.gate.save({'Right':VECTOR})
        for i in range(10): self.gate.verify([self.pose],i*.1)
        left=Pose('palm',hand='Left',geometry=VECTOR)
        self.assertFalse(self.gate.verify([self.pose,left],1))
        self.assertFalse(self.gate.tracks)

    def test_two_enrolled_hands_work(self):
        self.gate.save({'Right':VECTOR,'Left':VECTOR})
        poses=[self.pose,Pose('palm',hand='Left',geometry=VECTOR)]
        for i in range(10): result=self.gate.verify(poses,i*.1)
        self.assertTrue(result)
        self.assertFalse(self.gate.verify([self.pose,self.pose],1))

    def test_forget_persists_and_blocks(self):
        self.gate.save({'Right':VECTOR})
        self.gate.save({})
        self.assertFalse(HandIdentity(self.path).verify([self.pose],0))

    def unlock(self, hand='Right'):
        self.gate.save({hand:VECTOR})
        for i in range(10):
            result=self.gate.verify([Pose('palm',hand=hand,geometry=VECTOR)],i*.1)
        self.assertTrue(result)

    def test_curled_finger_estimates_keep_verified_hand(self):
        changed=VECTOR[:7]+tuple(v*.55 for v in VECTOR[7:])
        self.assertGreater(distance(VECTOR,changed),self.gate.threshold)
        self.unlock()
        for i,kind in enumerate(('adjust','point','fist','thumb_up','middle_only','three','four','peace')):
            self.assertTrue(self.gate.verify([Pose(kind,hand='Right',geometry=changed)],1+i*.1))

    def test_brightness_and_volume_after_open_palm_verification(self):
        changed=VECTOR[:7]+tuple(v*.65 for v in VECTOR[7:])
        for hand,expected in (('Left','brightness'),('Right','volume')):
            self.unlock(hand)
            router=HandsFree(); actions=[]
            for i in range(30):
                pose=Pose('adjust',ratio=.7,hand=hand,geometry=changed)
                now=1+i/30
                if self.gate.verify([pose],now): actions.extend(router.update([pose],now))
                else: router.reset()
            self.assertTrue(actions)
            self.assertEqual({a.name for a in actions},{expected})

    def test_closed_pose_cannot_unlock_even_with_matching_geometry(self):
        self.gate.save({'Right':VECTOR})
        for i in range(30):
            self.assertFalse(self.gate.verify([Pose('adjust',hand='Right',geometry=VECTOR)],i*.1))

    def test_changed_palm_or_invalid_geometry_revokes_verification(self):
        for shape in (tuple(v*1.6 for v in VECTOR[:7])+VECTOR[7:], ()):
            self.unlock()
            self.assertFalse(self.gate.verify([Pose('adjust',hand='Right',geometry=shape)],1))
            self.assertFalse(self.gate.verify([Pose('adjust',hand='Right',geometry=VECTOR)],1.1))

    def test_gap_and_position_jump_cannot_transfer_verified_state(self):
        for now,position in ((2,(.5,.5)),(1,(.9,.5))):
            self.unlock()
            self.assertFalse(self.gate.verify([Pose('point',hand='Right',geometry=VECTOR,palm=position)],now))

    def test_two_hand_zoom_after_verification(self):
        self.gate.save({'Right':VECTOR,'Left':VECTOR})
        for i in range(10):
            self.gate.verify([Pose('palm',hand=h,geometry=VECTOR,palm=(x,.5))
                              for h,x in (('Left',.2),('Right',.6))],i*.1)
        router=HandsFree(); actions=[]
        changed=VECTOR[:7]+tuple(v*.6 for v in VECTOR[7:])
        for i in range(30):
            poses=[Pose('point',ratio=.1,hand=h,geometry=changed,palm=(x,.5),pointer=(x,.5))
                   for h,x in (('Left',.2),('Right',.6+i*.006))]
            self.assertTrue(self.gate.verify(poses,1+i/30))
            actions.extend(router.update(poses,1+i/30))
        self.assertTrue(actions)
        self.assertEqual({a.name for a in actions},{'zoom'})


if __name__=='__main__': unittest.main()
