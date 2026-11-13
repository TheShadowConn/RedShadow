"""Read an uploaded CSV safely. Nothing in the file is ever executed or evaluated."""

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 60
MAX_CELL = 100_000
EXTENSIONS = {"csv", "txt", "tsv"}


class ParseError(Exception):
    """The file cannot be used. The message is shown to the user as written."""


@dataclass
class Parsed:
    encoding: str
    delimiter: str
    headers: list[str]
    rows: Iterator[tuple[int, list[str]]]  # (line number, cells padded to the header width)


def decode(data: bytes) -> tuple[str, str]:
    if not data:
        raise ParseError("The file is empty.")
    if b"\x00" in data:
        raise ParseError("This does not look like a CSV text file.")
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252"), "windows-1252"
    except UnicodeDecodeError:
        raise ParseError("The file is not UTF-8 or Windows-1252 text. Save it as CSV (UTF-8) and try again.") from None


def sniff(text: str) -> str:
    head = text[:4096]
    try:
        return csv.Sniffer().sniff(head, delimiters=",;\t").delimiter
    except csv.Error:
        first = head.splitlines()[0] if head else ""
        return max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","


def parse(data: bytes) -> Parsed:
    if len(data) > MAX_BYTES:
        raise ParseError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    text, encoding = decode(data)
    head = text[:2048].lstrip().lower()
    if head.startswith(("<!doctype html", "<html", "<svg", "<?xml")):
        raise ParseError("This is not a CSV file.")
    delimiter = sniff(text)
    csv.field_size_limit(MAX_CELL)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        raise ParseError("The file is empty.") from None
    except csv.Error as exc:
        raise ParseError(f"The file is not valid CSV: {exc}.") from None
    headers = [h.strip() for h in headers]
    if not any(headers):
        raise ParseError("The first row must hold the column names.")
    if len(headers) > MAX_COLUMNS:
        raise ParseError(f"The file has {len(headers)} columns. The limit is {MAX_COLUMNS}.")
    for i, h in enumerate(headers, 1):
        if not h:
            raise ParseError(f"Column {i} has no name in the first row.")
    if len({h.lower() for h in headers}) != len(headers):
        dup = next(h for h in headers if [x.lower() for x in headers].count(h.lower()) > 1)
        raise ParseError(f"Two columns are both named {dup!r}. Rename one and try again.")

    def rows():
        count = 0
        try:
            for cells in reader:
                if not any(c.strip() for c in cells):
                    continue  # blank line
                count += 1
                if count > MAX_ROWS:
                    raise ParseError(f"The file has more than {MAX_ROWS:,} rows. Split it and import the parts.")
                yield (
                    reader.line_num,
                    cells + [""] * (len(headers) - len(cells)) if len(cells) < len(headers) else cells,
                )
        except csv.Error as exc:
            raise ParseError(f"The file is not valid CSV near line {reader.line_num}: {exc}.") from None

    return Parsed(encoding=encoding, delimiter=delimiter, headers=headers, rows=rows())
