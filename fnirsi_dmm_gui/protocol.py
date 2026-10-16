"""Parser for the FNIRSI 2D15P `dmm-stream` line protocol (read-only)."""

FUNCTIONS = {
    'DCV': 'DC Voltage', 'ACV': 'AC Voltage', 'RES': 'Resistance',
    'CONT': 'Continuity', 'DIODE': 'Diode', 'IND': 'Inductance',
    'CAP': 'Capacitance', 'DCMA': 'DC mA', 'ACMA': 'AC mA',
    'DCA': 'DC Current', 'ACA': 'AC Current', 'TEMP': 'Temperature',
    'FREQ': 'Frequency', 'NCV': 'NCV', 'LIVE': 'Live wire',
    'AUTO': 'Auto', 'TEST': 'Test',
}

# unit string -> (SI base unit, multiplier)
UNITS = {
    'mV': ('V', 1e-3), 'V': ('V', 1.0),
    'Ohm': ('Ohm', 1.0), 'kOhm': ('Ohm', 1e3), 'MOhm': ('Ohm', 1e6),
    'nH': ('H', 1e-9), 'uH': ('H', 1e-6), 'mH': ('H', 1e-3), 'H': ('H', 1.0),
    'nF': ('F', 1e-9), 'uF': ('F', 1e-6), 'mF': ('F', 1e-3), 'F': ('F', 1.0),
    'uA': ('A', 1e-6), 'mA': ('A', 1e-3), 'A': ('A', 1.0),
    'degC': ('degC', 1.0), 'degF': ('degF', 1.0),
    'Hz': ('Hz', 1.0), 'kHz': ('Hz', 1e3), 'MHz': ('Hz', 1e6),
}


def parse(line):
    """Return dict(function, value, unit, hold) or None for non-DMM lines."""
    p = line.strip().split(',')
    if len(p) != 5 or p[0] != 'DMM':
        return None
    value = p[2].strip()  # blank while the firmware autoranges
    return {'function': p[1], 'value': value, 'unit': p[3], 'hold': p[4] == '1'}


def to_si(sample):
    """Return (value_in_SI, si_unit) or (None, unit) for OL / token values."""
    unit, mult = UNITS.get(sample['unit'], (sample['unit'], 1.0))
    try:
        return float(sample['value']) * mult, unit
    except ValueError:
        return None, unit


# Glyphs matching the device's own function icons (UTF-8, no images)
ICONS = {
    'DCV': 'V\u2393', 'ACV': 'V~', 'RES': '\u03a9', 'CONT': '\u2022)))',
    'DIODE': '\u25b7|', 'IND': '\u2112', 'CAP': '\u22a3\u22a2',
    'DCMA': 'mA\u2393', 'ACMA': 'mA~', 'DCA': 'A\u2393', 'ACA': 'A~',
    'TEMP': '\u2103', 'FREQ': 'Hz', 'NCV': 'NCV', 'LIVE': '\u26a1',
    'AUTO': '\u24b6', 'TEST': '\u2713',
}

# device unit string -> display string
DISPLAY_UNIT = {'Ohm': '\u03a9', 'kOhm': 'k\u03a9', 'MOhm': 'M\u03a9',
                'uA': '\u00b5A', 'uF': '\u00b5F', 'uH': '\u00b5H',
                'degC': '\u2103', 'degF': '\u2109'}
