from rest_framework import serializers
from django.utils import timezone

from apps.workspaces.models import WorkspaceInvitation


class WorkspaceInvitationSerializer(serializers.ModelSerializer):
    governance_key = serializers.CharField(source='governance.key', read_only=True)
    governance_name = serializers.CharField(source='governance.name', read_only=True)
    invited_by_email = serializers.EmailField(
        source='invited_by.email', read_only=True, allow_null=True
    )
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceInvitation
        fields = [
            'id',
            'workspace',
            'email',
            'governance', 'governance_key', 'governance_name',
            'status',
            'invited_by', 'invited_by_email',
            'created_at', 'updated_at',
            'expires_at',
            'accepted_at',
            'last_sent_at', 'send_count',
            'is_expired',
        ]
        read_only_fields = fields

    def get_is_expired(self, obj):
        return obj.is_expired()


class WorkspaceInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    governance_key = serializers.CharField()

    def validate_email(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError('Informe um email válido')
        return value

    def validate_governance_key(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Escolha uma governança')
        return value


class WorkspaceInvitationUpdateSerializer(serializers.Serializer):
    governance_key = serializers.CharField()

    def validate_governance_key(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Escolha uma governança')
        return value