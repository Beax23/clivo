from rest_framework import serializers

from apps.console.models import ConsoleCapability


class CapabilitySerializer(serializers.ModelSerializer):
    """Serializer para capabilities."""

    class Meta:
        model = ConsoleCapability
        fields = [
            'id', 'code', 'name', 'description',
            'source_app', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']