"""Move each asset's single `identifier` text into the new identifier table.

An asset whose identifier cannot be normalised becomes kind "other". If two assets of one organisation
turn out to share an identifier (the old constraint allowed it across asset types) the second asset keeps
only its old text: the new table allows one owner per identifier, and nothing is merged automatically.
"""

from django.db import migrations

from apps.organisations.identifiers import IdentifierError, detect_kind, normalize


def forwards(apps, schema_editor):
    Asset = apps.get_model("organisations", "Asset")
    AssetIdentifier = apps.get_model("organisations", "AssetIdentifier")
    taken = set(AssetIdentifier.objects.values_list("organisation_id", "match_key"))
    batch = []
    for asset in Asset.objects.exclude(identifier="").order_by("created_at").iterator():
        text = asset.identifier.strip()
        try:
            ident = normalize(detect_kind(text), text)
        except IdentifierError:
            ident = normalize("other", text)
        key = (asset.organisation_id, ident.match_key)
        if key in taken:
            continue
        taken.add(key)
        batch.append(
            AssetIdentifier(
                asset_id=asset.pk,
                organisation_id=asset.organisation_id,
                kind=ident.kind,
                value=ident.value,
                normalized=ident.normalized,
                match_key=ident.match_key,
                is_primary=True,
                source="legacy",
            )
        )
    AssetIdentifier.objects.bulk_create(batch, batch_size=500)


def backwards(apps, schema_editor):
    apps.get_model("organisations", "AssetIdentifier").objects.filter(source="legacy").delete()


class Migration(migrations.Migration):
    dependencies = [("organisations", "0003_asset_identifiers")]
    operations = [migrations.RunPython(forwards, backwards)]
