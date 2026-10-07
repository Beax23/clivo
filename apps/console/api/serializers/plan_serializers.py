import re
from rest_framework import serializers
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.console.models import Plan, PlanFeatureLimit, UsageMetric


# =========================================================================
# PLAN FEATURE LIMIT
# =========================================================================

class PlanFeatureLimitSerializer(serializers.ModelSerializer):
    """Serializer de leitura de PlanFeatureLimit."""

    metric_key = serializers.CharField(source='metric.key', read_only=True)
    metric_name = serializers.CharField(source='metric.name', read_only=True)
    metric_unit = serializers.CharField(source='metric.unit', read_only=True)
    feature_key = serializers.CharField(
        source='plan_feature.feature.key', read_only=True
    )
    feature_name = serializers.CharField(
        source='plan_feature.feature.name', read_only=True
    )
    plan_key = serializers.CharField(
        source='plan_feature.plan.key', read_only=True
    )
    plan_name = serializers.CharField(
        source='plan_feature.plan.name', read_only=True
    )

    class Meta:
        model = PlanFeatureLimit
        fields = [
            'id',
            'plan_feature',
            'plan_key', 'plan_name',
            'feature_key', 'feature_name',
            'metric', 'metric_key', 'metric_name', 'metric_unit',
            'limit_value', 'period', 'behavior',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlanFeatureLimitWriteSerializer(serializers.Serializer):
    """
    Serializer para definir limites de uma Feature dentro de um Plano.

    Recebe uma lista de limites:
        [
            {"metric_key": "ai.credits", "limit_value": 1000,
             "period": "monthly", "behavior": "hard_limit"},
            ...
        ]

    `limit_value = null` significa ilimitado.
    """

    metric_key = serializers.CharField()
    limit_value = serializers.IntegerField(
        required=False, allow_null=True, min_value=0
    )
    period = serializers.ChoiceField(
        choices=['monthly', 'current', 'lifetime'],
        default='monthly',
    )
    behavior = serializers.ChoiceField(
        choices=['hard_limit', 'soft_limit', 'overage_allowed'],
        default='hard_limit',
    )

    def validate_metric_key(self, value):
        if not UsageMetric.objects.filter(key=value, is_active=True).exists():
            raise serializers.ValidationError(
                _('Métrica "%(key)s" não encontrada ou inativa') % {'key': value}
            )
        return value


# =========================================================================
# PLAN
# =========================================================================

class PlanSerializer(serializers.ModelSerializer):
    """Serializer de leitura de Plan."""

    features = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            'id', 'key', 'name', 'description',
            'price', 'currency', 'billing_period',
            'default_trial_days',
            'is_active', 'is_public', 'is_default',
            'features',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_features(self, obj):
        """Lista features do plano, com seus limites aninhados."""
        result = []
        for pf in obj.plan_features.select_related('feature').all():
            limits = [
                PlanFeatureLimitSerializer(lim).data
                for lim in pf.limits.select_related('metric').all()
            ]
            result.append({
                'id': str(pf.id),
                'feature_id': str(pf.feature_id),
                'feature_key': pf.feature.key,
                'feature_name': pf.feature.name,
                'limits': limits,
            })
        return result


class PlanCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para criar Plan.

    A `key` é gerada automaticamente a partir do `name` (slug).
    """

    class Meta:
        model = Plan
        fields = [
            'name', 'description',
            'price', 'currency', 'billing_period',
            'default_trial_days',
            'is_active', 'is_public', 'is_default',
        ]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_('O nome é obrigatório'))
        return value.strip()

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_('O preço não pode ser negativo'))
        return value

    def create(self, validated_data):
        # Gera key a partir do nome (slug)
        base_key = slugify(validated_data['name']).replace('-', '_')
        base_key = re.sub(r'[^a-z0-9_]', '', base_key) or 'plan'

        # Garante unicidade
        key = base_key
        counter = 1
        while Plan.objects.filter(key=key).exists():
            counter += 1
            key = f"{base_key}_{counter}"

        validated_data['key'] = key
        return super().create(validated_data)


class PlanUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualizar Plan.

    Planos de sistema PODEM ser editados.
    O bloqueio existe apenas para exclusão (feito no ViewSet).
    """

    class Meta:
        model = Plan
        fields = [
            'name', 'description',
            'price', 'currency', 'billing_period',
            'default_trial_days',
            'is_active', 'is_public', 'is_default',
        ]

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_('O preço não pode ser negativo'))
        return value