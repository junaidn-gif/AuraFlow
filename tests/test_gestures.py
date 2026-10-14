"""Behavioral tests: no webcam or Windows APIs required."""
import math
import unittest
from auraflow.gestures import GestureEngine, Pose, analyze
from auraflow.demo import landmarks, sample, CHOICES


def feed(engine, pose, start=0, duration=1, fps=30):
    actions = []
    for frame in range(round(duration * fps) + 1):
        actions += engine.update(pose, start + frame / fps)
    return actions


class GeometryTests(unittest.TestCase):
    def test_all_fixture_poses(self):
        for kind in ('adjust', 'point', 'peace', 'three', 'palm', 'fist', 'neutral'):
            with self.subTest(kind=kind):
                self.assertEqual(analyze(landmarks(kind)).kind, kind)

    def test_pinch_distance_is_scale_and_rotation_invariant(self):
        points = landmarks('adjust', .73)
        for scale in (.5, 1, 1.4):
            for angle in (0, .6, -1.0):
                transformed = []
                for x, y in points:
                    x, y = (x - .5) * 640, (y - .5) * 480
                    transformed.append((.5 + scale * (x * math.cos(angle) - y * math.sin(angle)) / 640,
                                        .5 + scale * (x * math.sin(angle) + y * math.cos(angle)) / 480))
                pose = analyze(transformed)
                self.assertEqual(pose.kind, 'adjust')
                self.assertAlmostEqual(pose.ratio, .73, places=5)

    def test_invalid_and_tiny_hands_are_ignored(self):
        self.assertIsNone(analyze([]))
        self.assertIsNone(analyze([(0, 0)] * 21))
        self.assertIsNone(analyze([(float('nan'), 0)] * 21))

    def test_mirrored_hand(self):
        pose = analyze([(1-x, y) for x, y in landmarks('adjust', .8)])
        self.assertEqual(pose.kind, 'adjust')
        self.assertAlmostEqual(pose.ratio, .8)


class BehaviorTests(unittest.TestCase):
    def test_volume_requires_confirmation_and_pinky(self):
        engine = GestureEngine()
        self.assertEqual(feed(engine, Pose('adjust', .8), duration=.1), [])
        locked = feed(engine, Pose('point', .8), start=.13)
        self.assertEqual(locked, [])
        self.assertEqual(engine.value, 50)

    def test_folded_pinky_freezes_level(self):
        engine = GestureEngine()
        self.assertTrue(feed(engine, Pose('adjust', .9)))
        level = engine.value
        self.assertEqual(feed(engine, Pose('point', .18), start=1.04), [])
        self.assertEqual(engine.value, level)
        self.assertEqual(feed(engine, None, start=2.08), [])
        self.assertEqual(engine.value, level)

    def test_open_palm_never_changes_volume(self):
        self.assertEqual(feed(GestureEngine(), Pose('palm', 1.2), duration=3), [])

    def test_closed_pinch_reaches_zero_without_mute(self):
        engine = GestureEngine()
        actions = feed(engine, Pose('adjust', .01), duration=2)
        self.assertEqual(actions[-1].value, 0)
        self.assertEqual({a.name for a in actions}, {'volume'})

    def test_brightness_never_goes_below_ten(self):
        actions = feed(GestureEngine('Display'), Pose('adjust', 0), duration=2)
        self.assertEqual(actions[-1].value, 10)
        self.assertTrue(all(10 <= a.value <= 100 for a in actions))

    def test_fist_fires_once_and_needs_neutral_release(self):
        engine = GestureEngine()
        self.assertEqual([a.name for a in feed(engine, Pose('fist'), duration=3)], ['mute'])
        self.assertEqual(feed(engine, Pose('palm'), start=3.04), [])
        self.assertEqual(feed(engine, Pose('fist'), start=4.08), [])
        feed(engine, Pose('neutral'), start=5.12, duration=.4)
        self.assertEqual([a.name for a in feed(engine, Pose('fist'), start=5.56)], ['mute'])

    def test_optional_fist_disabled(self):
        engine = GestureEngine(); engine.fist_mute = False
        self.assertEqual(feed(engine, Pose('fist')), [])

    def test_short_detection_dropout_cannot_finish_a_hold(self):
        engine = GestureEngine('Media')
        self.assertEqual(feed(engine, Pose('peace'), duration=.5), [])
        engine.update(None, .53)
        self.assertEqual(feed(engine, Pose('peace'), start=.56, duration=.4), [])

    def test_delayed_frame_cannot_finish_old_confirmation(self):
        engine = GestureEngine('Media')
        engine.update(Pose('peace'), 0)
        self.assertEqual(engine.update(Pose('peace'), 4), [])

    def test_mode_switch_resets_confirmation(self):
        engine = GestureEngine('Media')
        feed(engine, Pose('peace'), duration=.5)
        engine.set_mode('Audio')
        self.assertEqual(feed(engine, Pose('peace'), start=.54), [])

    def test_swipe_direction_and_hold_latch(self):
        for mode, right, left in [('Media', 'next_track', 'previous_track'), ('Slides', 'next_slide', 'previous_slide')]:
            for direction, expected in [(1, right), (-1, left)]:
                engine = GestureEngine(mode); actions = []
                for frame in range(30):
                    actions += engine.update(Pose('palm', palm=(.5 + direction * min(frame, 15) * .018, .5)), frame / 30)
                self.assertEqual([a.name for a in actions], [expected])

    def test_slow_or_vertical_drift_is_not_swipe(self):
        for speed, vertical in [(.002, 0), (.018, .02)]:
            engine = GestureEngine('Media'); actions = []
            for frame in range(30):
                actions += engine.update(Pose('palm', palm=(.2 + frame * speed, .2 + frame * vertical)), frame / 30)
            self.assertEqual(actions, [])

    def test_mouse_needs_open_pinch_before_one_click(self):
        engine = GestureEngine('Pointer')
        self.assertEqual(feed(engine, Pose('point', .1)), [])
        feed(engine, Pose('point', .6), start=1.04)
        clicks = feed(engine, Pose('point', .1), start=2.08, duration=2)
        self.assertEqual([a.name for a in clicks], ['click'])

    def test_pointer_click_freezes_movement(self):
        engine = GestureEngine('Pointer')
        feed(engine, Pose('point', .6))
        actions = feed(engine, Pose('point', .1, pointer=(1, 1)), start=1.04)
        self.assertNotIn('move', [a.name for a in actions])

    def test_pointer_freezes_during_pinch_approach(self):
        engine = GestureEngine('Pointer')
        feed(engine, Pose('point', .7, pointer=(.2, .2)))
        actions = feed(engine, Pose('point', .34, pointer=(.9, .9)), start=1.04, duration=.3)
        self.assertEqual(actions, [])

    def test_scroll_and_move_are_bounded(self):
        engine = GestureEngine('Pointer')
        actions = feed(engine, Pose('point', .6, pointer=(-5, 8)))
        self.assertTrue(actions)
        self.assertTrue(all(0 < x < 1 and 0 < y < 1 for x, y in [a.value for a in actions]))
        self.assertEqual(engine.update(Pose('peace', pointer=(.5, .5)), 1.04), [])
        self.assertEqual(engine.update(Pose('peace', pointer=(.5, .4)), 1.24)[0].name, 'scroll')

    def test_every_demo_choice_exercises_its_expected_control(self):
        expected = {'Adjust volume': 'volume', 'Adjust brightness': 'brightness', 'Fist to mute': 'mute',
                    'Play / pause': 'play_pause', 'Next track': 'next_track', 'Previous track': 'previous_track',
                    'Next slide': 'next_slide', 'Previous slide': 'previous_slide', 'Blank screen': 'blank',
                    'Move pointer': 'move', 'Pinch to click': 'click', 'Two-finger scroll': 'scroll'}
        expected.update({'Right pinch · volume': 'volume', 'Left pinch · brightness': 'brightness',
                         'Fist · mute': 'mute', 'V sign · play / pause': 'play_pause',
                         'Open palm · next track': 'next_track', 'Three fingers · next slide': 'next_slide',
                         'Point · mouse': 'move'})
        for mode, choices in CHOICES.items():
            for choice in choices:
                with self.subTest(mode=mode, choice=choice):
                    engine = GestureEngine(mode); actions = []
                    for frame in range(240):
                        actions += engine.update(analyze(sample(mode, choice, frame/30), hand=__import__('auraflow.demo', fromlist=['hand_for']).hand_for(choice)), frame/30)
                    names = {a.name for a in actions}
                    if choice == 'Pinky lock': self.assertEqual(names, set())
                    else: self.assertIn(expected[choice], names)

    def test_hands_free_routes_hands_and_gestures(self):
        right = GestureEngine('Auto')
        volume = feed(right, Pose('adjust', .8, hand='Right'))
        self.assertEqual({a.name for a in volume}, {'volume'})
        left = GestureEngine('Auto')
        brightness = feed(left, Pose('adjust', .8, hand='Left'))
        self.assertEqual({a.name for a in brightness}, {'brightness'})
        blank = GestureEngine('Auto')
        self.assertEqual([a.name for a in feed(blank, Pose('three'), duration=1.2)], ['blank'])

    def test_hands_free_v_sign_scrolls_when_moved(self):
        engine = GestureEngine('Auto')
        actions = []
        for frame in range(18):
            actions += engine.update(Pose('peace', palm=(.5, .6 - frame * .009)), frame / 30)
        self.assertIn('scroll', [a.name for a in actions])
        self.assertNotIn('play_pause', [a.name for a in actions])


if __name__ == '__main__':
    unittest.main()
