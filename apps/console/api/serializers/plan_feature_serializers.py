from rest_framework import serializers

from apps.console.models import PlanFeature


class PlanFeatureSerializer(serializers.ModelSerializer):
    """Serializer de leitura de PlanFeature."""

    plan_key = serializers.CharField(source='plan.key', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    feature_key = serializers.CharField(source='feature.key', read_only=True)
    feature_name = serializers.CharField(source='feature.name', read_only=True)

    class Meta:
        model = PlanFeature
        fields = [
            'id',
            'plan', 'plan_key', 'plan_name',
            'feature', 'feature_key', 'feature_name',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class PlanFeatureWriteSerializer(serializers.ModelSerializer):
    """Serializer para associar/desassociar Feature a Plan."""

    class Meta:
        model = PlanFeature
        fields = ['plan', 'feature']

    def validate(self, attrs):
        plan = attrs.get('plan')
        feature = attrs.get('feature')

        if plan and feature:
            qs = PlanFeature.objects.filter(plan=plan, feature=feature)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'Esta feature já está associada a este plano.'
                )
        return attrs