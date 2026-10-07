from rest_framework import serializers

from apps.console.models import UsageMetric


class UsageMetricSerializer(serializers.ModelSerializer):
    """Serializer read-only de UsageMetric."""

    class Meta:
        model = UsageMetric
        fields = [
            'id', 'key', 'name', 'unit',
            'kind', 'origin', 'description',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']