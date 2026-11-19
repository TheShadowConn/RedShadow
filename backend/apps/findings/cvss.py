"""Server-side CVSS scoring. The client never supplies a score: only a vector, scored here."""

from decimal import Decimal

from cvss import CVSS3, CVSS4

PREFIXES = {"CVSS:3.1/": "3.1", "CVSS:4.0/": "4.0"}


class InvalidVector(ValueError):
    pass


# CVSS base score bands, highest first: (lowest score of the band, severity). Shown in the UI and the manual.
BANDS = [(Decimal("9.0"), "critical"), (Decimal("7.0"), "high"), (Decimal("4.0"), "medium"), (Decimal("0.1"), "low")]


def severity_for(score: Decimal) -> str:
    return next((name for floor, name in BANDS if score >= floor), "info")


def score_vector(vector: str) -> tuple[str, Decimal, str]:
    """Return (version, base score, severity). Raises InvalidVector."""
    vector = (vector or "").strip()
    version = next((v for p, v in PREFIXES.items() if vector.startswith(p)), None)
    if version is None:
        raise InvalidVector("Use a CVSS 3.1 or 4.0 vector, for example CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H.")
    try:
        if version == "3.1":
            score = Decimal(str(CVSS3(vector).scores()[0]))
        else:
            score = Decimal(str(CVSS4(vector).base_score))
    except Exception:  # the library raises several malformed-vector error types
        raise InvalidVector("This is not a valid CVSS vector.") from None
    return version, score, severity_for(score)
