from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from apps.console.models import ConsoleMembership
from apps.console.services.membership_service import ConsoleMembershipService

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    """Serializer para exibição de membros do Console."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_avatar = serializers.CharField(
        source='user.avatar', read_only=True, allow_null=True
    )
    created_by_email = serializers.EmailField(
        source='created_by.email', read_only=True, allow_null=True
    )

    class Meta:
        model = ConsoleMembership
        fields = [
            'id', 'user', 'user_email', 'user_full_name', 'user_avatar',
            'created_at', 'updated_at', 'created_by_email',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_email']


class MembershipCreateSerializer(serializers.Serializer):
    """
    Serializer para criação de membro do Console.

    Aceita DUAS formas de identificação:
    - user_id: quando o usuário já existe no banco
    - email: quando o usuário pode já existir OU precisa ser criado

    REGRA V1:
        Todo membro do Console é administrador integral.
        Não há escolha de governança.
    """

    user_id = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        user_id = attrs.get('user_id')
        email = attrs.get('email')

        if not user_id and not email:
            raise serializers.ValidationError(_('Informe user_id ou email'))

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
                # Cria conta pendente — será vinculada ao Google no
                # primeiro login (via CustomSocialAccountAdapter).
                user = User.objects.create_user(
                    email=email,
                    password=None,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save(update_fields=['password'])

        if not user.is_active:
            raise serializers.ValidationError(
                _('Usuário inativo não pode ser adicionado ao Console')
            )

        service = ConsoleMembershipService()
        if service.has_access(user):
            raise serializers.ValidationError(
                _('Este usuário já é membro do Console')
            )

        attrs['user'] = user
        return attrs