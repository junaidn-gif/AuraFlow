"""Verify raw and wrapped pycaw device compatibility without Windows hardware."""
import sys
import types
import unittest
from unittest.mock import patch
from auraflow.system import Audio


class Endpoint:
    def __init__(self):
        self.value, self.muted = .5, False

    def GetMasterVolumeLevelScalar(self): return self.value
    def GetMute(self): return self.muted
    def SetMasterVolumeLevelScalar(self, value, context): self.value = value
    def SetMute(self, value, context): self.muted = bool(value)


class AudioTests(unittest.TestCase):
    def make_audio(self, wrapped):
        endpoint = Endpoint()
        device = types.SimpleNamespace(FriendlyName="Test speakers", EndpointVolume=endpoint)
        raw = object()
        utilities = types.SimpleNamespace(GetSpeakers=lambda: device if wrapped else raw,
                                         CreateDevice=lambda source: device if source is raw else None)
        api = types.SimpleNamespace(AudioUtilities=utilities, IAudioEndpointVolume=object)
        modules = {'pycaw': types.ModuleType('pycaw'), 'pycaw.pycaw': api,
                   'comtypes': types.SimpleNamespace(CLSCTX_ALL=23)}
        with patch.dict(sys.modules, modules):
            return Audio(), endpoint

    def test_pinned_pycaw_raw_device_is_wrapped(self):
        audio, endpoint = self.make_audio(False)
        self.assertEqual(audio.name, 'Test speakers')
        self.assertEqual(audio.read(), (50, False))

    def test_newer_wrapped_device_also_works(self):
        audio, endpoint = self.make_audio(True)
        self.assertEqual(audio.read(), (50, False))

    def test_levels_are_clamped_and_never_unmute(self):
        audio, endpoint = self.make_audio(False)
        audio.mute()
        audio.set(-40)
        self.assertEqual(audio.read(), (0, True))
        audio.set(150)
        self.assertEqual(audio.read(), (100, True))
        audio.mute()
        self.assertEqual(audio.read(), (100, False))


if __name__ == '__main__': unittest.main()
