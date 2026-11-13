"""Column set of the findings CSV export."""

MAX_ROWS = 50_000
COLUMNS = [
    "reference",
    "engagement",
    "engagement_name",
    "title",
    "severity",
    "cvss_score",
    "cvss_vector",
    "status",
    "asset",
    "endpoint",
    "cwe",
    "assigned_pentester",
    "remediation_owner",
    "discovered_at",
    "due_date",
    "created_at",
    "description",
    "recommendation",
    "technical_details",
    "poc",
    "references",
]


def row(f) -> list:
    return [
        f.ref,
        f.engagement.ref,
        f.engagement.name,
        f.title,
        f.severity,
        f.cvss_score if f.cvss_score is not None else "",
        f.cvss_vector,
        f.status,
        f.asset.name if f.asset_id else "",
        f.endpoint,
        f"CWE-{f.cwe_id}" if f.cwe_id else "",
        f.assigned_pentester.email if f.assigned_pentester_id else "",
        f.remediation_owner.email if f.remediation_owner_id else "",
        f.discovered_at.isoformat(),
        f.due_date.isoformat() if f.due_date else "",
        f.created_at.isoformat(),
        f.description,
        f.recommendation,
        f.technical_details,
        f.poc,
        "; ".join(f"{r.get('label', '')}|{r.get('url', '')}" for r in f.references),
    ]
