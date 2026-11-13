"""CSV output shared by the audit and findings exports. Cells a spreadsheet could run as a formula are neutralised."""

import csv
import hashlib
import tempfile

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Text starting with = + - @ (or a tab or carriage return) gets a leading apostrophe."""
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def write_csv(header, rows):
    """Write header and rows to a temporary file. Returns (file object at 0, sha256 hex, row count).
    The caller hands the file to a response, which closes it."""
    out = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")  # noqa: SIM115 - closed by the response
    digest = hashlib.sha256()
    count = 0

    class _Sink:
        def write(self, text: str) -> int:
            raw = text.encode("utf-8")
            digest.update(raw)
            out.write(raw)
            return len(text)

    writer = csv.writer(_Sink(), lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
        count += 1
    out.seek(0)
    return out, digest.hexdigest(), count
