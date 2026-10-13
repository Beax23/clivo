"""
Serializers do StorageBudget.

- Leitura: expõe o estado completo com derivados calculados.
- Escrita: só aceita `total_budget_bytes`, `reserve_percent`,
  `allocation_policy` e `reason`.
- Histórico: read-only.
- Breakdown: leitura agregada por plano.
"""

from rest_framework import serializers

from apps.console.models import StorageBudget, StorageBudgetChange


class StorageBudgetSerializer(serializers.Serializer):
    """
    Estado completo do orçamento com derivados.

    Todos os campos são read-only. Este serializer é montado a partir
    do dict devolvido por `StorageBudgetService.get_budget_state()`.
    """

    total_budget_bytes = serializers.IntegerField(read_only=True)
    reserve_percent = serializers.IntegerField(read_only=True)
    allocatable_bytes = serializers.IntegerField(read_only=True)
    allocation_policy = serializers.CharField(read_only=True)

    committed_bytes = serializers.IntegerField(read_only=True)
    available_bytes = serializers.IntegerField(read_only=True)
    overallocated = serializers.BooleanField(read_only=True)

    updated_at = serializers.DateTimeField(read_only=True)


class StorageBudgetUpdateSerializer(serializers.Serializer):
    """
    Body do PATCH em `/api/console/storage/budget/`.

    Todos os campos são opcionais. Só o que for enviado é alterado.
    """

    total_budget_bytes = serializers.IntegerField(
        required=False,
        min_value=0,
    )
    reserve_percent = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=100,
    )
    allocation_policy = serializers.ChoiceField(
        choices=[c[0] for c in StorageBudget.POLICY_CHOICES],
        required=False,
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )

    def validate(self, attrs):
        # Se nenhum campo de configuração foi enviado, rejeita.
        # PATCH vazio é ruído.
        configurable = {
            'total_budget_bytes',
            'reserve_percent',
            'allocation_policy',
        }
        if not (configurable & set(attrs.keys())):
            raise serializers.ValidationError(
                'Nenhum campo para alterar. Envie pelo menos um de: '
                'total_budget_bytes, reserve_percent, allocation_policy.'
            )
        return attrs


class StorageBudgetChangeSerializer(serializers.ModelSerializer):
    """Serializer read-only do histórico de alterações."""

    changed_by_email = serializers.EmailField(
        source='changed_by.email',
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = StorageBudgetChange
        fields = [
            'id',
            'previous_total_bytes',
            'new_total_bytes',
            'previous_reserve_percent',
            'new_reserve_percent',
            'previous_allocation_policy',
            'new_allocation_policy',
            'reason',
            'changed_by',
            'changed_by_email',
            'created_at',
        ]
        read_only_fields = fields


# =========================================================================
# BREAKDOWN
# =========================================================================

class StorageBudgetPlanBreakdownRowSerializer(serializers.Serializer):
    """
    Linha do breakdown: um plano.

    `quota_bytes = null` quando o plano não tem `PlanFeatureLimit`
    de `storage.bytes`. Não confundir com quota zerada — são estados
    distintos, sinalizados por `has_quota`.
    """

    plan_key = serializers.CharField(read_only=True)
    plan_name = serializers.CharField(read_only=True)

    quota_bytes = serializers.IntegerField(read_only=True, allow_null=True)
    has_quota = serializers.BooleanField(read_only=True)
    is_unlimited = serializers.BooleanField(read_only=True)

    workspaces_count = serializers.IntegerField(read_only=True)
    committed_bytes = serializers.IntegerField(read_only=True)


class StorageBudgetBreakdownTotalsSerializer(serializers.Serializer):
    """Totais agregados do breakdown."""

    committed_bytes = serializers.IntegerField(read_only=True)
    workspaces_count = serializers.IntegerField(read_only=True)


class StorageBudgetBreakdownSerializer(serializers.Serializer):
    """
    Envelope do endpoint `/api/console/storage/budget/breakdown/`.

    Estrutura:

        {
            "plans": [ {...}, {...} ],
            "totals": {
                "committed_bytes": int,
                "workspaces_count": int,
            },
            "unconfigured_plans_count": int,
        }

    `unconfigured_plans_count` conta planos que aparecem no breakdown
    mas NÃO têm quota definida. Serve para o frontend mostrar
    "N planos pendentes de configuração".
    """

    plans = StorageBudgetPlanBreakdownRowSerializer(many=True, read_only=True)
    totals = StorageBudgetBreakdownTotalsSerializer(read_only=True)
    unconfigured_plans_count = serializers.IntegerField(read_only=True)


# =========================================================================
# PROVIDER CAP
# =========================================================================

class StorageProviderCapSerializer(serializers.Serializer):
    """
    Envelope do endpoint `/api/console/storage/provider-cap/`.

    Reúne em UMA resposta:

        - Identidade do provider (B2, por padrão)
        - Teto operacional do contrato ativo mais recente
        - Uso físico do snapshot 'ok' mais recente
        - Status do último snapshot (independente do uso)

    Semântica dos campos nulos:

        - `contract_id = null` → não há contrato ativo cadastrado
          para o provider.
        - `included_storage_bytes = null` → o contrato existe mas o
          teto NÃO está cadastrado. NUNCA significa "ilimitado".
        - `usage_bytes = null` → não há snapshot 'ok' disponível.
        - `usage_fetched_at = null` → idem.

    `is_configured` é `True` apenas quando há contrato ativo E o
    teto está cadastrado. É um booleano de conveniência; o frontend
    decide o que mostrar.
    """

    provider_key = serializers.CharField(read_only=True)
    provider_name = serializers.CharField(read_only=True)
    provider_is_active = serializers.BooleanField(read_only=True)

    contract_id = serializers.UUIDField(read_only=True, allow_null=True)
    contract_name = serializers.CharField(read_only=True, allow_null=True)
    contract_is_active = serializers.BooleanField(read_only=True)

    included_storage_bytes = serializers.IntegerField(
        read_only=True, allow_null=True,
    )
    is_configured = serializers.BooleanField(read_only=True)

    usage_bytes = serializers.IntegerField(read_only=True, allow_null=True)
    usage_fetched_at = serializers.DateTimeField(read_only=True, allow_null=True)
    usage_is_stale = serializers.BooleanField(read_only=True)

    snapshot_status = serializers.CharField(read_only=True)
    last_snapshot_status = serializers.CharField(read_only=True)
    last_snapshot_error = serializers.CharField(read_only=True, allow_blank=True)
    last_snapshot_fetched_at = serializers.DateTimeField(
        read_only=True, allow_null=True,
    )