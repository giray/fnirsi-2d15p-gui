import json
import os

PATH = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')),
                    'fnirsi-dmm-gui', 'config.json')
DEFAULTS = {'window_s': 60, 'color': '#33d17a'}


def load():
    try:
        with open(PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg):
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, 'w') as f:
            json.dump(cfg, f)
    except OSError:
        pass
