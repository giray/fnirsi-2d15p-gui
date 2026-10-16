import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fnirsi_dmm_gui.protocol import parse, to_si


def test_parse_number():
    s = parse('DMM,DCV,12.345,V,0\r\n')
    assert s == {'function': 'DCV', 'value': '12.345', 'unit': 'V', 'hold': False}
    assert to_si(s) == (12.345, 'V')


def test_ol_and_hold():
    s = parse('DMM,RES,OL,Ohm,1')
    assert s['hold'] and to_si(s) == (None, 'Ohm')


def test_units():
    assert to_si(parse('DMM,DCV,500,mV,0')) == (0.5, 'V')


def test_malformed():
    assert parse('IDN') is None and parse('DMM,a,b') is None


def test_formatting():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from fnirsi_dmm_gui.window import fmt_si
    assert fmt_si(0, 'V') == '0 V'
    assert fmt_si(0.0005, 'V') == '500 µV' or fmt_si(0.0005, 'V') == '500 µV'
    assert fmt_si(1500, 'Ohm') == '1.5 kΩ'
    assert fmt_si(21.5, 'degC') == '21.5 ℃'


def test_firmware_quirks():
    assert parse('DMM,RES,.OL,MOhm,0')['value'] == '.OL'  # shown as the device shows it
    assert to_si(parse('DMM,RES,.OL,MOhm,0')) == (None, 'Ohm')
    assert parse('DMM,RES, ,kOhm,0')['value'] == ''


def test_robust_range():
    from fnirsi_dmm_gui.window import robust_range
    # noise around 0 with a 6-sample spike to 4 V: spike is left off-scale
    noisy = [0.001 * (i % 7) for i in range(100)] + [4.0] * 6
    lo, hi = robust_range(noisy)
    assert hi < 0.02 and lo == 0
    # a normal wide signal keeps its full range
    ramp = [float(i) for i in range(100)]
    assert robust_range(ramp) == (0.0, 99.0)
    assert robust_range([1.0, 5.0]) == (1.0, 5.0)  # too few points: full range
