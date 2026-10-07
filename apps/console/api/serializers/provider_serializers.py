import re
from datetime import timedelta

from rest_framework import serializers
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Sum

from apps.console.models import (
    Provider,
    ProviderConnection,
    ProviderContract,
)


# =========================================================================
# PROVIDER CONNECTION
# =========================================================================

class ProviderConnectionSerializer(serializers.ModelSerializer):
    provider_key = serializers.CharField(source='provider.key', read_only=True)
    provider_name = serializers.CharField(source='provider.name', read_only=True)

    class Meta:
        model = ProviderConnection
        fields = [
            'id', 'provider', 'provider_key', 'provider_name',
            'name', 'environment',
            'credential_ref', 'config',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProviderConnectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderConnection
        fields = [
            'provider', 'name', 'environment',
            'credential_ref', 'config',
            'is_active',
        ]

    def validate_config(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError(_('Config deve ser um objeto JSON'))

        forbidden_keys = {
            'api_key', 'apikey', 'secret', 'password', 'token',
            'access_token', 'private_key',
        }
        found = forbidden_keys & set(k.lower() for k in value.keys())
        if found:
            raise serializers.ValidationError(
                _(
                    'Config não deve conter credenciais (%(keys)s). '
                    'Use `credential_ref` para referenciar o secret manager.'
                ) % {'keys': ', '.join(sorted(found))}
            )
        return value


# =========================================================================
# PROVIDER CONTRACT
# =========================================================================

class ProviderContractSerializer(serializers.ModelSerializer):
    provider_key = serializers.CharField(source='provider.key', read_only=True)
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    connection_name = serializers.CharField(
        source='connection.name', read_only=True, allow_null=True
    )

    class Meta:
        model = ProviderContract
        fields = [
            'id', 'provider', 'provider_key', 'provider_name',
            'connection', 'connection_name',
            'name', 'external_reference',
            'billing_period', 'fixed_cost', 'currency',
            'started_at', 'ends_at',
            'is_active', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProviderContractWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderContract
        fields = [
            'provider', 'connection',
            'name', 'external_reference',
            'billing_period', 'fixed_cost', 'currency',
            'started_at', 'ends_at',
            'is_active', 'notes',
        ]

    def validate(self, attrs):
        starts = attrs.get(
            'started_at',
            self.instance.started_at if self.instance else None,
        )
        ends = attrs.get(
            'ends_at',
            self.instance.ends_at if self.instance else None,
        )
        if starts and ends and ends < starts:
            raise serializers.ValidationError({
                'ends_at': _('Data de término deve ser posterior à de início')
            })

        provider = attrs.get(
            'provider',
            self.instance.provider if self.instance else None,
        )
        connection = attrs.get(
            'connection',
            self.instance.connection if self.instance else None,
        )
        if connection and provider and connection.provider_id != provider.id:
            raise serializers.ValidationError({
                'connection': _(
                    'A conexão selecionada pertence a outro provider.'
                )
            })

        return attrs


# =========================================================================
# PROVIDER
# =========================================================================

class ProviderSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de Provider com resumo operacional/econômico.

    Campos:
        connections_count, contracts_count
        active_contracts_count, active_pricings_count
        cost_30d, requests_30d, error_rate_30d

    NÃO expõe `usage_30d` — métricas heterogêneas não formam
    um "uso total" semanticamente válido.
    """

    connections_count = serializers.SerializerMethodField()
    contracts_count = serializers.SerializerMethodField()
    active_contracts_count = serializers.SerializerMethodField()
    active_pricings_count = serializers.SerializerMethodField()
    cost_30d = serializers.SerializerMethodField()
    requests_30d = serializers.SerializerMethodField()
    error_rate_30d = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            'id', 'key', 'name', 'category', 'description',
            'is_active',
            'connections_count', 'contracts_count',
            'active_contracts_count', 'active_pricings_count',
            'cost_30d', 'requests_30d', 'error_rate_30d',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_connections_count(self, obj):
        return obj.connections.count()

    def get_contracts_count(self, obj):
        return obj.contracts.count()

    def get_active_contracts_count(self, obj):
        return obj.contracts.filter(is_active=True).count()

    def get_active_pricings_count(self, obj):
        return obj.pricings.filter(is_active=True).count()

    def _window_start(self):
        return timezone.now() - timedelta(days=30)

    def get_cost_30d(self, obj):
        from apps.console.models import UsageRecord
        start = self._window_start()
        total = (
            UsageRecord.objects
            .filter(provider=obj, occurred_at__gte=start)
            .aggregate(t=Sum('estimated_cost'))['t']
        )
        return str(total or 0)

    def get_requests_30d(self, obj):
        from apps.console.models import ProviderLog
        start = self._window_start()
        return ProviderLog.objects.filter(
            provider=obj, occurred_at__gte=start
        ).count()

    def get_error_rate_30d(self, obj):
        from apps.console.models import ProviderLog
        start = self._window_start()
        qs = ProviderLog.objects.filter(provider=obj, occurred_at__gte=start)
        total = qs.count()
        if total == 0:
            return 0.0
        failed = qs.filter(
            status__in=['failed', 'timeout', 'rate_limited']
        ).count()
        return round(failed / total * 100, 2)


class ProviderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ['name', 'category', 'description', 'is_active']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_('O nome é obrigatório'))
        return value.strip()

    def create(self, validated_data):
        base_key = slugify(validated_data['name']).replace('-', '_')
        base_key = re.sub(r'[^a-z0-9_]', '', base_key) or 'provider'

        key = base_key
        counter = 1
        while Provider.objects.filter(key=key).exists():
            counter += 1
            key = f"{base_key}_{counter}"

        validated_data['key'] = key
        return super().create(validated_data)


class ProviderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ['name', 'category', 'description', 'is_active']