from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.console.models import ProviderPricing


class ProviderPricingSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    provider_key = serializers.CharField(source='provider.key', read_only=True)
    metric_key = serializers.CharField(source='metric.key', read_only=True)
    metric_name = serializers.CharField(source='metric.name', read_only=True)
    metric_unit = serializers.CharField(source='metric.unit', read_only=True)
    contract_name = serializers.CharField(
        source='contract.name', read_only=True, allow_null=True
    )

    class Meta:
        model = ProviderPricing
        fields = [
            'id',
            'provider', 'provider_name', 'provider_key',
            'contract', 'contract_name',
            'metric', 'metric_key', 'metric_name', 'metric_unit',
            'identifier',
            'pricing_model', 'unit_price', 'currency',
            'minimum_charge', 'included_quantity',
            'starts_at', 'ends_at',
            'is_active', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProviderPricingWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderPricing
        fields = [
            'provider', 'contract', 'metric', 'identifier',
            'pricing_model', 'unit_price', 'currency',
            'minimum_charge', 'included_quantity',
            'starts_at', 'ends_at', 'is_active', 'notes',
        ]

    def validate(self, attrs):
        # Corrige PATCH
        starts = attrs.get(
            'starts_at',
            self.instance.starts_at if self.instance else None,
        )
        ends = attrs.get(
            'ends_at',
            self.instance.ends_at if self.instance else None,
        )
        if starts and ends and ends < starts:
            raise serializers.ValidationError({
                'ends_at': _('Fim deve ser posterior ao início')
            })

        # Valida coerência provider ↔ contract
        provider = attrs.get('provider', self.instance.provider if self.instance else None)
        contract = attrs.get('contract', self.instance.contract if self.instance else None)
        if contract and provider and contract.provider_id != provider.id:
            raise serializers.ValidationError({
                'contract': _(
                    'O contrato selecionado pertence a outro provider.'
                )
            })

        return attrs