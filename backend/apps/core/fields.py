from rest_framework import serializers


class ScopedPrimaryKeyField(serializers.PrimaryKeyRelatedField):
    """Foreign key in a request body, resolved only inside the caller's scope.

    A UUID the user cannot reach is reported as nonexistent, so IDs of other organisations
    or engagements cannot be injected into payloads.
    """

    def __init__(self, scope, model, **kwargs):
        self._scope = scope
        super().__init__(queryset=model.objects.none(), **kwargs)

    def get_queryset(self):
        return self._scope(self.context["request"].user)
