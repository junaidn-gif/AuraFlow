"""Single hands-free router. Two-hand actions always suppress single-hand actions."""
import math
from collections import deque
from .gestures import GestureEngine, Action


def hand_label(raw, swap=False):
    return ({'Left': 'Right', 'Right': 'Left'}.get(raw, raw) if swap else raw)


class HandsFree:
    def __init__(self):
        self.single = GestureEngine('Auto')
        self.paused = False
        self.reset()

    def reset(self):
        self.single.reset()
        self.signature = None
        self.since = 0
        self.last = None
        self.latched = False
        self.anchor = None
        self.last_emit = -10
        self.release = False
        self.in_view_reset_since = None
        self.reset_fist_held = False
        self.reset_open_since = None
        self.tab_history = deque()
        self.app_history = deque()
        self.app_blocked = False
        self.tab_blocked = False
        self.tab_release_since = None
        self.status = 'Show your hand to begin'
        self.progress = 0

    def update(self, poses, now):
        poses = [p for p in poses if p is not None]
        signature = tuple(sorted((p.hand, p.kind) for p in poses))
        if self.last is not None and now-self.last > .35:
            pending = (self.tab_blocked, self.app_blocked, self.release, self.reset_fist_held)
            self.reset()
            self.tab_blocked, self.app_blocked, self.release, self.reset_fist_held = pending
        self.last = now
        if self.reset_fist_held:
            if poses and all(p.kind == 'fist' for p in poses):
                self.reset_open_since = None
                self.status = 'Ready · open your hand for the next gesture'
                self.progress = 0
                return []
            if self.reset_open_since is None:
                self.reset_open_since = now
            if now-self.reset_open_since < .15:
                self.status = 'Ready · open your hand for the next gesture'
                return []
            # The reset fist is consumed until it opens; it never becomes mute,
            # play/pause, or zoom reset, even if held for several seconds.
            self.reset()
            self.last = now
        if self.tab_blocked or self.app_blocked or self.release:
            if poses and all(p.kind == 'fist' for p in poses):
                if self.in_view_reset_since is None:
                    self.in_view_reset_since = now
                self.progress = min(1, (now-self.in_view_reset_since)/.25)
                self.status = 'Briefly close your hand to reset'
                if self.progress >= 1:
                    self.reset()
                    self.last = now
                    self.reset_fist_held = True
                    self.status = 'Ready · open your hand for the next gesture'
                return []
            self.in_view_reset_since = None
        if self.tab_blocked or self.app_blocked:
            released = not poses or all(p.kind == 'neutral' for p in poses)
            if released:
                if self.tab_release_since is None:
                    self.tab_release_since = now
                if now - self.tab_release_since >= .22:
                    self.tab_blocked = False
                    self.app_blocked = False
                    self.signature = None
                    self.tab_history.clear()
            else:
                self.tab_release_since = None
            self.status = 'Close your hand briefly, then make the next gesture'
            return []
        if self.release:
            if not poses or all(p.kind == 'neutral' for p in poses):
                self.release = False
            self.status = 'Close your visible hands briefly to continue'
            return []
        if signature != self.signature:
            self.signature, self.since = signature, now
            self.anchor = None
            self.latched = False
            self.single.reset()
            self.tab_history.clear()
            self.app_history.clear()
        self.progress = 0
        if len(poses) == 1 and poses[0].kind == 'thumb_up' and poses[0].hand == 'Left':
            self.status = 'Hold LEFT thumbs-up to resume' if self.paused else 'Hold LEFT thumbs-up to pause'
            return self.hold('toggle_pause', now, .9)
        if self.paused:
            self.status = 'Paused · LEFT thumbs-up to resume'
            return []
        if len(poses) == 2:
            self.single.reset()
            a, b = poses
            kinds = {a.kind,b.kind}
            if all(p.kind in ('point','adjust') and p.ratio < .32 for p in poses):
                distance=math.dist(a.pointer,b.pointer)
                self.status='Two-hand zoom · spread or bring hands together'
                if self.anchor is None:
                    self.anchor=distance
                if now-self.since < .3: return []
                delta=distance-self.anchor
                if abs(delta) > .055 and now-self.last_emit > .16:
                    self.anchor=distance
                    self.last_emit=now
                    return [Action('zoom', 1 if delta>0 else -1)]
            elif kinds == {'fist'}:
                self.status='Hold both fists · reset zoom'
                return self.hold('zoom_reset', now, .9)
            elif kinds == {'peace'}:
                self.status='Hold two V signs · screenshot'
                return self.hold('screenshot', now, 1.2)
            elif kinds == {'palm'}:
                self.status='Hold both palms · show desktop'
                return self.hold('desktop', now, 1.2)
            else:
                self.status='Two hands detected · pinch both to zoom'
            return []
        if not poses:
            self.single.update(None, now)
            self.status='Ready · show one or both hands'
            return []
        pose=poses[0]
        if pose.kind == 'middle_only':
            # Require a stationary, uninterrupted single-hand hold. The normal
            # release latch prevents closing several windows with one pose.
            if self.anchor is None or math.dist(self.anchor, pose.palm) > .05:
                self.anchor = pose.palm
                self.since = now
            self.status = 'Hold middle finger only · close focused app'
            return self.hold('close_app', now, 1.2)
        if pose.kind == 'thumb_up':
            self.status='Right hand ready · use LEFT thumbs-up to pause'
            return []
        if pose.kind == 'four':
            self.status='Four fingers, thumb tucked · swipe for desktop apps'
            self.app_history.append((now, *pose.palm))
            while self.app_history and now-self.app_history[0][0] > 1.1:
                self.app_history.popleft()
            t0, x0, y0 = self.app_history[0]
            dx, dy = pose.palm[0]-x0, pose.palm[1]-y0
            self.progress=min(1,abs(dx)/.16)
            if now-self.since >= .24 and now-t0 >= .12 and abs(dx) > .16 and abs(dy) < .12:
                self.app_blocked=True
                self.tab_release_since=None
                self.status='Alt + Tab' if dx>0 else 'Alt + Shift + Tab'
                return [Action('app_next' if dx>0 else 'app_previous')]
            return []
        if pose.kind == 'three':
            self.status='Three fingers · swipe left or right for tabs'
            self.tab_history.append((now, *pose.palm))
            while self.tab_history and now-self.tab_history[0][0] > 1.1:
                self.tab_history.popleft()
            t0, x0, y0 = self.tab_history[0]
            dx, dy = pose.palm[0]-x0, pose.palm[1]-y0
            self.progress=min(1,abs(dx)/.16)
            # Rolling history means waiting with three fingers raised never
            # disables the gesture. One swipe produces exactly one shortcut.
            if now-t0 >= .12 and abs(dx) > .16 and abs(dy) < .12:
                self.tab_blocked=True
                self.tab_release_since=None
                self.status='Next tab' if dx>0 else 'Previous tab'
                return [Action('tab_next' if dx>0 else 'tab_previous')]
            return []
        if pose.kind == 'peace':
            self.status='V sign · move vertically to scroll'
            if self.anchor is None: self.anchor=pose.palm[1]
            delta=self.anchor-pose.palm[1]
            if abs(delta)>.06 and now-self.last_emit>.15:
                self.anchor=pose.palm[1]; self.last_emit=now
                return [Action('scroll',1 if delta>0 else -1)]
            return []
        if pose.kind == 'point' and pose.hand == 'Left':
            self.status='Left hand · extend pinky to adjust brightness'
            return []
        # Left fist = media playback, right fist = mute. No hold/scroll conflict.
        if pose.kind == 'fist' and pose.hand == 'Left':
            self.status='Left fist · hold to play / pause'
            return self.hold('play_pause', now, .8)
        actions=self.single.update(pose,now)
        self.status,self.progress=self.single.status,self.single.progress
        if any(a.name in ('mute','next_track','previous_track') for a in actions):
            self.release = True
        return actions

    def hold(self, action, now, duration):
        self.progress=min(1,(now-self.since)/duration)
        if self.progress>=1 and not self.latched:
            self.latched=True
            self.release=True
            if action=='toggle_pause': self.paused=not self.paused
            return [Action(action)]
        return []
