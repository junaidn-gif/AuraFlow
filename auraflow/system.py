"""Windows adapters. A demo never instantiates these adapters."""
import ctypes
import sys
from ctypes import wintypes


class WindowsInput:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("System controls require Windows 10 or 11.")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        ulong_ptr = ctypes.c_size_t

        class MouseInput(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class KeyboardInput(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ulong_ptr)]

        class HardwareInput(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                        ("wParamH", wintypes.WORD)]

        class Union(ctypes.Union):
            _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]

        class Input(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", Union)]

        self.Input = Input
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self.user32.SetCursorPos.restype = wintypes.BOOL
        self.user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        self.user32.GetCursorPos.restype = wintypes.BOOL

    def _send(self, entries):
        array = (self.Input * len(entries))(*entries)
        if self.user32.SendInput(len(entries), array, ctypes.sizeof(self.Input)) != len(entries):
            raise RuntimeError("Windows blocked the input. Focus a normal desktop app.")

    def key(self, code):
        # Do not accidentally combine synthetic keys with a held modifier.
        if any(self.user32.GetAsyncKeyState(k) & 0x8000 for k in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise RuntimeError("Release Shift, Ctrl, Alt and Windows keys, then try again.")
        down, up = self.Input(), self.Input()
        down.type = up.type = 1
        down.ki.wVk = up.ki.wVk = code
        extended = 1 if code in (0x25, 0x27, 0xB0, 0xB1, 0xB3) else 0
        down.ki.dwFlags, up.ki.dwFlags = extended, extended | 2
        self._send([down, up])

    def chord(self, *codes):
        if any(self.user32.GetAsyncKeyState(k) & 0x8000 for k in (0x10,0x11,0x12,0x5B,0x5C)):
            raise RuntimeError("Release modifier keys first.")
        pressed=[]
        try:
            for code in codes:
                event=self.Input(); event.type=1; event.ki.wVk=code
                event.ki.dwFlags=1 if code in (0x5B,0x5C,0x2C) else 0
                self._send([event]); pressed.append(code)
        finally:
            # Release each key even if a later SendInput fails.
            for code in reversed(pressed):
                event=self.Input(); event.type=1; event.ki.wVk=code; event.ki.dwFlags=2 | (1 if code in (0x5B,0x5C,0x2C) else 0)
                self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(self.Input))

    def move(self, xy):
        width, height = self.user32.GetSystemMetrics(0), self.user32.GetSystemMetrics(1)
        if not self.user32.SetCursorPos(round(xy[0] * (width - 1)), round(xy[1] * (height - 1))):
            raise RuntimeError("Windows could not move the pointer.")

    def click(self):
        down, up = self.Input(), self.Input()
        down.mi.dwFlags, up.mi.dwFlags = 2, 4
        self._send([down, up])

    def scroll(self, direction):
        event = self.Input()
        event.mi.dwFlags = 0x0800
        event.mi.mouseData = (120 * direction) & 0xffffffff
        self._send([event])

    def pause_pressed(self):
        return all(self.user32.GetAsyncKeyState(k) & 0x8000 for k in (0x11, 0x12, 0x50))

    def corner_stop(self):
        point = wintypes.POINT()
        return bool(self.user32.GetCursorPos(ctypes.byref(point)) and point.x <= 2 and point.y <= 2)


class Audio:
    def __init__(self):
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        device = AudioUtilities.GetSpeakers()
        if device is None:
            raise RuntimeError("No default audio output. Connect speakers or headphones.")
        # The pinned pycaw release returns IMMDevice; newer releases wrap it.
        if not hasattr(device, "EndpointVolume"):
            device = AudioUtilities.CreateDevice(device)
        self.name = str(device.FriendlyName or "Windows default output")
        if hasattr(device, "EndpointVolume"):
            self.endpoint = device.EndpointVolume
        else:
            raw = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.endpoint = ctypes.cast(raw, ctypes.POINTER(IAudioEndpointVolume))

    def read(self):
        return round(self.endpoint.GetMasterVolumeLevelScalar() * 100), bool(self.endpoint.GetMute())

    def set(self, value):
        self.endpoint.SetMasterVolumeLevelScalar(max(0, min(100, value)) / 100, None)

    def mute(self):
        self.endpoint.SetMute(int(not self.endpoint.GetMute()), None)


class SystemController:
    """Created and used only on the system worker's COM thread."""
    def __init__(self):
        self.input = WindowsInput()
        self.audio = None
        self.brightness_module = None

    def _audio(self):
        if self.audio is None:
            self.audio = Audio()
        return self.audio

    def _display(self):
        if self.brightness_module is None:
            import screen_brightness_control as sbc
            self.brightness_module = sbc
        return self.brightness_module

    def perform(self, action, display=0):
        name, value = action.name, action.value
        if name == "volume":
            self._audio().set(value)
            return {"volume": self._audio().read()[0]}
        if name == "mute":
            self._audio().mute()
            return {"muted": self._audio().read()[1]}
        if name == "brightness":
            self._display().set_brightness(max(10, min(100, value)), display=display)
            return {"brightness": self._display().get_brightness(display=display)[0]}
        if name == "read_audio":
            self.audio = None  # Refresh the currently selected Windows output.
            value, muted = self._audio().read()
            return {"volume": value, "muted": muted, "device": self._audio().name}
        if name == "read_display":
            return {"brightness": self._display().get_brightness(display=display)[0]}
        chords = {"close_app": (0x12,0x73),
                  "app_next": (0x12,0x09), "app_previous": (0x12,0x10,0x09),
                  "zoom_reset": (0x11,0x30), "desktop": (0x5B,0x44),
                  "screenshot": (0x5B,0x2C), "tab_next": (0x11,0x09),
                  "tab_previous": (0x11,0x10,0x09)}
        if name == "zoom":
            self.input.chord(0x11, 0xBB if value > 0 else 0xBD)
        elif name in chords:
            self.input.chord(*chords[name])
        elif name == "move":
            self.input.move(value)
        elif name == "click":
            self.input.click()
        elif name == "scroll":
            self.input.scroll(value)
        else:
            keys = {"play_pause": 0xB3, "next_track": 0xB0, "previous_track": 0xB1}
            if name not in keys:
                raise ValueError("Unsupported action: " + name)
            self.input.key(keys[name])
        return {}
