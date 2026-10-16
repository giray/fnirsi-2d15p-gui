# Usage

## Window

| Control | Action |
|---|---|
| ● (record) | Start/stop CSV recording to `~/Documents/dmm-<timestamp>.csv`. A toast shows the path; failures (e.g. unwritable folder) are reported and recording stays off. |
| ⏸ (pause) | Freeze the display. CSV recording continues. |
| ⌫ (clear) | Clear the chart and min/max/avg. |
| Time-window drop-down | 30 s, 1 min, 5 min, 15 min, 1 h or 6 h. History of up to 6 h is always kept, so widening the window shows older data immediately. |
| Colour button | Trace colour. |

Switching the device to a different function clears the chart and statistics
(they would otherwise mix units).

## CSV format

`time,function,value,unit,hold` with an ISO-8601 timestamp. Consecutive identical readings
are collapsed. `value` is the device's own text, so it can be `.OL` for overload.

## Settings

`~/.config/fnirsi-dmm-gui/config.json` holds `window_s` and `color`. Delete the
file to reset.
