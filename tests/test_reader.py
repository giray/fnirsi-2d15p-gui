import os
import pty
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fnirsi_dmm_gui import reader as R


def make(port, ports=None):
    """Start a Reader that records states/samples synchronously."""
    states, samples = [], []
    r = R.Reader(samples.append, states.append, port, dispatch=lambda f, *a: f(*a))
    r.wait_after, r.retry_s = 0.6, 0.1
    r.start()
    return r, states, samples


def wait_for(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_stream_waiting_and_no_writes():
    m, s = pty.openpty()
    r, states, samples = make(os.ttyname(s))
    try:
        assert wait_for(lambda: 'waiting' in states)
        os.write(m, b'DMM,DCV,1.234,V,0\r\nbogus\r\nDMM,RES,OL,Ohm,1\r\n')
        assert wait_for(lambda: len(samples) == 2)
        assert samples[0]['value'] == '1.234' and samples[1]['hold']
        assert states[-1] == 'streaming'
        # device goes quiet (left the multimeter page) -> back to waiting
        assert wait_for(lambda: states[-1] == 'waiting')
        # the reader must never write to the device
        os.set_blocking(m, False)
        try:
            assert os.read(m, 64) == b''
        except BlockingIOError:
            pass
    finally:
        r.stop()


def test_split_lines_across_reads():
    m, s = pty.openpty()
    r, states, samples = make(os.ttyname(s))
    try:
        assert wait_for(lambda: 'waiting' in states)
        os.write(m, b'DMM,DC')
        time.sleep(0.2)
        os.write(m, b'V,5.0,V,0\r\n')
        assert wait_for(lambda: samples)
        assert samples[0]['function'] == 'DCV'
    finally:
        r.stop()


def test_replug(monkeypatch=None):
    """Unplug (port vanishes) -> no-device; replug -> streaming again."""
    m1, s1 = pty.openpty()
    current = {'port': os.ttyname(s1)}
    orig = R.find_port
    R.find_port = lambda: current['port']
    try:
        r, states, samples = make(None)
        assert wait_for(lambda: 'waiting' in states)
        os.close(m1)  # unplug
        os.close(s1)
        current['port'] = None
        assert wait_for(lambda: states[-1] == 'no-device')
        m2, s2 = pty.openpty()  # replug
        current['port'] = os.ttyname(s2)
        assert wait_for(lambda: states[-1] == 'waiting')
        os.write(m2, b'DMM,ACV,0.5,V,0\r\n')
        assert wait_for(lambda: states[-1] == 'streaming')
        r.stop()
    finally:
        R.find_port = orig


def test_permission_denied():
    with tempfile.NamedTemporaryFile() as f:
        os.chmod(f.name, 0)
        r, states, _ = make(f.name)
        try:
            assert wait_for(lambda: 'no-permission' in states)
        finally:
            r.stop()
