import csv
import os
import time
from bisect import bisect_left

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
import cairo
from gi.repository import Adw, Gdk, GLib, Gtk

from . import config
from .protocol import DISPLAY_UNIT, FUNCTIONS, ICONS, to_si
from .reader import Reader

STATES = {
    'no-device': 'No device found — connect the 2D15P (mod firmware, USB Sharing off)',
    'no-permission': 'Permission denied on the serial port — install '
                     '99-fnirsi-2d15p.rules (from the 2D15P repo) or add yourself '
                     'to the plugdev/dialout group, then replug.',
    'waiting': 'Connected but no data — open the Multimeter page on the device. '
               'If it stays silent after a replug, power-cycle the device.',
    'streaming': '',
}
WINDOWS = [('30 s', 30), ('1 min', 60), ('5 min', 300), ('15 min', 900),
           ('1 h', 3600), ('6 h', 21600)]
KEEP_S = WINDOWS[-1][1]


def fmt_si(v, unit):
    unit = DISPLAY_UNIT.get(unit, unit)
    if v == 0:
        return f'0 {unit}'
    for lim, pre, div in ((1e6, 'M', 1e6), (1e3, 'k', 1e3), (1, '', 1),
                          (1e-3, 'm', 1e-3), (1e-6, 'µ', 1e-6), (1e-9, 'n', 1e-9),
                          (0, 'p', 1e-12)):
        if abs(v) >= lim:
            return f'{v / div:.4g} {pre}{unit}'


def robust_range(vals, q=0.10, reach=0.5, min_n=20):
    """Axis range that ignores outliers so a short spike doesn't flatten the trace.

    Takes the q..1-q percentile span of the data and accepts values up to
    `reach` times that span beyond it (Tukey-style fences), clipped to the true
    min/max. Normal signals keep their full range; a spike far outside the bulk
    is left off-scale. Few samples use the full range."""
    if len(vals) < min_n:
        return min(vals), max(vals)
    v = sorted(vals)
    k = int(len(v) * q)
    p_lo, p_hi = v[k], v[-1 - k]
    margin = (p_hi - p_lo) * reach
    return max(v[0], p_lo - margin), min(v[-1], p_hi + margin)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, port=None):
        super().__init__(application=app, title='FNIRSI 2D15P Multimeter',
                         default_width=640, default_height=560)
        self.cfg = config.load()
        self.ts, self.vs = [], []  # monotonic time / value (None = OL); repeats dropped
        self.streaming = False
        self.last_v = object()
        self.stats = None
        self.func = None
        self.paused = False
        self.csv_file = self.csv_w = None
        self.last_row = None

        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        self.rec = Gtk.ToggleButton(icon_name='media-record-symbolic',
                                    tooltip_text='Record to CSV')
        self.rec.connect('toggled', self.on_rec)
        self.pause = Gtk.ToggleButton(icon_name='media-playback-pause-symbolic',
                                      tooltip_text='Pause display')
        self.pause.connect('toggled', lambda b: setattr(self, 'paused', b.get_active()))
        clear = Gtk.Button(icon_name='edit-clear-all-symbolic', tooltip_text='Clear')
        clear.connect('clicked', self.on_clear)
        for w in (self.rec, self.pause, clear):
            hb.pack_start(w)
        self.win_dd = Gtk.DropDown.new_from_strings([n for n, _ in WINDOWS])
        self.win_dd.set_tooltip_text('Chart time window')
        idx = next((i for i, (_, t) in enumerate(WINDOWS) if t == self.cfg['window_s']), 1)
        self.win_dd.set_selected(idx)
        self.win_dd.connect('notify::selected', self.on_window)
        self.color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), tooltip_text='Trace colour')
        rgba = Gdk.RGBA()
        if not rgba.parse(self.cfg['color']):
            rgba.parse(config.DEFAULTS['color'])
        self.color_btn.set_rgba(rgba)
        self.color_btn.connect('notify::rgba', self.on_color)
        hb.pack_end(self.color_btn)
        hb.pack_end(self.win_dd)
        tv.add_top_bar(hb)

        self.banner = Adw.Banner(title=STATES['no-device'], revealed=True)
        tv.add_top_bar(self.banner)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=12, margin_bottom=12, margin_start=16, margin_end=16)
        self.func_lbl = Gtk.Label(label='—', css_classes=['title-3'])
        self.value = Gtk.Label(label='---', margin_top=8, css_classes=['title-1'])
        self.value.set_label('---')
        css = Gtk.CssProvider()
        css.load_from_string('.dmm-value { font-size: 60pt; font-weight: bold; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.value.add_css_class('dmm-value')
        self.value.remove_css_class('title-1')
        self.flag = Gtk.Label(label='', css_classes=['accent'])
        self.stat_lbl = Gtk.Label(label='', css_classes=['dim-label'])
        self.area = Gtk.DrawingArea(vexpand=True, content_height=200)
        self.area.set_draw_func(self.draw)
        for w in (self.func_lbl, self.value, self.flag, self.stat_lbl, self.area):
            box.append(w)
        tv.set_content(box)
        self.toasts = Adw.ToastOverlay(child=tv)
        self.set_content(self.toasts)

        self.reader = Reader(self.on_sample, self.on_state, port)
        self.reader.start()
        self.connect('close-request', self.on_close)

    # -- reader callbacks (main loop) --
    def on_state(self, s):
        self.banner.set_title(STATES[s])
        self.banner.set_revealed(s != 'streaming')
        self.streaming = s == 'streaming'
        self.area.queue_draw()

    def on_sample(self, s):
        if self.csv_w:
            row = (s['function'], s['value'], s['unit'], int(s['hold']))
            if row != self.last_row:
                self.last_row = row
                self.csv_w.writerow([time.strftime('%Y-%m-%dT%H:%M:%S')] + list(row))
                self.csv_file.flush()
        if self.paused:
            return
        v, unit = to_si(s)
        if s['function'] != self.func:
            self.func = s['function']
            self.clear_data()
            self.stats = None
            self.stat_lbl.set_label('')
        name = FUNCTIONS.get(s['function'], s['function'])
        icon = ICONS.get(s['function'])
        self.func_lbl.set_label(f'{icon}  {name}' if icon else name)
        if not s['value']:  # autoranging: no reading yet, keep the chart and stats as they are
            self.value.set_label('---')
            self.flag.set_label('HOLD' if s['hold'] else '')
            return
        now = time.monotonic()
        if v != self.last_v:  # skip the firmware's repeated lines
            self.ts.append(now)
            self.vs.append(v)
            self.last_v = v
        if self.ts and now - self.ts[0] > KEEP_S * 1.1:  # prune in batches
            k = bisect_left(self.ts, now - KEEP_S)
            del self.ts[:k], self.vs[:k]
        if v is None:
            txt = s['value']
        else:
            txt = f"{s['value']} {DISPLAY_UNIT.get(s['unit'], s['unit'])}"
            st = self.stats or [v, v, 0.0, 0]
            st = [min(st[0], v), max(st[1], v), st[2] + v, st[3] + 1]
            self.stats = st
            self.stat_lbl.set_label(
                f'min {fmt_si(st[0], unit)}   max {fmt_si(st[1], unit)}   '
                f'avg {fmt_si(st[2] / st[3], unit)}')
        self.value.set_label(txt)
        self.flag.set_label('HOLD' if s['hold'] else '')
        self.unit = unit
        self.area.queue_draw()

    # -- actions --
    def on_rec(self, b):
        if b.get_active():
            d = GLib.get_user_special_directory(GLib.UserDirectory.DIRECTORY_DOCUMENTS) \
                or os.path.expanduser('~')
            path = os.path.join(d, time.strftime('dmm-%Y%m%d-%H%M%S.csv'))
            try:
                self.csv_file = open(path, 'a', newline='')
            except OSError as e:
                b.set_active(False)
                self.toasts.add_toast(Adw.Toast(title=f'Cannot record: {e.strerror}'))
                return
            self.csv_w = csv.writer(self.csv_file)
            self.csv_w.writerow(['time', 'function', 'value', 'unit', 'hold'])
            self.last_row = None
            b.set_tooltip_text(f'Recording to {path}')
            self.toasts.add_toast(Adw.Toast(title=f'Recording to {path}'))
        elif self.csv_file:
            self.csv_file.close()
            self.csv_file = self.csv_w = None
            b.set_tooltip_text('Record to CSV')
            self.toasts.add_toast(Adw.Toast(title='Recording stopped'))

    def on_window(self, dd, _p):
        self.cfg['window_s'] = WINDOWS[dd.get_selected()][1]
        config.save(self.cfg)
        self.area.queue_draw()

    def on_color(self, btn, _p):
        self.cfg['color'] = btn.get_rgba().to_string()
        config.save(self.cfg)
        self.area.queue_draw()

    def clear_data(self):
        self.ts.clear()
        self.vs.clear()
        self.last_v = object()

    def on_clear(self, _b):
        self.clear_data()
        self.stats = None
        self.stat_lbl.set_label('')
        self.area.queue_draw()

    def on_close(self, *_):
        self.reader.stop()
        if self.csv_file:
            self.csv_file.close()
        return False

    # -- chart --
    def draw(self, area, cr, w, h):
        fg = area.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        span_t = self.cfg['window_s']
        now = time.monotonic()
        t0 = now - span_t
        i0 = max(bisect_left(self.ts, t0) - 1, 0)  # one point before the window
        ts, vs = self.ts[i0:], self.vs[i0:]
        vis = [v for t, v in zip(ts, vs) if v is not None and t >= t0]
        if not vis:
            return
        true_lo, true_hi = min(vis), max(vis)
        lo, hi = robust_range(vis)
        span = (hi - lo) or max(abs(hi), 1e-9) * 0.1
        lo, hi = lo - span * 0.1, hi + span * 0.1
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.set_line_width(1)
        for k in range(1, 4):
            cr.move_to(0, h * k / 4)
            cr.line_to(w, h * k / 4)
        cr.stroke()
        rgba = self.color_btn.get_rgba()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.set_line_width(2)
        cr.set_line_join(cairo.LineJoin.ROUND)
        cr.rectangle(0, 0, w, h)
        cr.clip()

        def y_of(v):
            return h - (v - lo) / (hi - lo) * h

        # decimate to <= 4 points per pixel column (first, min, max, last)
        started = False
        col, bucket = None, []

        def flush():
            nonlocal started
            if not bucket:
                return
            x = (bucket[0][0] - t0) / span_t * w
            ys = [y_of(v) for _, v in bucket]
            for y in (ys[0], max(ys), min(ys), ys[-1]):
                cr.line_to(x, y) if started else cr.move_to(x, y)
                started = True

        for t, v in zip(ts, vs):
            if v is None:
                flush()
                bucket, col, started = [], None, False
                continue
            c = int((t - t0) / span_t * w)
            if c != col:
                flush()
                bucket, col = [], c
            bucket.append((t, v))
        flush()
        if started and self.streaming:  # extend last value to "now"
            cr.line_to(w, y_of(bucket[-1][1]))
        cr.stroke()
        cr.reset_clip()
        unit = getattr(self, 'unit', '')
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.9)
        cr.set_font_size(11)
        cr.move_to(4, 12)
        cr.show_text(fmt_si(hi, unit))
        cr.move_to(4, h - 4)
        cr.show_text(fmt_si(lo, unit))
        # points outside the scaled range run off the chart: say so, with the true extreme
        def marker(y, up, txt):
            cr.move_to(4, y + (-1 if up else 1) * 4)  # small triangle drawn as a path
            cr.line_to(12, y + (-1 if up else 1) * 4)
            cr.line_to(8, y + (1 if up else -1) * 4)
            cr.close_path()
            cr.fill()
            cr.move_to(17, y + 4)
            cr.show_text(txt)

        if true_hi > hi:
            marker(22, False, fmt_si(true_hi, unit))
        if true_lo < lo:
            marker(h - 22, True, fmt_si(true_lo, unit))
        label = f'{span_t // 60} min' if span_t >= 60 else f'{span_t} s'
        ext = cr.text_extents(label)
        cr.move_to(w - ext.width - 4, h - 4)
        cr.show_text(label)

