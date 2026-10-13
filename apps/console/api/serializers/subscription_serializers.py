"""
Serializer de resposta para a action `change_plan`.

Expõe a assinatura resultante com os dados do plano e a auditoria
de troca (`changed_by`, `changed_from`, `reason`).
"""

from rest_framework import serializers

from apps.workspaces.models import WorkspaceSubscription


class AdminWorkspaceSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer read-only da assinatura ativa após troca de plano."""

    plan_key = serializers.CharField(source='plan.key', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_price = serializers.DecimalField(
        source='plan.price', max_digits=10, decimal_places=2, read_only=True,
    )
    plan_currency = serializers.CharField(source='plan.currency', read_only=True)
    plan_billing_period = serializers.CharField(
        source='plan.billing_period', read_only=True,
    )

    changed_by_email = serializers.EmailField(
        source='changed_by.email', read_only=True, allow_null=True,
    )
    changed_from_id = serializers.UUIDField(
        source='changed_from.id', read_only=True, allow_null=True,
    )

    class Meta:
        model = WorkspaceSubscription
        fields = [
            'id',
            'workspace',
            'plan', 'plan_key', 'plan_name',
            'plan_price', 'plan_currency', 'plan_billing_period',
            'is_active',
            'started_at', 'ended_at',
            'reason',
            'changed_by', 'changed_by_email',
            'changed_from', 'changed_from_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields