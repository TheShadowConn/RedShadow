"""Shared two-organisation fixture for Phase 3 isolation tests."""

from datetime import date, timedelta
from types import SimpleNamespace

from apps.engagements import services as eng_services
from apps.engagements.models import EngagementMembership
from apps.organisations import services as org_services
from tests.conftest import make_user


def build_world(admin):
    org_a = org_services.create_organisation(None, admin, {"name": "Acme Corp", "industry": "Retail"})
    org_b = org_services.create_organisation(None, admin, {"name": "Borealis Ltd"})
    asset_a = org_services.create_asset(
        None, admin, org_a, {"name": "Acme shop", "type": "web_app", "identifier": "https://shop.acme.test"}
    )
    asset_b = org_services.create_asset(
        None, admin, org_b, {"name": "Borealis core", "type": "host", "identifier": "10.0.0.5"}
    )
    contact_a = org_services.create_contact(
        None, admin, org_a, {"name": "Alice Client", "email": "alice@acme.test", "is_primary": True}
    )
    contact_b = org_services.create_contact(None, admin, org_b, {"name": "Bob Client", "email": "bob@borealis.test"})
    today = date.today()
    p1 = make_user("p1@example.com", "pentester")
    p2 = make_user("p2@example.com", "pentester")
    p3 = make_user("p3@example.com", "pentester")
    r1 = make_user("r1@example.com", "remediation")
    base = {"type": "web", "start_date": today, "end_date": today + timedelta(days=10)}
    eng_a = eng_services.create_engagement(
        None, admin, {**base, "organisation": org_a, "name": "Acme web test", "lead": p1}
    )
    eng_b = eng_services.create_engagement(
        None,
        admin,
        {**base, "organisation": org_b, "name": "Borealis internal", "type": "internal_network", "lead": p2},
    )
    EngagementMembership.objects.create(engagement=eng_a, user=r1, added_by=admin)
    eng_services.link_asset(None, admin, eng_a, asset_a, True, "")
    eng_services.link_asset(None, admin, eng_b, asset_b, True, "")
    return SimpleNamespace(
        org_a=org_a, org_b=org_b, asset_a=asset_a, asset_b=asset_b, contact_a=contact_a, contact_b=contact_b,
        p1=p1, p2=p2, p3=p3, r1=r1, eng_a=eng_a, eng_b=eng_b, today=today, base=base,
    )  # fmt: skip
