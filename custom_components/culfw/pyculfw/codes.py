"""Convert FHT80b codes between the hex form on the radio and the display numbers."""

import re
from typing import Final

from .const import FHT_CODE_PART_MIN

# On the radio, the house code of an FHT80b is four hex digits, two bytes, such as 3F48.
# The thermostat shows the same code as two numbers, one for each byte, and a user types
# those numbers on the device, so the setup asks for them. The numbers are the decimal
# value of each hex byte, never the hex digits read as decimal: 3F48 is the bytes 0x3F
# and 0x48, which is 63 and 72. The display writes each number with three digits, so it
# shows 063 as "Code 1" and 072 as "Code 2", and the code reads "063 072".
#
# The manual of the FHT 80B (85643_FHT80B_UM.pdf, chapters 1.3 and 3.9.4) says the
# security code has two parts of 100 settings each, 10,000 codes in all, and that the
# special function "CodE" takes the first and then the second part as 000 to 099, so
# each part is one number from 0 to 99. The FHEM wiki page of the FHT80b describes the
# conversion byte by byte from hex to decimal, and node-cul does the same: it reads the
# device code as two decimal pairs and sends each pair as a hex byte, which gives 3924
# on the radio for the display code 057 036. The top of the range matches too, because
# FHT_CODE_PART_MAX in const.py is 0x63, which is 99.
#
# The owner checked the mapping on the real office thermostat on 2026-10-19: the
# thermostat with the hex code 3F48 shows Code 1 = 063 and, after a confirmation with
# PROG, Code 2 = 072, as the conversion says. The other two thermostats of the
# installation, 3924 (057 036) and 5D10 (093 016), are not compared yet
# (docs/protocol.md, "Verified on hardware"). The setup still shows the converted hex
# code back to the user before it writes anything.
#
# A byte from 0x64 to 0xFF is more than 99, so no display can show it and no user can
# type it. code_to_display_pair() returns None for such a code, and format_display_code()
# falls back to the hex code, so a code from the radio is never converted wrongly.
# display_pair_to_code() accepts 0 to 99 for both numbers, as the manual does, while the
# transport takes only the bytes FHT_CODE_PART_MIN to FHT_CODE_PART_MAX as a house code,
# so the setup form offers DISPLAY_PART_MIN to DISPLAY_PART_MAX.
# The device code of an FHT80 TF contact has three bytes and is not handled here.

DISPLAY_PART_MIN: Final = FHT_CODE_PART_MIN
DISPLAY_PART_MAX: Final = 99

_HEX_CODE_RE: Final = re.compile(r"[0-9A-Fa-f]{4}")


def display_pair_to_code(first: int, second: int) -> str:
    """Return the hex code for the two numbers on the display, or raise ValueError."""
    for number in (first, second):
        if not 0 <= number <= DISPLAY_PART_MAX:
            raise ValueError(
                f"Display code numbers must be 0 to {DISPLAY_PART_MAX}, got {number}"
            )
    return f"{first:02X}{second:02X}"


def code_to_display_pair(code: str) -> tuple[int, int] | None:
    """Return the two display numbers of a hex code, or None if it has no display form.

    Raises ValueError when the code is not four hex digits.
    """
    if not _HEX_CODE_RE.fullmatch(code):
        raise ValueError(f"A code must be four hex digits, got {code!r}")
    first, second = bytes.fromhex(code)
    if first > DISPLAY_PART_MAX or second > DISPLAY_PART_MAX:
        return None
    return first, second


def format_display_code(code: str) -> str:
    """Return the code as the two display numbers, such as "063 072".

    Each number has three digits, as the display shows it. A code without a display
    form comes back as its hex digits in upper case.
    """
    pair = code_to_display_pair(code)
    if pair is None:
        return code.upper()
    return f"{pair[0]:03d} {pair[1]:03d}"
