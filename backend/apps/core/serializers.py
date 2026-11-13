from rest_framework import serializers


class StrictSerializerMixin:
    """Reject unknown and read-only keys instead of silently ignoring them (mass assignment)."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            writable = {name for name, f in self.fields.items() if not f.read_only}
            unknown = set(data) - writable
            if unknown:
                raise serializers.ValidationError({key: ["Unknown or read-only field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class StrictSerializer(StrictSerializerMixin, serializers.Serializer):
    pass
