"""Finding template writes. Platform level: the view gate (templates.manage) decides who may call these."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.changes import apply_changes
from apps.core.errors import Conflict

from . import cvss
from .models import CWE, FindingTemplate

FIELDS = ("name", "title", "description", "recommendation", "severity", "cvss_vector", "references")


def _normalise(data: dict) -> dict:
    data = dict(data)
    if "cwe_id" in data:
        cwe_id = data.pop("cwe_id")
        data["cwe"] = None
        if cwe_id is not None:
            cwe = CWE.objects.filter(pk=cwe_id).first()
            if cwe is None:
                raise ValidationError({"cwe_id": ["Unknown CWE. Choose one from the list."]})
            data["cwe"] = cwe
    if data.get("cvss_vector"):
        try:
            _, _, severity = cvss.score_vector(data["cvss_vector"])
        except cvss.InvalidVector as e:
            raise ValidationError({"cvss_vector": [str(e)]}) from None
        if data.get("severity") and data["severity"] != severity:
            raise ValidationError({"severity": [f"Severity must be {severity} for this CVSS vector."]})
        data["severity"] = severity
    return data


def create_template(request, actor, data: dict) -> FindingTemplate:
    data = _normalise(data)
    try:
        with transaction.atomic():
            t = FindingTemplate.objects.create(created_by=actor, cwe=data.pop("cwe", None), **data)
            audit.record("template.created", request=request, entity=t)
    except IntegrityError:
        raise ValidationError({"name": ["A template with this name already exists."]}) from None
    return t


def update_template(request, actor, template: FindingTemplate, data: dict, version: int) -> FindingTemplate:
    data = _normalise(data)
    with transaction.atomic():
        t = FindingTemplate.objects.select_for_update().get(pk=template.pk)
        if t.version != version:
            raise Conflict("This template was changed by someone else. Reload and try again.")
        changes = apply_changes(t, data, FIELDS)
        if "cwe" in data and data["cwe"] != t.cwe:
            changes["cwe"] = [t.cwe_id, data["cwe"].pk if data["cwe"] else None]
            t.cwe = data["cwe"]
        if changes:
            t.version += 1
            try:
                with transaction.atomic():
                    t.save()
            except IntegrityError:
                raise ValidationError({"name": ["A template with this name already exists."]}) from None
            audit.record("template.updated", request=request, entity=t,
                         changes={k: [str(v)[:500] for v in pair] for k, pair in changes.items()})  # fmt: skip
    return t


def delete_template(request, actor, template: FindingTemplate) -> None:
    with transaction.atomic():
        audit.record("template.deleted", request=request, entity=template)
        template.delete()
