from rest_framework import serializers

from apps.core.serializers import StrictSerializer

from .models import Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    is_image = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id",
            "kind",
            "engagement",
            "finding",
            "is_image",
            "original_name",
            "mime",
            "size",
            "sha256",
            "uploaded_by",
            "download_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_uploaded_by(self, obj):
        return {"id": obj.uploaded_by_id, "display_name": obj.uploaded_by.display_name}

    def get_is_image(self, obj):
        return obj.mime.startswith("image/")

    def get_download_url(self, obj):
        return f"/api/v1/attachments/{obj.pk}/download"


class UploadSerializer(StrictSerializer):
    file = serializers.FileField(allow_empty_file=False, max_length=255)
