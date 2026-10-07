from rest_framework import serializers

from apps.console.models import ProviderLog


class ProviderLogSerializer(serializers.ModelSerializer):
    """
    Serializer read-only de ProviderLog.

    A criação NÃO é exposta via API pública.
    Só o ProviderLogService cria registros.
    """

    provider_name = serializers.CharField(source='provider.name', read_only=True)
    provider_key = serializers.CharField(source='provider.key', read_only=True)

    class Meta:
        model = ProviderLog
        fields = [
            'id',
            'provider', 'provider_name', 'provider_key',
            'connection',
            'workspace_id',
            'occurred_at',
            'operation', 'model', 'status',
            'latency_ms', 'input_units', 'output_units',
            'estimated_cost', 'currency',
            'request_id', 'correlation_id',
            'error_message', 'metadata',
            'created_at',
        ]
        read_only_fields = fields