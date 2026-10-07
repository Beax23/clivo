"""
Serializer administrativo de User para o Console.

O Console pode listar TODOS os usuários (não só os ConsoleMembers),
porque ConsoleMembership dá acesso administrativo integral.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer de leitura de User para o Console."""

    workspaces_count = serializers.SerializerMethodField()
    is_console_member = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email',
            'full_name',
            'avatar',
            'is_active', 'is_staff', 'is_superuser',
            'workspaces_count',
            'is_console_member',
            'last_login',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_workspaces_count(self, obj):
        return obj.workspace_memberships.count()

    def get_is_console_member(self, obj):
        return hasattr(obj, 'console_membership')