"""
Serializer de DocumentHistory.

Histórico é READ-ONLY. A criação é feita exclusivamente por
`DocumentHistoryService.log()`. Não existe endpoint público
para criação de histórico.
"""

from rest_framework import serializers

from apps.documents.models import DocumentHistory


class DocumentHistorySerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de DocumentHistory.

    `document` pode ser null (histórico órfão após exclusão).
    `user` pode ser null (usuário removido do Clivo).
    """

    action_display = serializers.CharField(
        source='get_action_display', read_only=True
    )

    user_name = serializers.CharField(
        source='user.full_name', read_only=True, allow_null=True
    )
    user_email = serializers.EmailField(
        source='user.email', read_only=True, allow_null=True
    )

    class Meta:
        model = DocumentHistory
        fields = [
            'id',
            'document',
            'user', 'user_name', 'user_email',
            'action', 'action_display',
            'timestamp',
            'previous_value',
            'new_value',
        ]
        read_only_fields = fields