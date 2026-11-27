"""Asset identifier, onboarding, delete and merge logic. Called from `services` and from the asset import.

Every function here that writes takes the organisation row lock first. That serialises all identifier
changes of one organisation, so two requests can never both claim the same identifier. The unique
constraint on (organisation, match_key) is the second line of defence.
"""

from collections.abc import Iterable

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import service as audit
from apps.core.errors import Conflict
from apps.engagements.models import EngagementAsset

from . import identifiers as ident
from . import tags
from .models import Asset, AssetIdentifier, Organisation

MAX_IDENTIFIERS = 50


class IdentifierConflict(ValidationError):
    """An identifier already belongs to another asset. The message names that asset (answers 400, like
    every other rejected value, and keeps the answer older clients already handle)."""

    def __init__(self, message: str):
        super().__init__({"identifiers": [message]})


# preparing input


def prepare(items: Iterable[dict], field: str = "identifiers") -> list[tuple[ident.Identifier, bool]]:
    """Normalise ``[{kind?, value, is_primary?}]``. Returns ``[(Identifier, wants_primary)]`` without repeats.

    Raises 400 listing every bad entry. The same identifier written twice (even in different spellings)
    is kept once."""
    problems, out, seen = [], [], {}
    items = list(items)
    if len(items) > MAX_IDENTIFIERS:
        raise ValidationError({field: [f"An asset can have at most {MAX_IDENTIFIERS} identifiers."]})
    for n, item in enumerate(items, 1):
        try:
            parsed = ident.parse(item.get("value", ""), item.get("kind") or None)
        except ident.IdentifierError as exc:
            problems.append(f"Identifier {n}: {exc}")
            continue
        wants = bool(item.get("is_primary"))
        if parsed.match_key in seen:
            if wants:
                out[seen[parsed.match_key]] = (out[seen[parsed.match_key]][0], True)
            continue
        seen[parsed.match_key] = len(out)
        out.append((parsed, wants))
    if problems:
        raise ValidationError({field: problems})
    return out


def owners(org_id, match_keys: Iterable[str]) -> dict[str, AssetIdentifier]:
    """match_key -> the identifier row that already holds it in this organisation."""
    keys = list(set(match_keys))
    found = {}
    for i in range(0, len(keys), 1000):
        qs = AssetIdentifier.objects.filter(organisation_id=org_id, match_key__in=keys[i : i + 1000])
        for row in qs.select_related("asset"):
            found[row.match_key] = row
    return found


def _conflict_message(parsed: ident.Identifier, owner: AssetIdentifier) -> str:
    return f"{parsed.value} already belongs to the asset {owner.asset.name!r}."


def assert_free(org_id, prepared, asset=None) -> None:
    """Raise IdentifierConflict if any identifier belongs to an asset other than ``asset``."""
    held = owners(org_id, (p.match_key for p, _ in prepared))
    clashes = [
        _conflict_message(p, held[p.match_key])
        for p, _ in prepared
        if p.match_key in held and (asset is None or held[p.match_key].asset_id != asset.pk)
    ]
    if clashes:
        raise IdentifierConflict(" ".join(clashes))


def check(org, items: list[dict], exclude_asset=None) -> list[dict]:
    """Dry run for the UI: per identifier, is it valid and who owns it."""
    results = []
    for n, item in enumerate(items[:MAX_IDENTIFIERS]):
        try:
            parsed = ident.parse(item.get("value", ""), item.get("kind") or None)
        except ident.IdentifierError as exc:
            results.append({"index": n, "status": "invalid", "message": str(exc)})
            continue
        owner = owners(org.pk, [parsed.match_key]).get(parsed.match_key)
        row = {"index": n, "kind": parsed.kind, "value": parsed.value, "normalized": parsed.normalized}
        if owner is None or (exclude_asset is not None and owner.asset_id == exclude_asset.pk):
            results.append({**row, "status": "free"})
        else:
            results.append(
                {
                    **row,
                    "status": "owned",
                    "asset": {"id": owner.asset_id, "name": owner.asset.name},
                    "message": _conflict_message(parsed, owner),
                }  # fmt: skip
            )
    return results


# primary identifier bookkeeping


def _sync_display(asset: Asset) -> None:
    """Keep Asset.identifier equal to the primary identifier (older clients and CSV matching read it)."""
    primary = asset.identifiers.filter(is_primary=True).first()
    value = primary.value if primary else ""
    if asset.identifier != value:
        asset.identifier = value
        asset.save(update_fields=["identifier", "updated_at"])


def _ensure_primary(asset: Asset) -> None:
    if not asset.identifiers.filter(is_primary=True).exists():
        first = asset.identifiers.order_by("kind", "normalized").first()
        if first:
            first.is_primary = True
            first.save(update_fields=["is_primary", "updated_at"])
    _sync_display(asset)


def attach(asset: Asset, prepared, source: str = "manual", primary_hint: bool = True) -> list[AssetIdentifier]:
    """Add identifiers to an asset inside the caller's transaction and organisation lock."""
    has_primary = asset.identifiers.filter(is_primary=True).exists()
    wanted = [p for p, w in prepared if w]
    rows = []
    for parsed, _ in prepared:
        make_primary = False
        if primary_hint and wanted:
            make_primary = parsed is wanted[0]
        elif not has_primary and not rows:
            make_primary = True
        rows.append(
            AssetIdentifier(
                asset=asset,
                organisation_id=asset.organisation_id,
                kind=parsed.kind,
                value=parsed.value,
                normalized=parsed.normalized,
                match_key=parsed.match_key,
                is_primary=False,
                source=source,
            )
        )
        if make_primary:
            rows[-1].is_primary = True
    primary_row = next((r for r in rows if r.is_primary), None)
    if primary_row is not None:
        asset.identifiers.filter(is_primary=True).update(is_primary=False)
    try:
        AssetIdentifier.objects.bulk_create(rows)
    except IntegrityError:
        raise IdentifierConflict("One of these identifiers was just added to another asset. Check again.") from None
    _ensure_primary(asset)
    return rows


def _lock_org(org_id) -> Organisation:
    return Organisation.objects.select_for_update().get(pk=org_id)


def _writable(asset: Asset) -> None:
    if asset.organisation.is_archived:
        raise Conflict("This organisation is archived. Unarchive it to make changes.")
    if asset.is_archived:
        raise Conflict("This asset is archived. Unarchive it to make changes.")


# identifier endpoints


def add_identifier(request, actor, asset: Asset, data: dict) -> AssetIdentifier:
    ((parsed, _),) = prepare([data])
    with transaction.atomic():
        _lock_org(asset.organisation_id)
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=asset.pk)
        _writable(asset)
        if asset.identifiers.count() >= MAX_IDENTIFIERS:
            raise ValidationError({"identifiers": [f"An asset can have at most {MAX_IDENTIFIERS} identifiers."]})
        held = owners(asset.organisation_id, [parsed.match_key]).get(parsed.match_key)
        if held is not None:
            if held.asset_id == asset.pk:
                raise Conflict(f"{parsed.value} is already an identifier of this asset.")
            raise IdentifierConflict(_conflict_message(parsed, held))
        (row,) = attach(asset, [(parsed, bool(data.get("is_primary")))])
        audit.record(
            "asset.identifier_added",
            request=request,
            entity=asset,
            metadata={"kind": row.kind, "value": row.value, "primary": row.is_primary},
        )
    return row


def update_identifier(request, actor, row: AssetIdentifier, data: dict) -> AssetIdentifier:
    with transaction.atomic():
        _lock_org(row.organisation_id)
        row = AssetIdentifier.objects.select_for_update(of=("self",)).get(pk=row.pk)
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=row.asset_id)
        _writable(asset)
        changes = {}
        if "value" in data or "kind" in data:
            ((parsed, _),) = prepare([{"kind": data.get("kind", row.kind), "value": data.get("value", row.value)}])
            if parsed.match_key != row.match_key:
                held = owners(asset.organisation_id, [parsed.match_key]).get(parsed.match_key)
                if held is not None and held.pk != row.pk:
                    raise IdentifierConflict(_conflict_message(parsed, held))
            before = f"{row.kind}: {row.value}"
            row.kind, row.value, row.normalized, row.match_key = (
                parsed.kind,
                parsed.value,
                parsed.normalized,
                parsed.match_key,
            )
            changes["identifier"] = [before, f"{row.kind}: {row.value}"]
        if data.get("is_primary") and not row.is_primary:
            asset.identifiers.filter(is_primary=True).update(is_primary=False)
            row.is_primary = True
            changes["primary"] = [False, True]
        elif data.get("is_primary") is False and row.is_primary:
            raise Conflict("Choose another identifier as primary instead.")
        if changes:
            row.save()
            _sync_display(asset)
            audit.record("asset.identifier_updated", request=request, entity=asset, changes=changes)
    return row


def remove_identifier(request, actor, row: AssetIdentifier) -> None:
    with transaction.atomic():
        _lock_org(row.organisation_id)
        row = AssetIdentifier.objects.select_for_update(of=("self",)).get(pk=row.pk)
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=row.asset_id)
        _writable(asset)
        if asset.is_onboarded and asset.identifiers.count() <= 1:
            raise Conflict("An onboarded asset needs at least one identifier.")
        audit.record(
            "asset.identifier_removed", request=request, entity=asset, metadata={"kind": row.kind, "value": row.value}
        )
        row.delete()
        _ensure_primary(asset)


# create and update


def legacy_items(data: dict) -> list[dict] | None:
    """The identifiers a write asks for: the new list, or the old single text field."""
    if "identifiers" in data:
        return data["identifiers"]
    if data.get("identifier"):
        return [{"value": data["identifier"], "is_primary": True}]
    return None


def create_asset(request, actor, org: Organisation, data: dict, *, pending: bool = False, source: str = "manual"):
    """Create an asset with its identifiers. ``pending`` assets come from imports and are not onboarded."""
    from .services import ASSET_FIELDS, _assert_org_writable

    items = legacy_items(data)
    prepared = prepare(items) if items else []
    with transaction.atomic():
        org = _lock_org(org.pk)
        _assert_org_writable(org)
        assert_free(org.pk, prepared)
        now = timezone.now()
        fields = {f: data[f] for f in ASSET_FIELDS if f in data and f != "identifier"}
        if fields.get("tags"):
            known = tags.spellings(Asset.objects.filter(organisation=org))
            fields["tags"] = tags.canonical(known, fields["tags"])
        asset = Asset.objects.create(
            organisation=org,
            origin="import" if pending else "manual",
            onboarding_status="pending" if pending else "onboarded",
            onboarded_at=None if pending else now,
            onboarded_by=None if pending else actor,
            **fields,
        )
        attach(asset, prepared, source=source)
        audit.record(
            "asset.created",
            request=request,
            actor=actor,
            entity=asset,
            metadata={"organisation": org.name, "identifiers": [p.value for p, _ in prepared], "pending": pending},
        )
    return asset


def update_identifier_field(asset: Asset, legacy_text: str | None) -> dict:
    """Apply the old single `identifier` text on PATCH: add it as the new primary (never drops identifiers)."""
    changes = {}
    if legacy_text is None:
        return changes
    text = legacy_text.strip()
    primary = asset.identifiers.filter(is_primary=True).first()
    if text == (primary.value if primary else ""):
        return changes
    if not text:
        return changes  # clearing is done by removing identifiers one by one
    ((parsed, _),) = prepare([{"value": text, "is_primary": True}])
    held = owners(asset.organisation_id, [parsed.match_key]).get(parsed.match_key)
    if held is not None and held.asset_id != asset.pk:
        raise IdentifierConflict(_conflict_message(parsed, held))
    if held is not None:
        asset.identifiers.filter(is_primary=True).update(is_primary=False)
        held.is_primary = True
        held.save(update_fields=["is_primary", "updated_at"])
    else:
        attach(asset, [(parsed, True)])
    _sync_display(asset)
    changes["identifier"] = [primary.value if primary else "", text]
    return changes


# usage, delete, merge


def usage(asset: Asset) -> dict:
    from apps.findings.models import Finding

    return {
        "engagements": EngagementAsset.objects.filter(asset=asset).count(),
        "findings": Finding.all_objects.filter(asset=asset).count(),
        "identifiers": asset.identifiers.count(),
    }


def delete_asset(request, actor, asset: Asset) -> None:
    """Permanently delete an asset nothing refers to. Otherwise the caller is told to archive it."""
    with transaction.atomic():
        _lock_org(asset.organisation_id)
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=asset.pk)
        if asset.organisation.is_archived:
            raise Conflict("This organisation is archived. Unarchive it to make changes.")
        use = usage(asset)
        if use["engagements"] or use["findings"]:
            raise Conflict(
                f"This asset is used by {use['engagements']} engagement(s) and {use['findings']} finding(s) and "
                "cannot be deleted. Archive it instead, or merge it into another asset."
            )
        audit.record(
            "asset.deleted",
            request=request,
            entity=asset,
            metadata={
                "organisation": asset.organisation.name,
                "type": asset.type,
                "identifiers": list(asset.identifiers.values_list("value", flat=True)),
            },
        )
        asset.identifiers.all().delete()
        asset.delete()


def merge_assets(request, actor, target: Asset, source: Asset) -> Asset:
    """Fold ``source`` into ``target``: identifiers, engagement links and findings move, source is deleted."""
    from apps.findings.models import Finding

    if target.pk == source.pk:
        raise ValidationError({"source": ["Choose a different asset to merge."]})
    if target.organisation_id != source.organisation_id:
        raise ValidationError({"source": ["Both assets must belong to the same organisation."]})
    with transaction.atomic():
        _lock_org(target.organisation_id)
        locked = {
            a.pk: a
            for a in Asset.objects.select_for_update()
            .select_related("organisation")
            .filter(pk__in=[target.pk, source.pk])
        }
        if len(locked) != 2:
            raise Conflict("One of the assets no longer exists.")
        target, source = locked[target.pk], locked[source.pk]
        _writable(target)
        if source.organisation.is_archived:
            raise Conflict("This organisation is archived. Unarchive it to make changes.")
        moved_idents = list(source.identifiers.values_list("value", flat=True))
        source.identifiers.update(asset=target, is_primary=False)
        links = 0
        for link in EngagementAsset.objects.filter(asset=source):
            twin = EngagementAsset.objects.filter(engagement_id=link.engagement_id, asset=target).first()
            if twin is None:
                link.asset = target
                link.save(update_fields=["asset", "updated_at"])
            else:
                if link.in_scope and not twin.in_scope:
                    twin.in_scope = True
                    twin.save(update_fields=["in_scope", "updated_at"])
                link.delete()
            links += 1
        findings = Finding.all_objects.filter(asset=source).update(asset=target)
        merged_tags = tags.canonical({}, [*target.tags, *source.tags])[:20]
        target.tags = merged_tags
        target.save(update_fields=["tags", "updated_at"])
        _ensure_primary(target)
        audit.record(
            "asset.merged",
            request=request,
            entity=target,
            metadata={
                "merged_asset": source.name,
                "identifiers_moved": moved_idents,
                "engagement_links": links,
                "findings_moved": findings,
            },
        )
        source.delete()
    return target


# onboarding


def onboard(request, actor, asset: Asset, data: dict) -> Asset:
    """Mark a not-onboarded asset as onboarded, optionally completing its details in the same step."""
    from apps.core.changes import apply_changes

    from .services import ASSET_FIELDS

    with transaction.atomic():
        _lock_org(asset.organisation_id)
        asset = Asset.objects.select_for_update().select_related("organisation").get(pk=asset.pk)
        _writable(asset)
        if asset.is_onboarded:
            return asset
        if not asset.identifiers.exists():
            raise Conflict("Add at least one identifier before onboarding this asset.")
        changes = apply_changes(asset, data, tuple(f for f in ASSET_FIELDS if f != "identifier"))
        asset.onboarding_status, asset.onboarded_at, asset.onboarded_by = "onboarded", timezone.now(), actor
        asset.save()
        audit.record(
            "asset.onboarded",
            request=request,
            entity=asset,
            changes={**changes, "onboarding": ["pending", "onboarded"]},
        )
    return asset


def onboard_many(request, actor, assets: list[Asset]) -> dict:
    done, skipped = 0, []
    for asset in assets:
        try:
            if not asset.is_onboarded:
                onboard(request, actor, asset, {})
                done += 1
        except (Conflict, ValidationError) as exc:
            skipped.append(
                {
                    "id": str(asset.pk),
                    "name": asset.name,
                    "reason": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail),
                }
            )
    return {"onboarded": done, "skipped": skipped}


def set_archived_many(request, actor, found: list[Asset], archived: bool) -> dict:
    """Archive or unarchive several assets. Each one is its own transaction; refusals are reported, not fatal."""
    from .services import set_asset_archived

    changed, skipped = 0, []
    for asset in found:
        if asset.is_archived == archived:
            continue
        try:
            set_asset_archived(request, actor, asset, archived)
            changed += 1
        except (Conflict, ValidationError) as exc:
            detail = exc.detail[0] if isinstance(exc.detail, list) else exc.detail
            skipped.append({"id": str(asset.pk), "name": asset.name, "reason": str(detail)})
    return {"changed": changed, "skipped": skipped}


def counts_for(qs) -> dict:
    return {row["onboarding_status"]: row["n"] for row in qs.values("onboarding_status").annotate(n=Count("id"))}
