"""Read psp.cz open-data tables: pipe-separated UNL files in Windows-1250.

Every row ends with a trailing "|". Empty fields are None. Dates come in three
shapes: "06.06.1992", "2021-11-08 14" (to the hour) and "2026-11-06".
"""

import datetime as dt
import re
from collections.abc import Iterator

ENCODING = "cp1250"

_HOUR = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}))?(?::(\d{2}))?$")
_CZECH = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")


def rows(data: bytes, columns: int | None = None) -> Iterator[list[str | None]]:
    """Split a UNL table into rows of fields, empty strings as None.

    Fields can contain escaped pipes ("\\|") and line breaks ("\\" at line end).
    """
    text = data.decode(ENCODING, errors="replace")
    text = text.replace("\\\r\n", "\n").replace("\\\n", "\n")
    for line in text.splitlines():
        if not line:
            continue
        fields = [f.replace("\x00", "|") for f in line.replace("\\|", "\x00").split("|")]
        if fields and fields[-1] == "":
            fields.pop()
        if columns is not None:
            fields += [""] * (columns - len(fields))
        yield [f.strip() or None for f in fields]


def integer(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def date(value: str | None) -> dt.date | None:
    if not value:
        return None
    if m := _CZECH.match(value):
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if m := _HOUR.match(value):
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise ValueError(f"Unrecognised date {value!r}")


def timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    if m := _HOUR.match(value):
        y, mo, d, h, mi = m.groups()
        return dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))
    if day := date(value):
        return dt.datetime(day.year, day.month, day.day)
    return None


def minutes(value: str | None) -> int | None:
    """Minutes after midnight; psp.cz uses null or negative values for unknown."""
    number = integer(value)
    return number if number is not None and number >= 0 else None
