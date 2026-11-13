"""All organisation, contact and asset writes. Views never write models directly."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.changes import apply_changes
from apps.core.errors import Conflict
from apps.engagements.models import OPEN_STATUSES, Engagement

from .models import Asset, Contact, Organisation

ORG_FIELDS = ("name", "industry", "notes")
CONTACT_FIELDS = ("name", "email", "phone", "title", "is_primary")
ASSET_FIELDS = ("name", "type", "identifier", "environment", "criticality", "tags")


def _unique_slug(name: str) -> str:
    base = slugify(name)[:70] or "organisation"
    slug, n = base, 2
    while Organisation.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _assert_org_writable(org: Organisation) -> None:
    if org.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to make changes.")


def create_organisation(request, actor, data: dict) -> Organisation:
    try:
        with transaction.atomic():
            org = Organisation.objects.create(
                slug=_unique_slug(data["name"]), created_by=actor, **{f: data.get(f, "") for f in ORG_FIELDS}
            )
            audit.record("organisation.created", request=request, entity=org, changes={"name": [None, org.name]})
    except IntegrityError:
        raise ValidationError({"name": ["An organisation with this name already exists."]}) from None
    return org


def update_organisation(request, actor, org: Organisation, data: dict) -> Organisation:
    try:
        with transaction.atomic():
            org = Organisation.objects.select_for_update().get(pk=org.pk)
            _assert_org_writable(org)
            changes = apply_changes(org, data, ORG_FIELDS)
            if changes:
                org.save()
                audit.record("organisation.updated", request=request, entity=org, changes=changes)
    except IntegrityError:
        raise ValidationError({"name": ["An organisation with this name already exists."]}) from None
    return org


def archive_organisation(request, actor, org: Organisation) -> Organisation:
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=org.pk)
        if org.is_archived:
            return org
        if Engagement.objects.filter(organisation=org, status__in=OPEN_STATUSES).exists():
            raise Conflict("This organisation has open engagements. Complete, cancel or archive them first.")
        org.archived_at = timezone.now()
        org.save(update_fields=["archived_at", "updated_at"])
        audit.record("organisation.archived", request=request, entity=org)
    return org


def unarchive_organisation(request, actor, org: Organisation) -> Organisation:
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=org.pk)
        if org.is_archived:
            org.archived_at = None
            org.save(update_fields=["archived_at", "updated_at"])
            audit.record("organisation.unarchived", request=request, entity=org)
    return org


# contacts


def create_contact(request, actor, org: Organisation, data: dict) -> Contact:
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=org.pk)
        _assert_org_writable(org)
        if data.get("is_primary"):
            Contact.objects.filter(organisation=org, is_primary=True).update(is_primary=False)
        contact = Contact.objects.create(
            organisation=org, **{f: data.get(f, "" if f != "is_primary" else False) for f in CONTACT_FIELDS}
        )
        audit.record("contact.created", request=request, entity=contact, metadata={"organisation": org.name})
    return contact


def update_contact(request, actor, contact: Contact, data: dict) -> Contact:
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=contact.organisation_id)
        _assert_org_writable(org)
        contact = Contact.objects.select_for_update().get(pk=contact.pk)
        if data.get("is_primary"):
            Contact.objects.filter(organisation=org, is_primary=True).exclude(pk=contact.pk).update(is_primary=False)
        changes = apply_changes(contact, data, CONTACT_FIELDS)
        if changes:
            contact.save()
            audit.record(
                "contact.updated", request=request, entity=contact, changes=changes, metadata={"organisation": org.name}
            )
    return contact


def delete_contact(request, actor, contact: Contact) -> None:
    with transaction.atomic():
        org = Organisation.objects.select_for_update().get(pk=contact.organisation_id)
        _assert_org_writable(org)
        audit.record("contact.deleted", request=request, entity=contact, metadata={"organisation": org.name})
        contact.delete()


# assets


def create_asset(request, actor, org: Organisation, data: dict) -> Asset:
    try:
        with transaction.atomic():
            org = Organisation.objects.select_for_update().get(pk=org.pk)
            _assert_org_writable(org)
            asset = Asset.objects.create(organisation=org, **{f: data[f] for f in ASSET_FIELDS if f in data})
            audit.record("asset.created", request=request, entity=asset, metadata={"organisation": org.name})
    except IntegrityError:
        raise ValidationError(
            {"identifier": ["This organisation already has an asset of this type with this identifier."]}
        ) from None
    return asset


def update_asset(request, actor, asset: Asset, data: dict) -> Asset:
    try:
        with transaction.atomic():
            asset = Asset.objects.select_for_update().select_related("organisation").get(pk=asset.pk)
            _assert_org_writable(asset.organisation)
            if asset.is_archived:
                raise Conflict("This asset is archived. Unarchive it to make changes.")
            changes = apply_changes(asset, data, ASSET_FIELDS)
            if changes:
                asset.save()
                audit.record("asset.updated", request=request, entity=asset, changes=changes)
    except IntegrityError:
        raise ValidationError(
            {"identifier": ["This organisation already has an asset of this type with this identifier."]}
        ) from None
    return asset


def set_asset_archived(request, actor, asset: Asset, archived: bool) -> Asset:
    with transaction.atomic():
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=asset.pk)
        if archived and not asset.is_archived:
            asset.archived_at = timezone.now()
            action = "asset.archived"
        elif not archived and asset.is_archived:
            _assert_org_writable(asset.organisation)
            asset.archived_at = None
            action = "asset.unarchived"
        else:
            return asset
        asset.save(update_fields=["archived_at", "updated_at"])
        audit.record(action, request=request, entity=asset)
    return asset
