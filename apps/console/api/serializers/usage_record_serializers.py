from rest_framework import serializers

from apps.console.models import UsageRecord


class UsageRecordSerializer(serializers.ModelSerializer):
    """
    Serializer read-only de UsageRecord.

    A criação NÃO é exposta via API pública.
    Só o UsageRecordService cria registros.
    """

    provider_name = serializers.CharField(source='provider.name', read_only=True)
    provider_key = serializers.CharField(source='provider.key', read_only=True)
    metric_key = serializers.CharField(source='metric.key', read_only=True)
    metric_name = serializers.CharField(source='metric.name', read_only=True)

    class Meta:
        model = UsageRecord
        fields = [
            'id',
            'provider', 'provider_name', 'provider_key',
            'connection',
            'metric', 'metric_key', 'metric_name',
            'workspace_id',
            'occurred_at',
            'quantity', 'unit',
            'request_id', 'operation', 'model',
            'metadata',
            'estimated_cost', 'currency',
            'status',
            'created_at',
        ]
        read_only_fields = fields