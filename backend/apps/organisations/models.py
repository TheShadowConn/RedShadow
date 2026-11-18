from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel

from .identifiers import KINDS


class Organisation(BaseModel):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    industry = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    logo = models.ForeignKey("files.Attachment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="uniq_organisation_name_ci")]

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Contact(BaseModel):
    """Client contact. Minimal PII by design: no address, no personal identifiers."""

    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=120)
    email = models.CharField(max_length=254, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=120, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Asset(BaseModel):
    TYPES = [
        ("web_app", "Web application"), ("api", "API"), ("host", "Host"),
        ("network_range", "Network range"), ("mobile_app", "Mobile application"),
        ("cloud_account", "Cloud account"), ("source_repo", "Source repository"),
        ("wireless", "Wireless network"), ("iot", "IoT or embedded device"),
        ("active_directory", "Active Directory"), ("thick_client", "Thick client"),
        ("other", "Other"),
    ]  # fmt: skip
    ENVIRONMENTS = [("prod", "Production"), ("staging", "Staging"), ("dev", "Development")]
    ONBOARDING = [("onboarded", "Onboarded"), ("pending", "Not onboarded")]
    ORIGINS = [("manual", "Added by hand"), ("import", "Imported")]

    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="assets")
    name = models.CharField(max_length=160)
    type = models.CharField(max_length=24, choices=TYPES)
    # Display copy of the primary identifier (kept for older clients and CSV matching). The identifiers
    # themselves live in AssetIdentifier; never write this field directly.
    identifier = models.CharField(max_length=500, blank=True)
    environment = models.CharField(max_length=10, choices=ENVIRONMENTS, default="prod")
    criticality = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])
    tags = models.JSONField(default=list, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    onboarding_status = models.CharField(max_length=10, choices=ONBOARDING, default="onboarded", db_index=True)
    origin = models.CharField(max_length=8, choices=ORIGINS, default="manual")
    onboarded_at = models.DateTimeField(null=True, blank=True)
    onboarded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(criticality__gte=1, criticality__lte=5), name="asset_criticality_1_5"
            ),
        ]

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_status == "onboarded"

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class AssetIdentifier(BaseModel):
    """One way an asset is known: an IP, a hostname, a domain, a URL ...

    ``match_key`` is unique per organisation, so the same identifier can never belong to two assets.
    ``organisation`` repeats the asset's organisation so the database can enforce that.
    """

    SOURCES = [("manual", "Added by hand"), ("import", "Imported"), ("legacy", "Migrated from the old field")]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="identifiers")
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=KINDS)
    value = models.CharField(max_length=500)  # as entered
    normalized = models.CharField(max_length=500)
    match_key = models.CharField(max_length=520)
    is_primary = models.BooleanField(default=False)
    source = models.CharField(max_length=8, choices=SOURCES, default="manual")

    class Meta:
        ordering = ["-is_primary", "kind", "normalized"]
        constraints = [
            models.UniqueConstraint(fields=["organisation", "match_key"], name="uniq_asset_identifier_org_key"),
            models.UniqueConstraint(
                fields=["asset"], condition=models.Q(is_primary=True), name="uniq_asset_primary_identifier"
            ),
        ]
        indexes = [models.Index(fields=["asset"], name="assetident_asset")]

    def audit_label(self) -> str:
        return f"{self.kind}: {self.value}"

    def __str__(self) -> str:
        return self.value
