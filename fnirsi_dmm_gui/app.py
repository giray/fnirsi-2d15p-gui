import argparse
import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw

from .window import MainWindow


class App(Adw.Application):
    def __init__(self, port=None):
        super().__init__(application_id='org.fnirsi.DMM')
        self.port = port

    def do_activate(self):
        (self.props.active_window or MainWindow(self, self.port)).present()


def main():
    ap = argparse.ArgumentParser(description='FNIRSI 2D15P multimeter live view')
    ap.add_argument('--port', help='serial device (default: auto-detect)')
    a, rest = ap.parse_known_args()
    return App(a.port).run([sys.argv[0]] + rest)
