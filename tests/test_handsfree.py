import unittest
from auraflow.handsfree import HandsFree,hand_label
from auraflow.gestures import Pose

def pose(kind,hand='Right',x=.5,ratio=.7,y=.5):
    return Pose(kind,ratio,(x,y),(x,y),hand)

def hold(router,poses,start=0,duration=1.3):
    actions=[]
    for i in range(round(duration*30)+1): actions+=router.update(poses,start+i/30)
    return [a.name for a in actions]

class HandsFreeTests(unittest.TestCase):
    def test_anatomical_labels_and_override(self):
        self.assertEqual(hand_label('Right'),'Right')
        self.assertEqual(hand_label('Left',True),'Right')
        self.assertEqual(hand_label('Right',True),'Left')

    def test_volume_brightness(self):
        for hand,action in [('Left','brightness'),('Right','volume')]:
            self.assertEqual(set(hold(HandsFree(),[pose('adjust',hand)])),{action})

    def test_two_hand_zoom_suppresses_volume_and_click(self):
        router=HandsFree()
        actions=[]
        for i in range(30):
            actions+=router.update([pose('point','Left',.2,.1),pose('point','Right',.6+i*.006,.1)],i/30)
        self.assertTrue(actions)
        self.assertEqual({a.name for a in actions},{'zoom'})
        self.assertTrue(all(a.value==1 for a in actions))

    def test_zoom_inward(self):
        r=HandsFree(); actions=[]
        for i in range(30): actions+=r.update([pose('adjust','Left',.2,.1),pose('adjust','Right',.8-i*.006,.1)],i/30)
        self.assertTrue(actions); self.assertTrue(all(a.value==-1 for a in actions))

    def test_both_hand_actions_once(self):
        for kind,action in [('fist','zoom_reset'),('peace','screenshot'),('palm','desktop')]:
            self.assertEqual(hold(HandsFree(),[pose(kind,'Left'),pose(kind)]),[action])

    def test_release_prevents_single_hand_leak(self):
        r=HandsFree(); hold(r,[pose('peace','Left'),pose('peace')])
        self.assertEqual(hold(r,[pose('fist')],1.34),[])
        r.update([],2.7)
        # Opening the reset fist must be stable, not one missing frame.
        self.assertEqual(hold(r,[pose('neutral')],2.74,duration=.3),[])
        self.assertEqual(hold(r,[pose('fist')],3.08),['mute'])

    def test_pause_resume_without_mouse(self):
        r=HandsFree(); self.assertEqual(hold(r,[pose('thumb_up','Left')]),['toggle_pause'])
        self.assertTrue(r.paused)
        r.update([],1.34)
        self.assertEqual(hold(r,[pose('adjust')],1.37),[])
        self.assertEqual(hold(r,[pose('thumb_up','Left')],2.71),['toggle_pause'])
        self.assertFalse(r.paused)

    def test_scroll_does_not_toggle_playback(self):
        r=HandsFree(); actions=[]
        for i in range(45): actions+=r.update([pose('peace',y=.8-i*.01)],i/30)
        self.assertEqual({a.name for a in actions},{'scroll'})

    def test_left_fist_playback(self):
        self.assertEqual(hold(HandsFree(),[pose('fist','Left')]),['play_pause'])

    def test_tab_swipe_not_presentation(self):
        r=HandsFree(); actions=[]
        for i in range(20): actions+=r.update([pose('three',x=.2+i*.02)],i/30)
        self.assertEqual([a.name for a in actions],['tab_next'])
        self.assertEqual(hold(HandsFree(),[pose('three')]),[])

    def test_gap_interrupts_confirmation(self):
        r=HandsFree(); r.update([pose('peace','Left'),pose('peace')],0)
        self.assertEqual(r.update([pose('peace','Left'),pose('peace')],2),[])

    def test_left_point_is_not_pointer(self):
        self.assertEqual(hold(HandsFree(),[pose('point','Left')]),[])
