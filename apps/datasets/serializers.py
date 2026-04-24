from rest_framework import serializers

from .models import ImageAsset, ImagePurpose, Module


class ImageAssetSerializer(serializers.ModelSerializer):
    """Read serializer — includes the absolute file URL for frontend consumption."""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageAsset
        fields = (
            'id', 'module', 'purpose', 'file', 'file_url',
            'captured_at', 'flash_fired', 'exif',
            'site', 'plot', 'weather', 'notes',
            'excluded', 'exclusion_reason',
            'total_open_flowers', 'total_pollinators', 'pollinator_types_present',
            'metadata', 'uploaded_at',
        )
        read_only_fields = (
            'id', 'file_url', 'captured_at', 'flash_fired', 'exif',
            'uploaded_at',
        )

    def get_file_url(self, obj: ImageAsset) -> str | None:
        request = self.context.get('request')
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ImageUploadSerializer(serializers.Serializer):
    """Write serializer — validates the multipart upload fields."""

    file = serializers.ImageField()
    module = serializers.ChoiceField(choices=Module.choices)
    purpose = serializers.ChoiceField(
        choices=ImagePurpose.choices, default=ImagePurpose.INFERENCE,
    )
