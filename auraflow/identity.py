"""Approximate hand geometry filter; not biometric authentication."""
import json
import math
import statistics
from pathlib import Path

EDGES = ((0,5),(0,9),(0,13),(0,17),(5,9),(9,13),(13,17),
         (1,2),(2,3),(3,4),(5,6),(6,7),(7,8),(9,10),(10,11),
         (11,12),(13,14),(14,15),(15,16),(17,18),(18,19),(19,20))


def features(points):
    if len(points) != 21 or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        return ()
    lengths = [math.dist(points[a], points[b]) for a,b in EDGES]
    scale = lengths[1]
    if scale < .005 or any(v < .001 for v in lengths):
        return ()
    return tuple(v/scale for v in lengths)


def distance(a, b):
    if len(a) != len(EDGES) or len(b) != len(EDGES):
        return math.inf
    if any(not math.isfinite(v) or v <= 0 for v in (*a,*b)):
        return math.inf
    errors = [abs(math.log(x/y)) for x,y in zip(a,b)]
    return max(math.sqrt(sum(e*e for e in errors)/len(errors)), max(errors)/3)


def palm_distance(a, b):
    # Finger estimates change when joints are occluded by a pinch or fist.
    # Once verified, compare only the rigid palm while following the same hand.
    if distance(a, a) != 0 or distance(b, b) != 0:
        return math.inf
    errors = [abs(math.log(x/y)) for x,y in zip(a[:7],b[:7])]
    return max(math.sqrt(sum(e*e for e in errors)/len(errors)), max(errors)/3)


class HandIdentity:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = {}
        self.error = ''
        self.pending = None
        self.samples = []
        self.sample_time = None
        self.tracks = {}
        self.threshold = .10
        self.status = 'Enroll your hands in My hands'
        self.load()

    def load(self):
        if not self.path.exists(): return
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data['version'] != 1: raise ValueError('Unsupported profile version')
            profiles = data['hands']
            if not isinstance(profiles, dict): raise ValueError('Invalid profiles')
            for hand, values in profiles.items():
                if hand not in ('Left','Right') or distance(values, values) != 0:
                    raise ValueError('Invalid profile')
            self.profiles = profiles
        except (OSError, ValueError, TypeError, KeyError):
            self.error = 'Profile unreadable. Re-enroll your hands.'

    def save(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'version':1, 'hands':profiles}), encoding='utf-8')
        temp.replace(self.path)
        self.profiles = profiles
        self.error = ''
        self.tracks.clear()

    def begin(self, hand):
        self.pending = hand
        self.samples = []
        self.sample_time = None
        self.tracks.clear()

    def cancel(self):
        self.pending = None
        self.samples = []
        self.tracks.clear()

    def enroll(self, poses, now):
        hand = self.pending
        if not hand: return False
        valid = (len(poses)==1 and poses[0] is not None and poses[0].hand==hand
                 and poses[0].kind=='palm' and bool(poses[0].geometry))
        if not valid:
            self.samples=[]; self.sample_time=None
            self.status=f'Show only your {hand.lower()} open palm, fingers spread'
            return False
        values = poses[0].geometry
        if self.sample_time is not None:
            if now-self.sample_time > .35: self.samples=[]
            elif now-self.sample_time < .05: return False
        self.sample_time=now
        if self.samples and distance(values, self.samples[0]) > .12:
            self.samples=[]
        self.samples.append(values)
        self.status=f'{hand} hand · keep palm steady · {len(self.samples)}/60'
        if len(self.samples) < 60: return False
        profile=[statistics.median(column) for column in zip(*self.samples)]
        try:
            self.save({**self.profiles, hand:profile})
        except OSError:
            self.status='Could not save profile. Check folder permissions and retry.'
            self.cancel()
            return False
        self.cancel()
        self.status=f'{hand} hand enrolled. Enroll the other hand for two-hand controls.'
        return True

    def verify(self, poses, now):
        if self.error or not self.profiles:
            self.tracks.clear(); self.status=self.error or 'Enroll your hands in My hands'
            return False
        labels=[p.hand for p in poses if p is not None]
        if not poses or len(labels)!=len(poses) or len(set(labels))!=len(labels):
            self.tracks.clear(); self.status='Show your enrolled hand clearly'
            return False
        new_tracks={}
        ready=True
        for p in poses:
            profile=self.profiles.get(p.hand,())
            old=self.tracks.get(p.hand)
            continuous=bool(old and 0 <= now-old[1] <= .25 and math.dist(p.palm,old[2]) < .18)
            authenticated=continuous and old[3]
            if authenticated:
                # Keep verification through pose changes, but never through a
                # tracking break, missing geometry, or incompatible palm shape.
                score=distance(p.geometry,profile) if p.kind=='palm' else palm_distance(p.geometry,profile)
                limit=self.threshold if p.kind=='palm' else max(.16,self.threshold*1.8)
                if score > limit:
                    self.tracks.clear(); self.status='Tracking uncertain · show enrolled open palm'
                    return False
                since=old[0]
            else:
                if p.kind!='palm' or distance(p.geometry,profile) > self.threshold:
                    self.tracks.clear(); self.status='Show your enrolled open palm to unlock gestures'
                    return False
                since=old[0] if continuous else now
                authenticated=now-since >= .6
            new_tracks[p.hand]=(since,now,p.palm,authenticated)
            ready = ready and authenticated
        self.tracks=new_tracks
        self.status='Verified hand · tracking gestures' if ready else 'Keep open palm steady · verifying…'
        return ready
