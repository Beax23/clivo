from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from apps.workspaces.models import WorkspaceMembership

User = get_user_model()


class WorkspaceMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de WorkspaceMembership.

    `created_at` foi removido do model — não aparece aqui.
    """

    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_avatar = serializers.CharField(
        source='user.avatar', read_only=True, allow_null=True
    )

    governance_key = serializers.CharField(source='governance.key', read_only=True)
    governance_name = serializers.CharField(source='governance.name', read_only=True)

    class Meta:
        model = WorkspaceMembership
        fields = [
            'id',
            'workspace',
            'user', 'user_email', 'user_full_name', 'user_avatar',
            'governance', 'governance_key', 'governance_name',
            'joined_at',
            'last_access_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'workspace', 'user',
            'joined_at', 'updated_at',
        ]


class WorkspaceMembershipCreateSerializer(serializers.Serializer):
    """
    Serializer para adicionar membro ao Workspace.

    Aceita DUAS formas:
        - user_id: usuário já existente
        - email: usuário pode já existir OU precisa ser criado

    A governança é escolhida no momento da adição.
    O service valida que a governança tem scope='workspace'.
    """

    user_id = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    governance_key = serializers.CharField()

    def validate(self, attrs):
        user_id = attrs.get('user_id')
        email = attrs.get('email')
        governance_key = (attrs.get('governance_key') or '').strip()

        if not user_id and not email:
            raise serializers.ValidationError(_('Informe user_id ou email'))

        if not governance_key:
            raise serializers.ValidationError(
                {'governance_key': _('A governança é obrigatória')}
            )

        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except (User.DoesNotExist, ValueError):
                raise serializers.ValidationError(
                    {'user_id': _('Usuário não encontrado')}
                )
        elif email:
            email = User.normalize_email(email)
            user = User.objects.filter(email__iexact=email).first()

            if not user:
                # Cria conta pendente — vinculada ao Google no primeiro login
                user = User.objects.create_user(
                    email=email,
                    password=None,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save(update_fields=['password'])

        attrs['user'] = user
        attrs['governance_key'] = governance_key
        return attrs


class WorkspaceMembershipUpdateSerializer(serializers.Serializer):
    """Serializer para alterar a governança de um membro."""

    governance_key = serializers.CharField()

    def validate_governance_key(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError(_('A governança é obrigatória'))
        return value