from rest_framework import serializers

from .models import ImageAsset, ImagePurpose, Module, Upload, UploadStatus


class UploadSerializer(serializers.ModelSerializer):
    image_count = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = (
            'id', 'module', 'name', 'status',
            'created_by', 'created_at', 'notes', 'image_count',
        )
        read_only_fields = ('id', 'created_by', 'created_at', 'image_count')

    def get_image_count(self, obj: Upload) -> int:
        return obj.images.count()


class UploadCreateSerializer(serializers.Serializer):
    module = serializers.ChoiceField(choices=Module.choices)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class UploadUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=UploadStatus.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class ImageAssetSerializer(serializers.ModelSerializer):
    """Read serializer — includes the absolute file URL for frontend consumption."""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageAsset
        fields = (
            'id', 'module', 'purpose', 'file', 'file_url',
            'upload',
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
    upload = serializers.PrimaryKeyRelatedField(
        queryset=Upload.objects.all(), required=False, allow_null=True,
    )
