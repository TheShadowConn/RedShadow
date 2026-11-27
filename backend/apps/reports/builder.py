"""Collects what a report shows. Everything starts at the requester's own scoped selectors, so a report can never
contain a finding its requester could not open in the app. Drafts are never included. Technical details, proof of
concept and technical notes only appear in internal reports for people who hold ``finding_notes.technical``."""

import base64
import io
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from PIL import Image

from apps.core.markdown import render_markdown
from apps.core.storage import get_storage
from apps.engagements.models import Engagement, EngagementScenario
from apps.files.models import Attachment
from apps.findings import lifecycle
from apps.findings.models import SEVERITIES, STATUSES, FindingNote, RemediationActivity, RetestRound
from apps.findings.selectors import scope_findings, with_severity_rank
from apps.organisations import tags as asset_tags
from apps.organisations.models import Asset
from apps.rbac.authz import engagement_permissions

from . import charts

MAX_FINDINGS = 500
MAX_IMAGES_PER_FINDING = 3
MAX_IMAGES_TOTAL = 60
MAX_IMAGE_EDGE = 1400
IMAGE_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp")
DEFAULT_STATUSES = ["open", "in_progress", "pending_verification", "reopened", "closed", "risk_accepted"]
REPORTABLE_STATUSES = [key for key, _ in STATUSES if key != "draft"]
OPEN_STATUSES = ("open", "in_progress", "pending_verification", "reopened")
STATUS_LABELS = dict(STATUSES)
SEVERITY_KEYS = [key for key, _ in SEVERITIES]
RISK_LABELS = {
    "critical": "Critical", "high": "High", "medium": "Moderate", "low": "Low", "info": "Minimal",
}  # fmt: skip


class ReportRefused(Exception):
    """The report cannot be built as asked; the message is shown to the user."""


def normalise_filters(raw: dict | None) -> dict:
    raw = raw or {}
    severities = [s for s in raw.get("severities") or [] if s in SEVERITY_KEYS]
    statuses = [s for s in raw.get("statuses") or [] if s in REPORTABLE_STATUSES]
    clean = {"severities": severities, "statuses": statuses or list(DEFAULT_STATUSES)}
    wanted = [t.strip() for t in raw.get("tags") or [] if isinstance(t, str) and t.strip()]
    return {**clean, "tags": wanted} if wanted else clean


def _image_data_uri(key: str) -> str | None:
    """Re-encode stored evidence as a bounded JPEG so the PDF stays small and carries no stray metadata."""
    try:
        with Image.open(io.BytesIO(get_storage().read(key))) as img:
            img.load()
            frame = img.convert("RGBA")
            flat = Image.new("RGB", frame.size, "white")
            flat.paste(frame, mask=frame.getchannel("A"))
            flat.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            out = io.BytesIO()
            flat.save(out, "JPEG", quality=80, optimize=True)
    except Exception:  # noqa: BLE001 - a broken or missing image is left out, never fails the report
        return None
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def _evidence(finding_ids, allowed: bool) -> dict:
    if not allowed:
        return {}
    found: dict = {}
    total = 0
    rows = Attachment.objects.filter(
        kind="evidence",
        finding_id__in=finding_ids,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        mime__in=IMAGE_MIMES,
    ).order_by("finding_id", "created_at")
    for att in rows:
        bucket = found.setdefault(att.finding_id, [])
        if len(bucket) >= MAX_IMAGES_PER_FINDING or total >= MAX_IMAGES_TOTAL:
            continue
        uri = _image_data_uri(att.storage_key)
        if uri:
            bucket.append({"name": att.original_name, "src": uri})
            total += 1
    return found


def _scenarios(eng: Engagement, allowed: bool) -> list[dict]:
    """Scenario list for the report: what was tested, what is still to come. Pictures are bounded like evidence."""
    if not allowed:
        return []
    rows = list(EngagementScenario.objects.filter(engagement=eng).order_by("position", "created_at"))
    pictures: dict = {}
    total = 0
    images = Attachment.objects.filter(
        kind="scenario_image", scenario__in=rows, deleted_at__isnull=True, purged_at__isnull=True, mime__in=IMAGE_MIMES
    ).order_by("scenario_id", "created_at")
    for att in images:
        bucket = pictures.setdefault(att.scenario_id, [])
        if len(bucket) >= MAX_IMAGES_PER_FINDING or total >= MAX_IMAGES_TOTAL:
            continue
        uri = _image_data_uri(att.storage_key)
        if uri:
            bucket.append({"name": att.original_name, "src": uri})
            total += 1
    return [
        {
            "name": r.name, "status": r.status, "status_label": r.get_status_display(),
            "planned_start": r.planned_start, "planned_end": r.planned_end, "completed_on": r.completed_on,
            "reason": r.status_reason, "description_html": render_markdown(r.description),
            "pending": r.status in ("planned", "in_progress", "deferred"), "images": pictures.get(r.pk, []),
        }
        for r in rows
    ]  # fmt: skip


def _roadmap(findings: list[dict], today) -> list[dict]:
    groups = [
        ("Overdue", "Past the remediation date set by the SLA."),
        ("Due within 7 days", ""),
        ("Due within 30 days", ""),
        ("Due later", ""),
        ("No date set", "No remediation date is recorded."),
    ]
    buckets: list[list[dict]] = [[] for _ in groups]
    for f in findings:
        if f["status"] not in OPEN_STATUSES:
            continue
        due = f["due_date"]
        if due is None:
            buckets[4].append(f)
        elif due < today:
            buckets[0].append(f)
        elif due <= today + timedelta(days=7):
            buckets[1].append(f)
        elif due <= today + timedelta(days=30):
            buckets[2].append(f)
        else:
            buckets[3].append(f)
    return [{"title": t, "hint": h, "rows": rows} for (t, h), rows in zip(groups, buckets, strict=True) if rows]


def collect(job, actor) -> dict:
    """Everything the PDF and the CSV need. Re-checks the requester's rights at run time."""
    eng: Engagement = Engagement.objects.select_related("organisation", "lead").get(pk=job.engagement_id)
    perms = engagement_permissions(actor, eng.pk)
    internal = job.audience == "internal"
    if internal and "finding_notes.technical" not in perms:
        raise ReportRefused("Internal reports need access to technical details on this engagement.")
    filters = normalise_filters(job.filters)

    qs = scope_findings(actor).filter(engagement=eng).exclude(status="draft").filter(status__in=filters["statuses"])
    if filters["severities"]:
        qs = qs.filter(severity__in=filters["severities"])
    if filters.get("tags"):
        on = Asset.objects.filter(pk__in=qs.values("asset_id"))
        qs = qs.filter(asset_id__in={pk for tag in filters["tags"] for pk in asset_tags.ids_with_tag(on, tag)})
    total = qs.count()
    if total > MAX_FINDINGS:
        raise ReportRefused(f"{total} findings match. Narrow the filters to {MAX_FINDINGS} or fewer.")
    qs = (
        with_severity_rank(qs)
        .select_related("asset", "cwe", "assigned_pentester", "remediation_owner", "verified_by")
        .order_by("-severity_rank", F("cvss_score").desc(nulls_last=True), "ref")
    )
    rows = list(qs)
    ids = [f.pk for f in rows]
    today = timezone.localdate()

    activities: dict = {}
    for a in (
        RemediationActivity.objects.filter(finding_id__in=ids).select_related("actor").order_by("created_at", "id")
    ):
        activities.setdefault(a.finding_id, []).append(a)
    tech_notes: dict = {}
    if internal:
        for n in (
            FindingNote.objects.filter(finding_id__in=ids, kind="technical")
            .select_related("author")
            .order_by("created_at")
        ):
            tech_notes.setdefault(n.finding_id, []).append(n)
    evidence = _evidence(ids, "evidence.view" in perms)

    findings = []
    for f in rows:
        item = {
            "id": str(f.pk),
            "ref": f.ref,
            "title": f.title,
            "severity": f.severity,
            "severity_label": charts.SEVERITY_LABELS[f.severity],
            "cvss_score": f.cvss_score,
            "cvss_vector": f.cvss_vector,
            "cwe": f"CWE-{f.cwe_id} {f.cwe.name}" if f.cwe_id else "",
            "status": f.status,
            "status_label": STATUS_LABELS[f.status],
            "asset": f.asset.name if f.asset_id else "",
            "asset_tags": "; ".join(f.asset.tags) if f.asset_id else "",
            "endpoint": f.endpoint,
            "discovered_at": f.discovered_at,
            "due_date": f.due_date,
            "resolved_at": f.resolved_at,
            "verified_at": f.verified_at,
            "closed_at": f.closed_at,
            "assigned_pentester": f.assigned_pentester.display_name if f.assigned_pentester_id else "",
            "remediation_owner": f.remediation_owner.display_name if f.remediation_owner_id else "",
            "overdue": bool(f.due_date and f.due_date < today and f.status in lifecycle.OVERDUE_STATUSES),
            "description_html": render_markdown(f.description),
            "recommendation_html": render_markdown(f.recommendation),
            "references": [
                {"label": str(r.get("label", ""))[:120], "url": str(r.get("url", ""))[:500]}
                for r in (f.references or [])
                if isinstance(r, dict) and r.get("url")
            ][:20],
            "evidence": evidence.get(f.pk, []),
            "timeline": [
                {
                    "at": a.created_at,
                    "label": a.get_action_display(),
                    "who": a.actor.display_name if a.actor_id else "System",
                    "note_html": render_markdown(a.note) if a.note and a.action != "comment" else "",
                }
                for a in activities.get(f.pk, [])
                if a.action != "comment"
            ][-12:],
            "internal": None,
            "risk_accept": f.risk_acceptance_reason
            and f.status == "risk_accepted"
            and {"until": f.risk_accepted_until, "reason_html": render_markdown(f.risk_acceptance_reason)}
            or None,
        }
        if internal:
            item["internal"] = {
                "technical_html": render_markdown(f.technical_details),
                "poc_html": render_markdown(f.poc),
                "notes": [
                    {"at": n.created_at, "who": n.author.display_name, "body_html": render_markdown(n.body)}
                    for n in tech_notes.get(f.pk, [])
                ],
            }
        findings.append(item)

    by_sev = Counter(f["severity"] for f in findings)
    by_status = Counter(f["status"] for f in findings)
    open_sev = Counter(f["severity"] for f in findings if f["status"] in OPEN_STATUSES)
    status_keys = [k for k, _ in STATUSES if by_status.get(k)]
    matrix = [
        {
            "severity": s,
            "label": charts.SEVERITY_LABELS[s],
            "cells": [sum(1 for f in findings if f["severity"] == s and f["status"] == st) for st in status_keys],
            "total": by_sev.get(s, 0),
        }
        for s in charts.SEVERITY_ORDER
    ]
    risk = next((RISK_LABELS[s] for s in charts.SEVERITY_ORDER if open_sev.get(s)), "Minimal")
    risk_key = next((s for s in charts.SEVERITY_ORDER if open_sev.get(s)), "info")
    open_total = sum(open_sev.values())
    closed_total = by_status.get("closed", 0)

    rounds = []
    for rnd in (
        RetestRound.objects.filter(engagement=eng, items__finding_id__in=ids)
        .distinct()
        .select_related("assessor")
        .order_by("number")
    ):
        items = [i for i in rnd.items.select_related("finding") if i.finding_id in set(ids)]
        results = Counter(i.result for i in items)
        rounds.append(
            {
                "ref": rnd.ref,
                "status": rnd.get_status_display(),
                "assessor": rnd.assessor.display_name,
                "completed_at": rnd.completed_at,
                "created_at": rnd.created_at,
                "passed": results.get("passed", 0),
                "failed": results.get("failed", 0),
                "pending": results.get("pending", 0) + results.get("not_tested", 0),
                "items": [
                    {"ref": i.finding.ref, "title": i.finding.title, "result": i.get_result_display()} for i in items
                ],
            }
        )

    team = [
        {"name": m.user.display_name, "role": (m.role_override or m.user.role).name}
        for m in eng.memberships.select_related("user", "role_override", "user__role").order_by("user__display_name")
    ]
    assets = [
        {
            "name": ea.asset.name,
            "type": ea.asset.get_type_display(),
            "identifier": ea.asset.identifier,
            "identifiers": [i.value for i in ea.asset.identifiers.all()]
            or ([ea.asset.identifier] if ea.asset.identifier else []),
            "environment": ea.asset.get_environment_display(),
            "in_scope": ea.in_scope,
        }
        for ea in eng.engagement_assets.select_related("asset")
        .prefetch_related("asset__identifiers")
        .order_by("-in_scope", "asset__name")
    ]

    scenario_rows = _scenarios(eng, "engagement_scenarios.view" in perms)
    return {
        "job": job,
        "scenarios": scenario_rows,
        "scenarios_pending": sum(1 for r in scenario_rows if r["pending"]),
        "scenarios_tested": sum(1 for r in scenario_rows if r["status"] == "tested"),
        "engagement": eng,
        "organisation": eng.organisation,
        "title": job.title or f"{eng.get_type_display()} penetration test",
        "internal": internal,
        "generated_at": timezone.now(),
        "today": today,
        "prepared_by": actor.display_name,
        "filters": filters,
        "filter_text": "; ".join(
            part
            for part in (
                "severity " + ", ".join(charts.SEVERITY_LABELS[x] for x in filters["severities"])
                if filters["severities"]
                else "",
                "status " + ", ".join(STATUS_LABELS[x] for x in filters["statuses"]),
                "department " + ", ".join(filters["tags"]) if filters.get("tags") else "",
            )
            if part
        ),
        "findings": findings,
        "raw_findings": rows,
        "key_findings": [f for f in findings if f["status"] in OPEN_STATUSES][:5],
        "totals": {
            "all": len(findings),
            "open": open_total,
            "closed": closed_total,
            "overdue": sum(1 for f in findings if f["overdue"]),
        },
        "severity_counts": [
            (s, charts.SEVERITY_LABELS[s], by_sev.get(s, 0), open_sev.get(s, 0)) for s in charts.SEVERITY_ORDER
        ],
        "status_keys": status_keys,
        "status_headers": [STATUS_LABELS[k] for k in status_keys],
        "matrix": matrix,
        "risk_label": risk,
        "risk_key": risk_key,
        "severity_chart": charts.severity_bars({s: by_sev.get(s, 0) for s in charts.SEVERITY_ORDER}),
        "status_chart": charts.status_strip({k: by_status[k] for k in status_keys}, STATUS_LABELS),
        "roadmap": _roadmap(findings, today),
        "retests": rounds,
        "team": team,
        "assets": assets,
        "scope_html": render_markdown(eng.scope),
        "out_of_scope_html": render_markdown(eng.out_of_scope),
        "objectives_html": render_markdown(eng.objectives),
        "methodology_html": render_markdown(eng.methodology),
        "rules_html": render_markdown(eng.rules_of_engagement),
        "sla_days": [(charts.SEVERITY_LABELS[k], settings.SLA_DAYS[k]) for k in ("critical", "high", "medium", "low")],
    }
