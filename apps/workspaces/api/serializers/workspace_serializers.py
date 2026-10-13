import re
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.workspaces.models import Workspace
from apps.workspaces.public_id import encode_workspace_id


class WorkspaceSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de Workspace.

    - `id` é o UUID real (usado em chamadas API).
    - `public_id` é o token ofuscado (usado em URLs do browser).
    """

    plan = serializers.SerializerMethodField()
    members_count = serializers.SerializerMethodField()
    public_id = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            'id', 'public_id', 'name', 'slug',
            'cnpj', 'city', 'state',
            'is_active',
            'plan',
            'members_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'public_id', 'slug', 'created_at', 'updated_at',
            'plan', 'members_count',
        ]

    def get_public_id(self, obj):
        return encode_workspace_id(obj.id)

    def get_plan(self, obj):
        """
        Plano da assinatura ATIVA do workspace.

        `active_subscription` já filtra `is_active=True` — não é
        preciso checar isso aqui. Retorna `None` se não houver
        assinatura ativa ou se o plano não existir.
        """
        sub = obj.active_subscription
        if sub and sub.plan:
            return {
                'id': str(sub.plan.id),
                'key': sub.plan.key,
                'name': sub.plan.name,
                'price': str(sub.plan.price),
                'currency': sub.plan.currency,
                'billing_period': sub.plan.billing_period,
            }
        return None

    def get_members_count(self, obj):
        return obj.memberships.count()


class WorkspaceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ['name', 'cnpj', 'city', 'state']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_('O nome é obrigatório'))
        return value.strip()

    def validate_cnpj(self, value):
        if not value:
            return ''
        return value.strip()

    def validate_city(self, value):
        if not value:
            return ''
        return value.strip()

    def validate_state(self, value):
        if not value:
            return ''
        value = value.strip().upper()
        if len(value) != 2:
            raise serializers.ValidationError(
                _('A UF deve ter exatamente 2 caracteres')
            )
        return value


class WorkspaceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ['name', 'cnpj', 'city', 'state', 'is_active']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_('O nome é obrigatório'))
        return value.strip()

    def validate_cnpj(self, value):
        if not value:
            return ''
        return value.strip()

    def validate_city(self, value):
        if not value:
            return ''
        return value.strip()

    def validate_state(self, value):
        if not value:
            return ''
        value = value.strip().upper()
        if len(value) != 2:
            raise serializers.ValidationError(
                _('A UF deve ter exatamente 2 caracteres')
            )
        return value