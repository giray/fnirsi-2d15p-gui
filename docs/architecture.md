# Architecture and protocol

## Stream protocol

Provided by the `dmm-stream` patch in
[fnirsi-2d15p-mod](https://github.com/giray/fnirsi-2d15p-mod). USB CDC ACM, VID `0416`,
PID `50A1`. While the multimeter page is shown and a host has the port open, the
device sends ASCII lines:

    DMM,<function>,<value>,<unit>,<hold 0|1>\r\n

Observed quirks (handled in `protocol.py`):

- Overload is `.OL` (with a leading dot, as on the device screen).
- While the meter autoranges the value is blank (`DMM,RES, ,kOhm,0`).
- Identical lines repeat on every firmware loop pass.
- After a USB reconnect the firmware may stay silent until the device is power-cycled.

The GUI never sends anything. Per the mod repository's `SAFETY.md`, the only command the
device should ever receive is `*IDN?`; commands starting with `CAL:` change calibration.

## Modules

| File | Role |
|---|---|
| `fnirsi_dmm_gui/protocol.py` | Line parser, unit normalisation to SI, display units and function icons. No GTK dependency. |
| `fnirsi_dmm_gui/reader.py` | Thread that finds the port, reads lines and reports `no-device`, `no-permission`, `waiting` or `streaming`. Results reach the UI through a `dispatch` callable (`GLib.idle_add` by default), which is what makes it testable. |
| `fnirsi_dmm_gui/window.py` | Adwaita window, Cairo chart (decimated to at most four points per pixel column), CSV recording. |
| `fnirsi_dmm_gui/config.py` | JSON settings. |
| `fnirsi_dmm_gui/app.py` | `Adw.Application` and the command line. |

## Tests

`tests/test_protocol.py` covers parsing and formatting. `tests/test_reader.py` runs the
reader against pseudo-terminals: streaming, going quiet, split lines, replug,
permission denied, and a check that the reader writes nothing.
