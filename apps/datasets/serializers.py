from rest_framework import serializers

from .models import ImageAsset, ImagePurpose, Module, Upload


class ImageAssetSerializer(serializers.ModelSerializer):
    """Read serializer; includes the absolute file URL for frontend consumption."""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageAsset
        fields = (
            'id',
            'module',
            'purpose',
            'upload',
            'file',
            'file_url',
            'captured_at',
            'flash_fired',
            'exif',
            'site',
            'plot',
            'weather',
            'notes',
            'excluded',
            'exclusion_reason',
            'total_open_flowers',
            'total_pollinators',
            'pollinator_types_present',
            'metadata',
            'uploaded_at',
        )
        read_only_fields = (
            'id',
            'file_url',
            'captured_at',
            'flash_fired',
            'exif',
            'uploaded_at',
        )

    def get_file_url(self, obj: ImageAsset) -> str | None:
        request = self.context.get('request')
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ImageUploadSerializer(serializers.Serializer):
    """Write serializer; validates the multipart upload fields."""

    file = serializers.ImageField()
    module = serializers.ChoiceField(choices=Module.choices)
    purpose = serializers.ChoiceField(
        choices=ImagePurpose.choices,
        default=ImagePurpose.INFERENCE,
    )
    upload = serializers.PrimaryKeyRelatedField(
        queryset=Upload.objects.all(),
        required=False,
        allow_null=True,
    )


class UploadSerializer(serializers.ModelSerializer):
    """Read serializer for an upload batch.

    image_count is exposed as a regular field; views that list uploads
    annotate the queryset for efficiency, others fall back to a count().
    """

    image_count = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = ('id', 'name', 'module', 'status', 'image_count', 'created_at')
        read_only_fields = ('id', 'status', 'image_count', 'created_at')

    def get_image_count(self, obj: Upload) -> int:
        annotated = getattr(obj, 'image_count_annotated', None)
        if annotated is not None:
            return annotated
        return obj.images.count()


class UploadCreateSerializer(serializers.ModelSerializer):
    """Write serializer for POST /api/datasets/uploads/."""

    class Meta:
        model = Upload
        fields = ('name', 'module')
