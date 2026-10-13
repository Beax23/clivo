"""
Serializer de ReferenceHistory.

Histórico é READ-ONLY. A criação é feita exclusivamente por
`ReferenceHistoryService.log()`. Não existe endpoint público
para criação de histórico.
"""

from rest_framework import serializers

from apps.references.models import ReferenceHistory


class ReferenceHistorySerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de ReferenceHistory.

    `reference` pode ser null (histórico órfão após exclusão).
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
        model = ReferenceHistory
        fields = [
            'id',
            'reference',
            'user', 'user_name', 'user_email',
            'action', 'action_display',
            'timestamp',
            'previous_value',
            'new_value',
        ]
        read_only_fields = fields