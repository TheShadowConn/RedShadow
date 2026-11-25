from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import BaseModel, SoftDeleteModel

OPEN_STATUSES = ("planned", "scheduled", "in_progress", "reporting")


class EngagementCounter(models.Model):
    """One row per year. Locked with SELECT ... FOR UPDATE so refs never collide."""

    year = models.PositiveSmallIntegerField(primary_key=True)
    last = models.PositiveIntegerField(default=0)


class Engagement(SoftDeleteModel, BaseModel):
    """``objects`` hides soft-deleted engagements; ``all_objects`` shows them (audit and DBA only)."""

    TYPES = [
        ("web", "Web"), ("api", "API"), ("mobile", "Mobile"),
        ("internal_network", "Internal network"), ("external_network", "External network"),
        ("cloud", "Cloud"), ("red_team", "Red team"), ("social_engineering", "Social engineering"),
        ("code_review", "Code review"), ("wireless", "Wireless"), ("other", "Other"),
    ]  # fmt: skip
    STATUSES = [
        ("planned", "Planned"), ("scheduled", "Scheduled"), ("in_progress", "In progress"),
        ("reporting", "Reporting"), ("completed", "Completed"), ("cancelled", "Cancelled"),
        ("archived", "Archived"),
    ]  # fmt: skip

    ref = models.CharField(max_length=20, unique=True)
    organisation = models.ForeignKey("organisations.Organisation", on_delete=models.PROTECT, related_name="engagements")
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=24, choices=TYPES)
    status = models.CharField(max_length=16, choices=STATUSES, default="planned", db_index=True)
    status_before_archive = models.CharField(max_length=16, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    scope = models.TextField(blank=True)
    out_of_scope = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    rules_of_engagement = models.TextField(blank=True)
    lead = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField(default=1)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    deleted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    assets = models.ManyToManyField("organisations.Asset", through="EngagementAsset", related_name="engagements")

    class Meta:
        ordering = ["-start_date", "ref"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="engagement_dates_ordered")
        ]
        indexes = [models.Index(fields=["organisation", "status"]), models.Index(fields=["start_date", "end_date"])]

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def audit_label(self) -> str:
        return f"{self.ref} {self.name}"

    def __str__(self) -> str:
        return self.ref


class EngagementAsset(BaseModel):
    """Asset in an engagement. A DB trigger (migration 0001) rejects assets of another organisation."""

    engagement = models.ForeignKey(Engagement, on_delete=models.PROTECT, related_name="engagement_assets")
    asset = models.ForeignKey("organisations.Asset", on_delete=models.PROTECT, related_name="engagement_assets")
    in_scope = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["engagement", "asset"], name="uniq_engagement_asset")]


class EngagementMembership(BaseModel):
    FINDING_SCOPES = [("all", "All findings"), ("assigned", "Assigned findings only"), ("own", "Own findings only")]

    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="engagement_memberships")
    role_override = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    finding_scope = models.CharField(max_length=16, choices=FINDING_SCOPES, blank=True)
    added_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["engagement", "user"], name="uniq_engagement_member")]
        indexes = [models.Index(fields=["user"])]

    @property
    def effective_role(self):
        return self.role_override or self.user.role


class EngagementNote(BaseModel):
    VISIBILITY = [("team", "Team only"), ("all", "All members")]

    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    visibility = models.CharField(max_length=8, choices=VISIBILITY, default="team")

    class Meta:
        ordering = ["-created_at"]


# ISO 4217 codes offered in the UI and accepted by the API. Money is never converted between currencies.
CURRENCIES = [
    ("USD", "US dollar"), ("EUR", "Euro"), ("GBP", "Pound sterling"), ("INR", "Indian rupee"),
    ("AED", "UAE dirham"), ("SAR", "Saudi riyal"), ("QAR", "Qatari riyal"), ("KWD", "Kuwaiti dinar"),
    ("BHD", "Bahraini dinar"), ("OMR", "Omani rial"), ("SGD", "Singapore dollar"), ("MYR", "Malaysian ringgit"),
    ("AUD", "Australian dollar"), ("NZD", "New Zealand dollar"), ("CAD", "Canadian dollar"),
    ("CHF", "Swiss franc"), ("SEK", "Swedish krona"), ("NOK", "Norwegian krone"), ("DKK", "Danish krone"),
    ("PLN", "Polish zloty"), ("CZK", "Czech koruna"), ("ZAR", "South African rand"), ("NGN", "Nigerian naira"),
    ("KES", "Kenyan shilling"), ("EGP", "Egyptian pound"), ("TRY", "Turkish lira"), ("ILS", "Israeli shekel"),
    ("JPY", "Japanese yen"), ("CNY", "Chinese yuan"), ("HKD", "Hong Kong dollar"), ("KRW", "South Korean won"),
    ("THB", "Thai baht"), ("IDR", "Indonesian rupiah"), ("PHP", "Philippine peso"), ("VND", "Vietnamese dong"),
    ("PKR", "Pakistani rupee"), ("BDT", "Bangladeshi taka"), ("LKR", "Sri Lankan rupee"),
    ("BRL", "Brazilian real"), ("MXN", "Mexican peso"), ("ARS", "Argentine peso"), ("CLP", "Chilean peso"),
    ("COP", "Colombian peso"), ("RUB", "Russian rouble"), ("UAH", "Ukrainian hryvnia"),
]  # fmt: skip
CURRENCY_CODES = [code for code, _ in CURRENCIES]


class EngagementCost(BaseModel):
    """One cost line of an engagement. An engagement can hold lines in several currencies."""

    CATEGORIES = [
        ("labour", "Labour"), ("tools", "Tools and licences"), ("travel", "Travel"),
        ("subcontractor", "Subcontractor"), ("other", "Other"),
    ]  # fmt: skip

    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name="costs")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    category = models.CharField(max_length=16, choices=CATEGORIES, default="other")
    description = models.CharField(max_length=300, blank=True)
    incurred_on = models.DateField()
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-incurred_on", "-created_at"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="engagement_cost_positive")]
        indexes = [models.Index(fields=["engagement", "currency"])]

    def audit_label(self) -> str:
        return f"{self.amount} {self.currency}"


CATEGORY_CODES = [code for code, _ in EngagementCost.CATEGORIES]


class EngagementScenario(BaseModel):
    """One use case or test scenario inside an engagement.

    A scenario only records what is tested and when. It has no owner: the engagement lead owns the work, and
    findings belong to the engagement, never to a scenario. The name is exactly what the user typed.
    """

    STATUSES = [
        ("planned", "Planned"), ("in_progress", "In progress"), ("tested", "Tested"),
        ("deferred", "Deferred"), ("cancelled", "Cancelled"),
    ]  # fmt: skip

    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="planned")
    status_reason = models.CharField(max_length=500, blank=True)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "engagement", name="uniq_scenario_name_per_engagement"
            ),
            models.CheckConstraint(
                condition=Q(planned_start__isnull=True) | Q(planned_end__isnull=True)
                | Q(planned_end__gte=models.F("planned_start")),
                name="scenario_dates_ordered",
            ),
        ]
        indexes = [models.Index(fields=["engagement", "status"], name="scenario_eng_status")]

    def audit_label(self) -> str:
        return self.name
