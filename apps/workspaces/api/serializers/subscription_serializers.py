from rest_framework import serializers

from apps.workspaces.models import WorkspaceSubscription


class WorkspaceSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer read-only de WorkspaceSubscription.

    Expõe os dados do Plan para conveniência do frontend.
    """

    plan_key = serializers.CharField(source='plan.key', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_price = serializers.DecimalField(
        source='plan.price', max_digits=10, decimal_places=2, read_only=True
    )
    plan_currency = serializers.CharField(source='plan.currency', read_only=True)
    plan_billing_period = serializers.CharField(
        source='plan.billing_period', read_only=True
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
            'created_at', 'updated_at',
        ]
        read_only_fields = fields