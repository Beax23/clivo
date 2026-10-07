"""
Serializer administrativo de Workspace para o Console.

O Console pode listar TODOS os workspaces (não só os do usuário),
porque ConsoleMembership dá acesso administrativo integral.

Este serializer é diferente do `WorkspaceSerializer` usado na Mesa:
    - Expõe `members_count`, `plan_name`, `plan_key`
    - Expõe `governance_keys` (quais governanças estão em uso)
"""

from rest_framework import serializers

from apps.workspaces.models import Workspace


class AdminWorkspaceSerializer(serializers.ModelSerializer):
    """Serializer de leitura de Workspace para o Console."""

    members_count = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    plan_key = serializers.SerializerMethodField()
    plan_currency = serializers.SerializerMethodField()
    plan_price = serializers.SerializerMethodField()
    governance_keys = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            'id', 'name', 'slug',
            'cnpj', 'city', 'state',
            'is_active',
            'members_count',
            'plan_name', 'plan_key', 'plan_currency', 'plan_price',
            'governance_keys',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_members_count(self, obj):
        return obj.memberships.count()

    def _get_subscription(self, obj):
        return getattr(obj, 'subscription', None)

    def get_plan_name(self, obj):
        sub = self._get_subscription(obj)
        return sub.plan.name if sub and sub.plan else None

    def get_plan_key(self, obj):
        sub = self._get_subscription(obj)
        return sub.plan.key if sub and sub.plan else None

    def get_plan_currency(self, obj):
        sub = self._get_subscription(obj)
        return sub.plan.currency if sub and sub.plan else None

    def get_plan_price(self, obj):
        sub = self._get_subscription(obj)
        return str(sub.plan.price) if sub and sub.plan else None

    def get_governance_keys(self, obj):
        """Lista os keys das governanças em uso neste workspace."""
        return list(
            obj.memberships
            .values_list('governance__key', flat=True)
            .distinct()
        )