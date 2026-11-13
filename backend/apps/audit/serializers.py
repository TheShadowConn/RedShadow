from rest_framework import serializers

from .models import AuditEvent, IntegrityCheck


class AuditEventSerializer(serializers.ModelSerializer):
    """IP, user agent and hash fields are for Super Admin only (``context["full"]``)."""

    engagement = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id", "occurred_at", "actor_id", "actor_label", "request_id", "action", "entity_type", "entity_id",
            "entity_label", "engagement", "changes", "metadata", "outcome",
        ]  # fmt: skip
        read_only_fields = fields

    def get_engagement(self, obj):
        return {"id": obj.engagement_id, "ref": obj.engagement_ref} if obj.engagement_id else None

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if self.context.get("full"):
            data.update(actor_ip=obj.actor_ip, user_agent=obj.user_agent, hash=obj.hash, prev_hash=obj.prev_hash)
        return data


class IntegrityCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrityCheck
        fields = ["id", "status", "trigger", "requested_by_label", "started_at", "finished_at", "checked",
                  "first_bad_id", "reason"]  # fmt: skip
        read_only_fields = fields
