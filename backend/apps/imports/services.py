"""CSV import: upload, map, validate, commit. Every step checks the caller's rights on the job's target:
the engagement for a findings import, the organisation (``assets.import``) for an assets import.

Findings an import creates are always drafts. Assets an import creates are not onboarded. Heavy work
(reading, checking, inserting) runs in the worker on the ``imports`` queue; the functions ending in
``_job`` and ``run_import`` are what the tasks call.

A failed, previewed or partly failed import can take a corrected file (`reupload`) into the same job:
that opens a new attempt. Re-running is duplicate-safe because findings are matched by their dedupe hash
and assets by their identifiers, so rows that already went in are recognised and skipped.
"""

import datetime
import hashlib
import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.core.storage import get_storage
from apps.engagements.models import Engagement, EngagementAsset
from apps.findings import cvss
from apps.findings.models import Finding
from apps.findings.selectors import scope_findings
from apps.findings.services import reserve_refs
from apps.organisations import assets as asset_ops
from apps.organisations import identifiers as ident
from apps.organisations.models import Asset, Organisation
from apps.rbac.authz import has_engagement_perm, has_platform_perm

from . import parsing
from .asset_import import AssetRowValidator, Matcher, describe
from .mapping import clean_mapping
from .models import ImportAttempt, ImportJob, ImportMapping, ImportRow
from .validation import RowValidator, is_recoverable

log = logging.getLogger(__name__)

CHUNK = 500
STALE = timedelta(minutes=30)
FILE_RETENTION = timedelta(days=30)


class ImportAbort(Exception):
    """Raised inside the commit transaction to roll everything back with a message for the user."""


def _enqueue(task_name: str, job_id) -> None:
    from . import tasks

    getattr(tasks, task_name).apply_async((str(job_id),), queue="imports")


def _deny(request, job_or_eng, action: str, reason: str, engagement=None):
    audit.record(
        action,
        request=request,
        entity=job_or_eng,
        engagement=engagement or getattr(job_or_eng, "engagement", None),
        outcome="denied",
        metadata={"reason": reason},
    )
    raise PermissionDenied(reason)


def can_import(actor, job: ImportJob) -> bool:
    if job.kind == "assets":
        return has_platform_perm(actor, "assets.import")
    return has_engagement_perm(actor, job.engagement_id, "imports.create")


def _require_create(request, actor, job: ImportJob, action: str) -> None:
    if not can_import(actor, job):
        where = "your organisation's assets" if job.kind == "assets" else "this engagement"
        _deny(request, job, action, f"You do not have permission to import into {where}.")


def _lock(job: ImportJob) -> ImportJob:
    """The job, locked for this transaction, with its target loaded (the joins are nullable: lock only the job)."""
    return ImportJob.objects.select_for_update(of=("self",)).select_related("engagement", "organisation").get(pk=job.pk)


def _target(job: ImportJob) -> dict:
    return {"engagement_id": job.engagement_id} if job.kind == "findings" else {"organisation_id": job.organisation_id}


def _busy(*, engagement_id=None, organisation_id=None, exclude=None) -> bool:
    target = {"engagement_id": engagement_id} if engagement_id else {"organisation_id": organisation_id}
    qs = ImportJob.objects.filter(**target, status__in=ImportJob.WORKING, updated_at__gte=timezone.now() - STALE)
    return qs.exclude(pk=exclude).exists() if exclude else qs.exists()


def _writable_target(job: ImportJob) -> None:
    if job.kind == "findings" and job.engagement.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to import.")
    if job.kind == "assets" and job.organisation.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to import.")


def _sync_attempt(job_id) -> None:
    """Copy the job's current state onto the record of its current attempt."""
    job = ImportJob.objects.filter(pk=job_id).first()
    if job is None:
        return
    outcome = {"completed": "completed", "failed": "failed", "cancelled": "cancelled"}.get(job.status, "in_progress")
    ImportAttempt.objects.filter(job=job, number=job.attempt).update(
        counts=job.counts,
        outcome=outcome,
        error=job.error if outcome == "failed" else "",
        finished_at=job.finished_at if outcome != "in_progress" else None,
        updated_at=timezone.now(),
    )


# upload


def _read_upload(uploaded) -> tuple[str, bytes]:
    name = (uploaded.name or "").rsplit("/", 1)[-1][:255]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in parsing.EXTENSIONS:
        raise ValidationError({"file": ["Upload a .csv file."]})
    if uploaded.size > parsing.MAX_BYTES:
        raise ValidationError({"file": [f"The file is larger than {parsing.MAX_BYTES // (1024 * 1024)} MB."]})
    data = uploaded.read()
    if not data:
        raise ValidationError({"file": ["The file is empty."]})
    return name, data


def _store(request, actor, name: str, data: bytes, **target) -> ImportJob:
    digest = hashlib.sha256(data).hexdigest()
    key = get_storage().save(data)
    with transaction.atomic():
        job = ImportJob.objects.create(
            **target,
            kind="assets" if "organisation" in target else "findings",
            uploaded_by=actor,
            original_name=name,
            storage_key=key,
            file_sha256=digest,
            file_size=len(data),
            started_at=timezone.now(),
        )
        ImportAttempt.objects.create(
            job=job, number=1, uploaded_by=actor, original_name=name, file_sha256=digest, file_size=len(data)
        )
        audit.record(
            "import.uploaded",
            request=request,
            entity=job,
            engagement=target.get("engagement"),
            metadata={"file": name, "size": len(data), "sha256": digest, "kind": job.kind},
        )
    _enqueue("parse_job", job.pk)
    return job


def create_upload(request, actor, eng: Engagement, uploaded) -> ImportJob:
    if not has_engagement_perm(actor, eng.pk, "imports.create"):
        _deny(request, eng, "import.upload_denied", "You do not have permission to import into this engagement.", eng)
    if eng.is_archived:
        raise Conflict("This engagement is archived. Unarchive it to import.")
    name, data = _read_upload(uploaded)
    if _busy(engagement_id=eng.pk):
        raise Conflict("Another import into this engagement is still running. Wait for it to finish.")
    return _store(request, actor, name, data, engagement=eng)


def create_asset_upload(request, actor, org: Organisation, uploaded) -> ImportJob:
    if not has_platform_perm(actor, "assets.import"):
        _deny(request, org, "import.upload_denied", "You do not have permission to import assets.")
    if org.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to import.")
    name, data = _read_upload(uploaded)
    if _busy(organisation_id=org.pk):
        raise Conflict("Another import into this organisation is still running. Wait for it to finish.")
    return _store(request, actor, name, data, organisation=org)


def parse_job(job_id) -> None:
    """Worker: read the file, store its rows, and leave the job ready for mapping. Safe to run twice."""
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != "uploaded":
            return
        job.status = "parsing"
        job.save(update_fields=["status", "updated_at"])
    try:
        parsed = parsing.parse(get_storage().read(job.storage_key))
        sample, total, batch = [], 0, []
        with transaction.atomic():
            for line, cells in parsed.rows:
                total += 1
                if len(sample) < 5:
                    sample.append(cells[: len(parsed.headers)])
                batch.append(ImportRow(job=job, attempt=job.attempt, row_number=line, raw=cells))
                if len(batch) >= 1000:
                    ImportRow.objects.bulk_create(batch)
                    batch = []
            if batch:
                ImportRow.objects.bulk_create(batch)
        if total == 0:
            raise parsing.ParseError("The file has column names but no rows.")
        ImportJob.objects.filter(pk=job.pk).update(
            status="parsed",
            encoding=parsed.encoding,
            delimiter=parsed.delimiter,
            headers=parsed.headers,
            sample=sample,
            counts={"total": total},
            updated_at=timezone.now(),
        )
        _auto_validate(job)
    except parsing.ParseError as exc:
        _fail(job, str(exc)[:300])
    except Exception:  # noqa: BLE001 - never leave a job stuck in "parsing"
        log.exception("import %s: parsing crashed", job_id)
        _fail(job, "The file could not be read.")


def _auto_validate(job: ImportJob) -> None:
    """After a corrected file: reuse the earlier column mapping when the new file still fits it."""
    if job.attempt < 2 or not job.mapping.get("column_map"):
        return
    fresh = ImportJob.objects.get(pk=job.pk)
    try:
        cleaned, values = clean_mapping(
            fresh.headers, job.mapping["column_map"], job.mapping.get("value_map", {}), job.kind
        )
    except ValidationError:
        return  # the new file's columns changed: the user maps them again
    ImportJob.objects.filter(pk=job.pk, status="parsed").update(
        status="validating", mapping={"column_map": cleaned, "value_map": values}, updated_at=timezone.now()
    )
    _enqueue("validate_job", job.pk)


def _fail(job: ImportJob, message: str) -> None:
    ImportJob.objects.filter(pk=job.pk).update(
        status="failed", error=message, finished_at=timezone.now(), updated_at=timezone.now()
    )
    _sync_attempt(job.pk)
    audit.record(
        "import.failed",
        actor=job.uploaded_by,
        entity=job,
        engagement=job.engagement,
        outcome="failure",
        metadata={"reason": message},
    )


# mapping and validation


def set_mapping(request, actor, job: ImportJob, column_map: dict, value_map: dict, save_as: str = "") -> ImportJob:
    _require_create(request, actor, job, "import.mapping_denied")
    with transaction.atomic():
        job = _lock(job)
        if job.status not in ("parsed", "previewed"):
            raise Conflict("This import is not waiting for a mapping.")
        _writable_target(job)
        if _busy(**_target(job), exclude=job.pk):
            raise Conflict("Another import into this target is still running. Wait for it to finish.")
        cleaned, values = clean_mapping(job.headers, column_map, value_map, job.kind)
        job.mapping = {"column_map": cleaned, "value_map": values}
        job.status, job.started_at = "validating", timezone.now()
        job.version += 1
        job.save()
        job.rows_now.update(
            status="pending", mapped={}, errors=[], duplicate_of_finding=None, duplicate_of_line=None, asset_id=None
        )
        if save_as.strip():
            ImportMapping.objects.update_or_create(
                owner=actor, name=save_as.strip()[:120], defaults={"column_map": cleaned, "value_map": values}
            )
        audit.record(
            "import.mapped",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"columns": sorted(cleaned), "saved_as": save_as.strip() or None, "kind": job.kind},
        )
    _enqueue("validate_job", job.pk)
    return job


def validate_job(job_id) -> None:
    """Worker: check every row, mark duplicates, and leave the job ready to preview."""
    job = ImportJob.objects.select_related("engagement", "organisation", "uploaded_by").filter(pk=job_id).first()
    if job is None or job.status != "validating":
        return
    if job.kind == "assets":
        return _validate_assets(job)
    try:
        maps = job.mapping
        validator = RowValidator(job.engagement, job.headers, maps["column_map"], maps.get("value_map", {}))
        first_seen: dict[str, tuple[int, int]] = {}  # hash -> (row id, line)
        by_hash: dict[str, list[int]] = {}
        dup_in_file: list[tuple[int, int]] = []  # (row id, line of the first occurrence)
        pending = []

        def flush():
            if pending:
                ImportRow.objects.bulk_update(pending, ["mapped", "errors", "status"])
                pending.clear()

        for row in job.rows_now.order_by("row_number", "id").iterator(chunk_size=1000):
            mapped, errors = validator.validate(row.raw)
            row.mapped, row.errors = mapped, errors
            row.status = "invalid" if errors else "valid"
            if not errors:
                h = mapped["dedupe_hash"]
                by_hash.setdefault(h, []).append(row.pk)
                if h in first_seen:
                    dup_in_file.append((row.pk, first_seen[h][1]))
                else:
                    first_seen[h] = (row.pk, row.row_number)
            pending.append(row)
            if len(pending) >= 1000:
                flush()
        flush()
        for row_id, line in dup_in_file:
            ImportRow.objects.filter(pk=row_id).update(status="duplicate", duplicate_of_line=line)
        hashes = list(first_seen)
        for i in range(0, len(hashes), 1000):
            existing = {}
            for fid, h in (
                scope_findings(job.uploaded_by)
                .filter(engagement=job.engagement, dedupe_hash__in=hashes[i : i + 1000])
                .order_by("-created_at")
                .values_list("pk", "dedupe_hash")
            ):
                existing[h] = fid
            for h, fid in existing.items():
                ImportRow.objects.filter(pk__in=by_hash[h]).update(status="duplicate", duplicate_of_finding=fid)
        counts = {s: job.rows_now.filter(status=s).count() for s in ("valid", "invalid", "duplicate")}
        incomplete = sum(
            1 for errs in job.rows_now.filter(status="invalid").values_list("errors", flat=True) if is_recoverable(errs)
        )
        if incomplete:
            counts["incomplete"] = incomplete
        counts["total"] = job.rows_now.count()
        ImportJob.objects.filter(pk=job.pk, status="validating").update(
            status="previewed", counts=counts, updated_at=timezone.now()
        )
        _sync_attempt(job.pk)
        audit.record("import.validated", actor=job.uploaded_by, entity=job, engagement=job.engagement, metadata=counts)
    except Exception:  # noqa: BLE001
        log.exception("import %s: validation crashed", job_id)
        _fail(job, "The rows could not be checked.")


# commit


def commit(request, actor, job: ImportJob, mode: str, duplicates: str) -> ImportJob:
    _require_create(request, actor, job, "import.commit_denied")
    with transaction.atomic():
        job = _lock(job)
        if job.status != "previewed":
            raise Conflict("This import is not ready to import.")
        _writable_target(job)
        if _busy(**_target(job), exclude=job.pk):
            raise Conflict("Another import into this target is still running. Wait for it to finish.")
        if job.kind == "assets":
            duplicates = "skip"  # an asset that is already known is never created again
        c = job.counts
        if mode == "all_or_nothing" and c.get("invalid", 0) > 0:
            raise Conflict(f"{c['invalid']} rows have errors. Fix the file, or choose to import the valid rows only.")
        importable = c.get("valid", 0) + (c.get("duplicate", 0) if duplicates == "import" else 0)
        if mode == "everything" and job.kind == "findings":
            importable += c.get("incomplete", 0)
        if job.kind == "assets":
            importable = c.get("valid", 0)
        if importable == 0:
            raise Conflict("There is nothing to import.")
        job.status, job.mode, job.duplicates, job.started_at = "importing", mode, duplicates, timezone.now()
        job.version += 1
        job.save()
        audit.record(
            "import.commit_requested",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"mode": mode, "duplicates": duplicates, "rows": importable},
        )
    _enqueue("run_import", job.pk)
    return job


def run_import(job_id) -> None:
    """Worker: create the drafts in one transaction. Any failure rolls back to zero findings."""
    job = ImportJob.objects.select_related("engagement", "organisation", "uploaded_by").filter(pk=job_id).first()
    if job is None or job.status != "importing":
        return
    if job.kind == "assets":
        return _run_asset_import(job)
    try:
        with transaction.atomic():
            eng = Engagement.objects.select_for_update().get(pk=job.engagement_id)
            if eng.is_archived:
                raise ImportAbort("The engagement was archived before the import ran.")
            scope_assets = set(
                EngagementAsset.objects.filter(engagement=eng, in_scope=True).values_list("asset_id", flat=True)
            )
            want = ["valid"] + (["duplicate"] if job.duplicates == "import" else [])
            if job.mode == "everything":
                want.append("invalid")  # only the recoverable ones are kept, see insert()
            rows = job.rows_now.filter(status__in=want).order_by("row_number", "id")
            imported, lost, first_ref, last_ref = 0, 0, None, None
            batch: list[ImportRow] = []

            def insert(batch_rows):
                nonlocal imported, lost, first_ref, last_ref
                usable = []
                for r in batch_rows:
                    if r.status == "invalid" and not is_recoverable(r.errors):
                        continue  # stays invalid: it cannot be stored
                    aid = r.mapped.get("asset_id")
                    if aid and uuid.UUID(str(aid)) not in scope_assets and job.mode == "everything":
                        r.mapped = {**r.mapped, "asset_id": None}
                        r.errors = [
                            *r.errors,
                            {"field": "asset", "code": "unknown_asset", "message": "The asset is no longer in scope."},
                        ]
                        if r.status != "invalid":
                            r.status = "invalid"  # imported below with the gap recorded
                        aid = None
                    if aid and uuid.UUID(str(aid)) not in scope_assets:
                        if job.mode == "all_or_nothing":
                            raise ImportAbort(
                                f"Line {r.row_number}: the asset is no longer in scope for this engagement."
                            )
                        r.status, r.errors = (
                            "invalid",
                            [
                                *r.errors,
                                {
                                    "field": "asset",
                                    "code": "unknown_asset",
                                    "message": "The asset is no longer in scope.",
                                },
                            ],
                        )
                        r.save(update_fields=["status", "errors"])
                        lost += 1
                        continue
                    usable.append(r)
                if not usable:
                    return
                refs = reserve_refs(len(usable))
                findings = [_finding(job, eng, r, ref) for r, ref in zip(usable, refs, strict=True)]
                Finding.objects.bulk_create(findings, batch_size=CHUNK)
                for r, f in zip(usable, findings, strict=True):
                    r.status, r.finding_id = "imported", f.pk
                ImportRow.objects.bulk_update(usable, ["status", "finding_id"])
                imported += len(usable)
                first_ref = first_ref or refs[0]
                last_ref = refs[-1]

            for row in rows.iterator(chunk_size=CHUNK):
                batch.append(row)
                if len(batch) >= CHUNK:
                    insert(batch)
                    batch = []
            if batch:
                insert(batch)
            skipped = 0
            if job.duplicates == "skip":
                skipped = job.rows_now.filter(status="duplicate").update(status="skipped")
            counts = {
                **job.counts,
                "imported": imported,
                "skipped": skipped,
                "invalid": job.rows_now.filter(status="invalid").count(),
            }
            ImportJob.objects.filter(pk=job.pk).update(
                status="completed", counts=counts, finished_at=timezone.now(), updated_at=timezone.now()
            )
            _sync_attempt(job.pk)
            audit.record(
                "import.committed",
                actor=job.uploaded_by,
                entity=job,
                engagement=eng,
                metadata={
                    "imported": imported,
                    "skipped": skipped,
                    "invalid": counts["invalid"],
                    "mode": job.mode,
                    "first_ref": first_ref,
                    "last_ref": last_ref,
                    "sha256": job.file_sha256,
                    "lost_to_scope_change": lost,
                },
            )
    except ImportAbort as exc:
        _fail(job, f"Nothing was imported. {exc}"[:300])
    except Exception:  # noqa: BLE001
        log.exception("import %s: commit crashed", job_id)
        _fail(job, "Nothing was imported: the import failed and was rolled back.")


def _finding(job: ImportJob, eng: Engagement, row: ImportRow, ref: str) -> Finding:
    m = row.mapped
    # Gaps: problems the row came with. Each one is kept on the draft so it can be fixed in the finding editor.
    issues = [{"field": e["field"], "message": e["message"]} for e in row.errors if is_recoverable([e])]
    if row.errors and "title" not in {i["field"] for i in issues} and not m.get("title"):
        issues.append({"field": "title", "message": "The title is empty."})
    extra = {}
    if m.get("cvss_vector"):
        version, score, severity = cvss.score_vector(m["cvss_vector"])
        extra = {"cvss_vector": m["cvss_vector"], "cvss_version": version, "cvss_score": score, "severity": severity}
    return Finding(
        ref=ref,
        engagement=eng,
        reported_by=job.uploaded_by,
        status="draft",
        source="import",
        import_job=job,
        title=m.get("title") or f"Untitled finding (line {row.row_number})",
        severity=extra.get("severity") or m.get("severity") or "info",
        import_issues=issues,
        description=m.get("description", ""),
        recommendation=m.get("recommendation", ""),
        technical_details=m.get("technical_details", ""),
        poc=m.get("poc", ""),
        endpoint=m.get("endpoint", ""),
        asset_id=m.get("asset_id"),
        cwe_id=m.get("cwe_id"),
        references=m.get("references", []),
        discovered_at=datetime.date.fromisoformat(m["discovered_at"])
        if m.get("discovered_at")
        else timezone.localdate(),
        dedupe_hash=m["dedupe_hash"],
        **{k: v for k, v in extra.items() if k != "severity"},
    )


# assets: check and commit


def _validate_assets(job: ImportJob) -> None:
    """Worker: validate every row, match it against the organisation's assets and against earlier rows."""
    try:
        maps = job.mapping
        validator = AssetRowValidator(job.headers, maps["column_map"])
        matcher = Matcher(job.organisation_id)
        counts = {"valid": 0, "invalid": 0, "duplicate": 0, "to_create": 0, "to_merge": 0}
        pending, chunk = [], []

        def flush_chunk():
            matcher.preload(i["match_key"] for r in chunk if not r.errors for i in r.mapped["identifiers"])
            for r in chunk:
                if not r.errors:
                    outcome = matcher.resolve(r.mapped["identifiers"], r.row_number)
                    if outcome.action in ("conflict", "archived"):
                        code = "identifier_conflict" if outcome.action == "conflict" else "archived_asset"
                        r.errors = [{"field": "identifiers", "code": code, "message": outcome.message}]
                        r.status = "invalid"
                    else:
                        r.status, r.mapped = describe(outcome, r.mapped)
                        counts["to_create"] += outcome.action == "create"
                        counts["to_merge"] += outcome.action in ("merge", "merge_in_file")
                        if r.status == "duplicate" and outcome.target_line:
                            r.duplicate_of_line = outcome.target_line
                counts[r.status] += 1
                pending.append(r)
            ImportRow.objects.bulk_update(pending, ["mapped", "errors", "status", "duplicate_of_line"])
            pending.clear()
            chunk.clear()

        for row in job.rows_now.order_by("row_number", "id").iterator(chunk_size=500):
            row.mapped, row.errors = validator.validate(row.raw)
            row.status = "invalid" if row.errors else "valid"
            chunk.append(row)
            if len(chunk) >= 500:
                flush_chunk()
        flush_chunk()
        counts["total"] = job.rows_now.count()
        ImportJob.objects.filter(pk=job.pk, status="validating").update(
            status="previewed", counts=counts, updated_at=timezone.now()
        )
        _sync_attempt(job.pk)
        audit.record("import.validated", actor=job.uploaded_by, entity=job, metadata={**counts, "kind": "assets"})
    except Exception:  # noqa: BLE001
        log.exception("import %s: asset validation crashed", job.pk)
        _fail(job, "The rows could not be checked.")


def _run_asset_import(job: ImportJob) -> None:
    """Worker: create or enrich assets in one transaction under the organisation lock. Rows are matched
    again against live data, so anything that changed since the check is caught here."""
    try:
        with transaction.atomic():
            org = Organisation.objects.select_for_update().get(pk=job.organisation_id)
            if org.is_archived:
                raise ImportAbort("The organisation was archived before the import ran.")
            matcher = Matcher(org.pk)
            created = merged = skipped = lost = 0
            pending: list[ImportRow] = []

            def reject(r: ImportRow, code: str, message: str):
                nonlocal lost
                if job.mode == "all_or_nothing":
                    raise ImportAbort(f"Line {r.row_number}: {message}")
                r.status, r.errors = "invalid", [*r.errors, {"field": "identifiers", "code": code, "message": message}]
                lost += 1
                pending.append(r)

            rows = job.rows_now.filter(status__in=["valid", "duplicate"]).order_by("row_number", "id")
            chunk: list[ImportRow] = []

            def work(batch):
                nonlocal created, merged, skipped
                matcher.preload(i["match_key"] for r in batch for i in r.mapped["identifiers"])
                for r in batch:
                    if r.status == "duplicate":
                        r.status = "skipped"
                        skipped += 1
                        pending.append(r)
                        continue
                    outcome = matcher.resolve(r.mapped["identifiers"], r.row_number)
                    prepared = [(ident.parse(i["value"], i["kind"]), False) for i in r.mapped["identifiers"]]
                    if outcome.action in ("conflict", "archived"):
                        reject(
                            r,
                            "identifier_conflict" if outcome.action == "conflict" else "archived_asset",
                            outcome.message,
                        )
                        continue
                    if outcome.action in ("known", "known_in_file"):
                        r.status = "skipped"
                        skipped += 1
                    elif outcome.action == "merge":
                        asset = Asset.objects.select_for_update().get(pk=outcome.asset_id)
                        fresh = [(p, w) for p, w in prepared if p.match_key in outcome.new_keys]
                        asset_ops.attach(asset, fresh, source="import", primary_hint=False)
                        r.status, r.asset_id = "imported", asset.pk
                        merged += 1
                    else:  # create
                        m = r.mapped
                        asset = Asset.objects.create(
                            organisation=org,
                            name=m["name"][:160],
                            type=m["type"],
                            environment=m["environment"],
                            criticality=m["criticality"],
                            tags=m["tags"],
                            origin="import",
                            onboarding_status="pending",
                        )
                        asset_ops.attach(asset, prepared, source="import")
                        r.status, r.asset_id = "imported", asset.pk
                        created += 1
                        for p, _ in prepared:
                            matcher.db[p.match_key] = (str(asset.pk), asset.name, False)
                            matcher.overlay.pop(p.match_key, None)
                    pending.append(r)
                ImportRow.objects.bulk_update(pending, ["status", "errors", "asset_id"])
                pending.clear()

            for row in rows.iterator(chunk_size=CHUNK):
                chunk.append(row)
                if len(chunk) >= CHUNK:
                    work(chunk)
                    chunk = []
            if chunk:
                work(chunk)
            counts = {
                **job.counts,
                "imported": created + merged,
                "created": created,
                "merged": merged,
                "skipped": skipped,
                "invalid": job.rows_now.filter(status="invalid").count(),
            }
            ImportJob.objects.filter(pk=job.pk).update(
                status="completed", counts=counts, finished_at=timezone.now(), updated_at=timezone.now()
            )
            _sync_attempt(job.pk)
            audit.record(
                "import.committed",
                actor=job.uploaded_by,
                entity=job,
                metadata={
                    "kind": "assets",
                    "organisation": org.name,
                    "created_not_onboarded": created,
                    "merged_into_existing": merged,
                    "skipped": skipped,
                    "invalid": counts["invalid"],
                    "mode": job.mode,
                    "sha256": job.file_sha256,
                    "lost_to_changes": lost,
                },
            )
    except ImportAbort as exc:
        _fail(job, f"Nothing was imported. {exc}"[:300])
    except Exception:  # noqa: BLE001
        log.exception("import %s: asset commit crashed", job.pk)
        _fail(job, "Nothing was imported: the import failed and was rolled back.")


# delete, corrected file, retry


FAILED_OR_STUCK = ("failed", "cancelled")


def delete_job(request, actor, job: ImportJob) -> None:
    """Delete a failed or cancelled import with its rows, history and any file. Nothing it was meant to
    create exists (a failed commit rolls back), so no findings or assets are touched."""
    _require_create(request, actor, job, "import.delete_denied")
    with transaction.atomic():
        job = _lock(job)
        if job.status not in FAILED_OR_STUCK:
            raise Conflict("Only a failed or cancelled import can be deleted. Cancel an import that has not run first.")
        if job.findings.exists() or job.rows.filter(asset_id__isnull=False).exists():
            raise Conflict("This import already created records and is kept as history.")
        audit.record(
            "import.deleted",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"file": job.original_name, "status": job.status, "error": job.error, "attempts": job.attempt},
        )
        storage_key = job.storage_key
        job.rows.all().delete()
        job.attempts.all().delete()
        job.delete()
    if storage_key:
        get_storage().delete(storage_key)


def can_reupload(job: ImportJob) -> bool:
    c = job.counts or {}
    return job.status in ("failed", "previewed", "parsed") or (job.status == "completed" and (c.get("invalid", 0) > 0))


def reupload(request, actor, job: ImportJob, uploaded) -> ImportJob:
    """Take a corrected file into the same import. Starts a new attempt; earlier attempts stay as history.
    The column mapping is reused when the new file still has those columns."""
    _require_create(request, actor, job, "import.reupload_denied")
    name, data = _read_upload(uploaded)
    digest = hashlib.sha256(data).hexdigest()
    with transaction.atomic():
        job = _lock(job)
        if not can_reupload(job):
            raise Conflict(
                "A corrected file can be uploaded when the import failed, is waiting to import, or left rows out."
            )
        _writable_target(job)
        if _busy(**_target(job), exclude=job.pk):
            raise Conflict("Another import into this target is still running. Wait for it to finish.")
        if digest == job.file_sha256:
            raise ValidationError({"file": ["This is the same file as the last upload. Correct it first."]})
        old_key = job.storage_key
        ImportAttempt.objects.filter(job=job, number=job.attempt).exclude(outcome="completed").update(
            outcome="superseded", finished_at=timezone.now(), updated_at=timezone.now()
        )
        job.attempt += 1
        job.original_name, job.file_sha256, job.file_size = name, digest, len(data)
        job.storage_key = get_storage().save(data)
        job.file_purged_at = None
        job.status, job.error, job.finished_at, job.started_at = "uploaded", "", None, timezone.now()
        job.headers, job.sample, job.counts, job.encoding, job.delimiter = [], [], {}, "", ""
        job.version += 1
        job.save()
        ImportAttempt.objects.create(
            job=job, number=job.attempt, uploaded_by=actor, original_name=name, file_sha256=digest, file_size=len(data)
        )
        audit.record(
            "import.reuploaded",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"attempt": job.attempt, "file": name, "size": len(data), "sha256": digest},
        )
    if old_key:
        try:
            get_storage().delete(old_key)
        except Exception:  # noqa: BLE001 - an orphaned blob must never fail the upload
            log.warning("import %s: could not delete the replaced file", job.pk)
    _enqueue("parse_job", job.pk)
    return job


def retry(request, actor, job: ImportJob) -> ImportJob:
    """Run a failed import again from where it stopped, with the same file and mapping."""
    _require_create(request, actor, job, "import.retry_denied")
    with transaction.atomic():
        job = _lock(job)
        if job.status != "failed":
            raise Conflict("Only a failed import can be retried.")
        _writable_target(job)
        if _busy(**_target(job), exclude=job.pk):
            raise Conflict("Another import into this target is still running. Wait for it to finish.")
        if not job.storage_key:
            raise Conflict("The uploaded file was deleted. Upload the file again as a corrected file.")
        if not job.headers:
            next_status, task = "uploaded", "parse_job"
            job.rows_now.delete()
        elif job.mapping.get("column_map"):
            next_status, task = "validating", "validate_job"
            job.rows_now.update(
                status="pending", mapped={}, errors=[], duplicate_of_finding=None, duplicate_of_line=None, asset_id=None
            )
        else:
            next_status, task = "parsed", None
        job.status, job.error, job.finished_at, job.started_at = next_status, "", None, timezone.now()
        job.version += 1
        job.save()
        ImportAttempt.objects.filter(job=job, number=job.attempt).update(
            outcome="in_progress", error="", finished_at=None, updated_at=timezone.now()
        )
        audit.record(
            "import.retried",
            request=request,
            entity=job,
            engagement=job.engagement,
            metadata={"resumed_at": next_status},
        )
    if task:
        _enqueue(task, job.pk)
    return job


# cancel and housekeeping


def cancel(request, actor, job: ImportJob) -> ImportJob:
    _require_create(request, actor, job, "import.cancel_denied")
    with transaction.atomic():
        job = _lock(job)
        if job.status not in ("uploaded", "parsed", "previewed"):
            raise Conflict("Only an import that has not started working can be cancelled.")
        job.status, job.finished_at = "cancelled", timezone.now()
        job.version += 1
        job.save()
        audit.record("import.cancelled", request=request, entity=job, engagement=job.engagement)
    _sync_attempt(job.pk)
    _purge_file(job)
    return job


def _purge_file(job: ImportJob) -> None:
    if job.storage_key:
        try:
            get_storage().delete(job.storage_key)
        finally:
            ImportJob.objects.filter(pk=job.pk).update(storage_key="", file_purged_at=timezone.now())


def cleanup() -> dict:
    """Daily: close jobs stuck in a working state, and delete uploaded files of finished jobs after 30 days.
    Job and row history stay."""
    now = timezone.now()
    stuck = ImportJob.objects.filter(status__in=ImportJob.WORKING, updated_at__lt=now - STALE)
    stuck_count = 0
    for job in stuck.select_related("engagement", "uploaded_by"):
        _fail(job, "The import did not finish in time.")
        stuck_count += 1
    old = ImportJob.objects.filter(status__in=ImportJob.FINISHED, finished_at__lt=now - FILE_RETENTION).exclude(
        storage_key=""
    )
    purged = 0
    for job in old:
        _purge_file(job)
        purged += 1
    return {"stuck": stuck_count, "purged": purged}
