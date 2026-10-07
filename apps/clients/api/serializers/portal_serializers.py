from rest_framework import serializers

from apps.clients.models import (
    ClientPortalSession,
    ClientPortalAccess,
    ClientPortalInvitation,
    ClientPortalFeedback,
)


class PortalSessionSerializer(serializers.ModelSerializer):
    """
    NUNCA expõe token_hash.
    """

    class Meta:
        model = ClientPortalSession
        fields = [
            'id', 'client',
            'created_at', 'expires_at',
            'last_used_at', 'revoked_at',
        ]
        read_only_fields = fields


class PortalAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientPortalAccess
        fields = ['id', 'client', 'session', 'ip_address', 'user_agent', 'accessed_at']
        read_only_fields = fields


class PortalInvitationSerializer(serializers.ModelSerializer):
    sent_by_email = serializers.EmailField(
        source='sent_by.email', read_only=True, allow_null=True
    )

    class Meta:
        model = ClientPortalInvitation
        fields = [
            'id', 'client', 'session', 'email',
            'sent_by', 'sent_by_email',
            'status', 'error_message', 'sent_at',
        ]
        read_only_fields = fields


class PortalFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientPortalFeedback
        fields = [
            'id', 'client', 'kind', 'rating', 'message', 'page', 'created_at',
        ]
        read_only_fields = fields


class PortalFeedbackCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[c[0] for c in ClientPortalFeedback.KIND_CHOICES],
    )
    rating = serializers.ChoiceField(
        choices=[c[0] for c in ClientPortalFeedback.RATING_CHOICES],
        required=False,
        allow_blank=True,
    )
    message = serializers.CharField(required=False, allow_blank=True)
    page = serializers.CharField(required=False, allow_blank=True)


class PortalContextSerializer(serializers.Serializer):
    """
    Contexto público do cliente — o que o Portal expõe.

    NÃO expõe dados internos (notas internas, tarefas, timeline).
    Apenas o que o arquiteto publicou via `Client.context`.
    """

    public_code = serializers.CharField()
    name = serializers.CharField()
    context = serializers.DictField()