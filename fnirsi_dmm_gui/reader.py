"""Background serial reader. Never writes to the device."""
import errno
import glob
import os
import threading
import time

import serial
from gi.repository import GLib

from .protocol import parse

SYMLINK = '/dev/fnirsi-2d15p'
VIDPID = ('0416', '50a1')
WAIT_AFTER = 3.0  # seconds without data => "waiting"


def find_port():
    if os.path.exists(SYMLINK):
        return SYMLINK
    for t in sorted(glob.glob('/sys/class/tty/ttyACM*')):
        try:
            d = os.path.realpath(t + '/device')
            while d != '/' and not os.path.exists(d + '/idVendor'):
                d = os.path.dirname(d)
            with open(d + '/idVendor') as v, open(d + '/idProduct') as p:
                if (v.read().strip(), p.read().strip()) == VIDPID:
                    return '/dev/' + os.path.basename(t)
        except OSError:
            continue
    return None


class Reader(threading.Thread):
    """Calls on_sample(dict) and on_state(str) via `dispatch` (GLib main loop by default).
    States: 'no-device', 'no-permission', 'waiting', 'streaming'."""

    wait_after = WAIT_AFTER
    retry_s = 1.0

    def __init__(self, on_sample, on_state, port=None, dispatch=GLib.idle_add):
        super().__init__(daemon=True)
        self.on_sample, self.on_state, self.port = on_sample, on_state, port
        self.dispatch = dispatch
        self._halt = threading.Event()
        self._state = None

    def stop(self):
        self._halt.set()

    def _set(self, s):
        if s != self._state:
            self._state = s
            self.dispatch(self.on_state, s)

    def run(self):
        while not self._halt.is_set():
            port = self.port or find_port()
            if not port:
                self._set('no-device')
                self._halt.wait(self.retry_s)
                continue
            try:
                with serial.Serial(port, timeout=0.5, dsrdtr=False) as ser:
                    try:
                        ser.dtr = True  # open() already raises it; ptys reject the ioctl
                    except OSError:
                        pass
                    self._set('waiting')
                    buf = b''
                    last = time.monotonic()
                    while not self._halt.is_set():
                        buf += ser.read(256)
                        while b'\n' in buf:
                            raw, buf = buf.split(b'\n', 1)
                            s = parse(raw.decode('ascii', 'replace'))
                            if s:
                                last = time.monotonic()
                                self._set('streaming')
                                self.dispatch(self.on_sample, s)
                        if time.monotonic() - last > self.wait_after:
                            self._set('waiting')
            except (serial.SerialException, OSError) as e:
                denied = getattr(e, 'errno', None) in (errno.EACCES, errno.EPERM)
                self._set('no-permission' if denied else 'no-device')
                self._halt.wait(self.retry_s)
