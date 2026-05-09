from rest_framework import serializers

from .models import ModelVersion


class ModelVersionSerializer(serializers.ModelSerializer):
    """Read serializer for trained model versions.

    Exposes the fields the frontend's run-config and models pages consume.
    Training-job-derived fields (samples, training_duration, charts) are
    deliberately omitted at this tier; they will join in once the
    TrainingJob link is wired.
    """

    class Meta:
        model = ModelVersion
        fields = (
            'id',
            'module',
            'kind',
            'version_name',
            'is_active',
            'metrics',
            'parameters',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')
