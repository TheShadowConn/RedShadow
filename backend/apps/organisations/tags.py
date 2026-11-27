"""Asset tags. Tags are free text kept on each asset (`Asset.tags`); there is no tag table.

Tags are compared without regard to case. Every change is made asset by asset inside one transaction and
audited as `asset.updated`. Callers pass an already scoped queryset, so nothing outside it is read or written.
"""

from django.db import transaction
from rest_framework.exceptions import NotFound

from apps.audit import service as audit

MAX_TAGS = 20


def _key(tag: str) -> str:
    return tag.casefold()


def _unique(tags) -> list[str]:
    seen: dict[str, str] = {}
    for tag in tags:
        seen.setdefault(_key(tag), tag)
    return list(seen.values())


def ids_with_tag(qs, tag: str) -> list:
    wanted = _key(tag.strip())
    rows = qs.values_list("pk", "tags")
    return [pk for pk, tags in rows if any(_key(t) == wanted for t in tags)]


def spellings(qs) -> dict[str, str]:
    """Casefolded tag -> the spelling in use among the assets of `qs`."""
    return {_key(row["tag"]): row["tag"] for row in catalogue(qs)}


def canonical(known: dict[str, str], tags) -> list[str]:
    """Trim, drop repeats and reuse the spelling already in `known`. New tags are remembered in `known`."""
    cleaned = [t.strip() for t in tags if t.strip()]
    return [known.setdefault(_key(t), t) for t in _unique(cleaned)]


def ids_without_tags(qs) -> list:
    return [pk for pk, tags in qs.values_list("pk", "tags") if not tags]


def catalogue(qs) -> list[dict]:
    """Every tag in use, with how many live (and onboarded) and archived assets carry it."""
    found: dict[str, dict] = {}
    for tags, onboarding, archived_at in qs.values_list("tags", "onboarding_status", "archived_at"):
        for tag in _unique(tags):
            row = found.setdefault(_key(tag), {"spellings": {}, "assets": 0, "onboarded": 0, "archived": 0})
            row["spellings"][tag] = row["spellings"].get(tag, 0) + 1
            if archived_at is not None:
                row["archived"] += 1
            else:
                row["assets"] += 1
                row["onboarded"] += onboarding == "onboarded"
    result = []
    for key in sorted(found):
        row = found[key]
        spellings = row.pop("spellings")
        result.append({"tag": max(sorted(spellings), key=spellings.get), **row})
    return result


def _apply(request, qs, ids, change) -> dict:
    """Run `change(tags) -> tags` on each asset. Archived assets are reported and left as they are."""
    updated, skipped = 0, []
    with transaction.atomic():
        rows = qs.model.objects.filter(pk__in=ids).select_related("organisation").select_for_update(of=("self",))
        for asset in rows.order_by("pk"):
            new = change(list(asset.tags))
            if new == asset.tags:
                continue
            reason = ""
            if asset.is_archived:
                reason = "This asset is archived."
            elif asset.organisation.is_archived:
                reason = "Its organisation is archived."
            elif len(new) > MAX_TAGS and len(new) > len(asset.tags):
                reason = f"An asset takes at most {MAX_TAGS} tags."
            if reason:
                skipped.append({"id": str(asset.pk), "name": asset.name, "reason": reason})
                continue
            old, asset.tags = asset.tags, new
            asset.save(update_fields=["tags", "updated_at"])
            audit.record("asset.updated", request=request, entity=asset, changes={"tags": [old, new]})
            updated += 1
    return {"updated": updated, "skipped": skipped}


def assign(request, qs, ids: list, add: list[str], remove: list[str]) -> dict:
    # An added tag takes the spelling already in use, so "DevOps" and "devops" do not both appear.
    known = {_key(row["tag"]): row["tag"] for row in catalogue(qs)}
    add = [known.get(_key(t), t) for t in _unique(add)]
    gone = {_key(t) for t in remove}
    found = list(qs.filter(pk__in=ids).values_list("pk", flat=True))

    def change(tags):
        kept = [t for t in tags if _key(t) not in gone]
        have = {_key(t) for t in kept}
        return kept + [t for t in add if _key(t) not in have]

    result = _apply(request, qs, found, change)
    result["not_found"] = len(set(ids)) - len(found)
    return result


def rename(request, qs, tag: str, new_name: str) -> dict:
    """Rename a tag everywhere in `qs`. Renaming onto another tag merges the two."""
    old, new = _key(tag), _key(new_name)
    ids = ids_with_tag(qs, tag)
    if not ids:
        raise NotFound("No asset has this tag.")

    def change(tags):
        return _unique(new_name if _key(t) in (old, new) else t for t in tags) if old in map(_key, tags) else tags

    return _apply(request, qs, ids, change)


def delete(request, qs, tag: str) -> dict:
    """Take a tag off every asset in `qs`. The assets themselves stay."""
    gone = _key(tag)
    ids = ids_with_tag(qs, tag)
    if not ids:
        raise NotFound("No asset has this tag.")
    return _apply(request, qs, ids, lambda tags: [t for t in tags if _key(t) != gone])
