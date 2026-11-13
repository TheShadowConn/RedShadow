from apps.engagements.models import EngagementAsset
from apps.engagements.selectors import _active, engagement_ids_with, sees_everything

from .models import Asset, Contact, Organisation

ORG_PLATFORM = ("organisations.create", "organisations.update", "organisations.archive")
ASSET_PLATFORM = ("assets.create", "assets.update", "assets.archive")


def scope_organisations(user):
    if not _active(user):
        return Organisation.objects.none()
    if sees_everything(user, "organisations.view", ORG_PLATFORM):
        return Organisation.objects.all()
    from apps.engagements.models import Engagement

    reachable = Engagement.objects.filter(id__in=engagement_ids_with(user, "organisations.view"))
    return Organisation.objects.filter(id__in=reachable.values("organisation_id"))


def scope_assets(user):
    if not _active(user):
        return Asset.objects.none()
    if sees_everything(user, "assets.view", ASSET_PLATFORM):
        return Asset.objects.select_related("organisation")
    links = EngagementAsset.objects.filter(engagement_id__in=engagement_ids_with(user, "assets.view"))
    return Asset.objects.filter(id__in=links.values("asset_id")).select_related("organisation")


def scope_contacts(user):
    return Contact.objects.filter(organisation__in=scope_organisations(user))
