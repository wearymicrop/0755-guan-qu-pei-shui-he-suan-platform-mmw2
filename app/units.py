import re
import unicodedata
from fractions import Fraction

UNIT_SCALE = {"L": 1, "m3": 1000, "m³": 1000}
VOLUME = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?")


def liters(value, unit):
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if unit not in UNIT_SCALE or not VOLUME.fullmatch(text):
        raise ValueError("水量或单位无效")
    exact = Fraction(text.replace(",", "")) * UNIT_SCALE[unit]
    if exact.denominator != 1 or exact > 10**12:
        raise ValueError("水量超出整升范围")
    return int(exact)


def integer(value, low=0, high=10**9):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("整数越界")
    return value
