"""
StorageBudgetService — leitura e mutação do orçamento operacional.

REGRA ARQUITETURAL
------------------
Só este service toca no `StorageBudget`. O modelo é puro estado;
toda regra de negócio (validação contra comprometido, transação,
histórico) vive aqui.

CÁLCULO DE `committed_bytes`
----------------------------
`committed_bytes` é a soma das quotas prometidas pelos planos dos
workspaces ATIVOS com assinatura ATIVA. Não é uma soma simplificada.

Para cada plano ativo que tenha pelo menos um workspace ativo com
assinatura ativa:

    - Conta quantos workspaces ativos usam o plano — via filtro que
      exige `subscriptions__is_active=True` E
      `subscriptions__plan__is_active=True`. Sem isso, um workspace
      com histórico de assinatura inativa contaria dupla.
    - Procura `PlanFeatureLimit` de `storage.bytes` no plano.
    - Se não existir → quota do plano é 0 (não compromete).
    - Se `limit_value` for NULL → ERROR (ilimitado bloqueia estrito).
    - Se houver mais de um `PlanFeatureLimit` para `storage.bytes`
      → ERROR (configuração ambígua).
    - Caso contrário → quota × workspaces do plano.

`committed_bytes` é a soma dos `quota × workspaces` de todos os
planos elegíveis.

O BREAKDOWN
-----------
O breakdown por plano é a MESMA conta, mas sem agregar. Cada linha
mostra quota, contagem de workspaces, e o compromisso do plano. A
soma do breakdown É `committed_bytes` — não há duplicação.

ATUALIZAÇÃO DO ORÇAMENTO
------------------------
Toda mutação passa por `update_budget`, que:

    - Abre `transaction.atomic`.
    - Trava a linha do orçamento com `select_for_update`.
    - Recalcula `committed_bytes` DENTRO da transação.
    - Valida que o novo total não fica abaixo do comprometido.
    - Grava o novo estado.
    - Grava `StorageBudgetChange` com valores anteriores e novos.

O `select_for_update` serializa mutações concorrentes.
"""

import logging
from typing import Optional, List, Dict, Any

from django.db import transaction

from apps.console.models import (
    Plan,
    PlanFeatureLimit,
    StorageBudget,
    StorageBudgetChange,
)
from apps.console.exceptions import (
    StorageBudgetNotFoundError,
    StorageBudgetNotConfiguredError,
    StorageBudgetBelowCommittedError,
    StorageBudgetUnlimitedQuotaError,
    StorageBudgetAmbiguousQuotaError,
)

logger = logging.getLogger('console')


# Chave canônica da métrica de armazenamento.
_STORAGE_METRIC_KEY = 'storage.bytes'


class StorageBudgetService:

    # ==================================================================
    # LEITURA
    # ==================================================================

    @staticmethod
    def get_budget() -> Optional[StorageBudget]:
        """
        Retorna o orçamento atual, ou None se não configurado.

        Não levanta. O chamador decide se `None` é erro.
        """
        return StorageBudget.objects.first()

    @staticmethod
    def get_budget_or_raise() -> StorageBudget:
        """Igual ao anterior, mas levanta se não existir."""
        budget = StorageBudget.objects.first()
        if budget is None:
            raise StorageBudgetNotFoundError(
                'Orçamento não configurado. Rode '
                '`python manage.py seed_storage_budget`.'
            )
        return budget

    @staticmethod
    def get_budget_state() -> Dict:
        """
        Retorna o estado completo do orçamento com derivados calculados.

        Levanta `StorageBudgetNotConfiguredError` se ainda não existe.
        Propaga `StorageBudgetUnlimitedQuotaError` e
        `StorageBudgetAmbiguousQuotaError` se o cálculo de comprometido
        não puder ser feito.
        """
        budget = StorageBudgetService.get_budget()
        if budget is None:
            raise StorageBudgetNotConfiguredError(
                'Orçamento não configurado. Rode '
                '`python manage.py seed_storage_budget` ou configure '
                'via PATCH no Console.'
            )

        committed = StorageBudgetService.calculate_committed_bytes()

        allocatable = budget.allocatable_bytes
        available = max(0, allocatable - committed)

        overallocated = committed > allocatable

        return {
            'budget': budget,
            'total_budget_bytes': budget.total_budget_bytes,
            'reserve_percent': budget.reserve_percent,
            'allocatable_bytes': allocatable,
            'allocation_policy': budget.allocation_policy,
            'committed_bytes': committed,
            'available_bytes': available,
            'overallocated': overallocated,
            'updated_at': budget.updated_at,
        }

    # ==================================================================
    # BREAKDOWN — cálculo interno reutilizável
    # ==================================================================

    @staticmethod
    def _eligible_plans() -> List[Plan]:
        """
        Retorna os planos que têm pelo menos um workspace ativo com
        assinatura ativa, e cujo plano em si está ativo.

        Esta é a ÚNICA fonte de verdade sobre quais planos entram no
        cálculo. Tanto `_calculate_breakdown` quanto
        `calculate_committed_bytes` usam este conjunto.
        """
        from apps.workspaces.models import Workspace

        plan_ids = list(
            Workspace.objects
            .filter(
                is_active=True,
                subscriptions__is_active=True,
                subscriptions__plan__is_active=True,
            )
            .values_list('subscriptions__plan_id', flat=True)
            .distinct()
        )

        if not plan_ids:
            return []

        # Recupera os Plan de uma vez, preservando ordem por key.
        return list(
            Plan.objects
            .filter(id__in=plan_ids)
            .order_by('key')
        )

    @staticmethod
    def _count_active_workspaces_for_plan(plan: Plan) -> int:
        """
        Conta workspaces ATIVOS com assinatura ATIVA no plano.

        O filtro exige:
            - workspace.is_active=True
            - subscription.is_active=True
            - subscription.plan__is_active=True

        Sem `subscriptions__plan__is_active=True`, um workspace cujo
        plano ficou inativo entre a primeira query e esta seria
        contado — inconsistência.
        """
        from apps.workspaces.models import Workspace

        return (
            Workspace.objects
            .filter(
                is_active=True,
                subscriptions__is_active=True,
                subscriptions__plan__is_active=True,
                subscriptions__plan=plan,
            )
            .distinct()
            .count()
        )

    @staticmethod
    def _calculate_breakdown() -> List[Dict[str, Any]]:
        """
        Calcula o compromisso por plano, sem agregar.

        Retorna uma lista de dicts, um por plano ATIVO que tenha pelo
        menos um workspace ATIVO com assinatura ATIVA. Planos sem
        workspaces elegíveis NÃO aparecem aqui.

        Cada dict:

            {
                'plan_key': str,
                'plan_name': str,
                'quota_bytes': int | None,
                'has_quota': bool,
                'is_unlimited': bool,
                'workspaces_count': int,
                'committed_bytes': int,
            }

        Semântica:
            - `has_quota=False` e `quota_bytes=None` → plano sem
              `PlanFeatureLimit` de `storage.bytes`. Não compromete.
            - `is_unlimited=True` → `limit_value` é NULL. Bloqueia o
              cálculo, com `StorageBudgetUnlimitedQuotaError`.
            - `committed_bytes = quota × workspaces_count`.

        Levanta:
            StorageBudgetUnlimitedQuotaError
                Se qualquer plano elegível tem `limit_value=None`.

            StorageBudgetAmbiguousQuotaError
                Se qualquer plano elegível tem mais de um
                `PlanFeatureLimit` para `storage.bytes`.
        """
        breakdown: List[Dict[str, Any]] = []

        for plan in StorageBudgetService._eligible_plans():
            workspaces_count = (
                StorageBudgetService._count_active_workspaces_for_plan(plan)
            )

            if workspaces_count == 0:
                continue

            # Quota do plano. Pode levantar se ilimitado ou ambíguo.
            quota = StorageBudgetService._plan_storage_quota(plan)

            # Determina `has_quota` e `is_unlimited` lendo direto no
            # banco — não dá para inferir de `quota` porque `quota=0`
            # pode significar tanto "sem limite" quanto "limite zero".
            limits = list(
                PlanFeatureLimit.objects
                .filter(
                    plan_feature__plan=plan,
                    metric__key=_STORAGE_METRIC_KEY,
                    metric__is_active=True,
                )
            )

            if not limits:
                has_quota = False
                is_unlimited = False
                quota_for_row = None
            else:
                has_quota = True
                is_unlimited = limits[0].limit_value is None
                quota_for_row = quota

            committed = quota * workspaces_count

            breakdown.append({
                'plan_key': plan.key,
                'plan_name': plan.name,
                'quota_bytes': quota_for_row,
                'has_quota': has_quota,
                'is_unlimited': is_unlimited,
                'workspaces_count': workspaces_count,
                'committed_bytes': committed,
            })

        return breakdown

    @staticmethod
    def get_breakdown() -> Dict[str, Any]:
        """
        Breakdown por plano com totais agregados.

        Mesma lógica do `calculate_committed_bytes()`, mas expõe cada
        plano individualmente.

        Retorna:

            {
                'plans': [ {...}, {...} ],
                'totals': {
                    'committed_bytes': int,
                    'workspaces_count': int,
                },
                'unconfigured_plans_count': int,
            }

        Onde `unconfigured_plans_count` é o número de planos ativos
        que aparecem no breakdown mas NÃO têm quota definida.

        Levanta o mesmo que `_calculate_breakdown()`.
        """
        plans = StorageBudgetService._calculate_breakdown()

        total_committed = sum(p['committed_bytes'] for p in plans)
        total_workspaces = sum(p['workspaces_count'] for p in plans)
        unconfigured = sum(1 for p in plans if not p['has_quota'])

        return {
            'plans': plans,
            'totals': {
                'committed_bytes': total_committed,
                'workspaces_count': total_workspaces,
            },
            'unconfigured_plans_count': unconfigured,
        }

    @staticmethod
    def calculate_committed_bytes() -> int:
        """
        Soma das quotas prometidas pelos planos dos workspaces ATIVOS
        com assinatura ATIVA.

        Reusa `_calculate_breakdown()` — mesma regra, sem duplicação.
        A soma é a única coisa que este método faz.
        """
        return sum(
            p['committed_bytes']
            for p in StorageBudgetService._calculate_breakdown()
        )

    @staticmethod
    def _plan_storage_quota(plan: Plan) -> int:
        """
        Retorna a quota de 'storage.bytes' do plano em bytes.

        0 se o plano não tem limite configurado.

        Levanta:
            StorageBudgetUnlimitedQuotaError
                Se `limit_value=None`.

            StorageBudgetAmbiguousQuotaError
                Se existirem múltiplos `PlanFeatureLimit` para
                'storage.bytes' no plano.
        """
        limits = list(
            PlanFeatureLimit.objects
            .filter(
                plan_feature__plan=plan,
                metric__key=_STORAGE_METRIC_KEY,
                metric__is_active=True,
            )
        )

        if not limits:
            # Plano sem quota de armazenamento definida. Válido.
            # Não compromete orçamento.
            return 0

        if len(limits) > 1:
            feature_keys = sorted(
                lim.plan_feature.feature.key for lim in limits
            )
            raise StorageBudgetAmbiguousQuotaError(
                f"O plano '{plan.key}' tem {len(limits)} features "
                f"definindo '{_STORAGE_METRIC_KEY}': "
                f"{', '.join(feature_keys)}. "
                f"O cálculo de comprometido é bloqueado até que a "
                f"configuração seja corrigida."
            )

        limit_value = limits[0].limit_value

        if limit_value is None:
            raise StorageBudgetUnlimitedQuotaError(
                f"O plano '{plan.key}' define quota de "
                f"'{_STORAGE_METRIC_KEY}' como ilimitada. A política "
                f"estrita não pode calcular comprometido enquanto "
                f"isso existir."
            )

        return int(limit_value)

    # ==================================================================
    # MUTAÇÃO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def update_budget(
        *,
        total_budget_bytes: Optional[int] = None,
        reserve_percent: Optional[int] = None,
        allocation_policy: Optional[str] = None,
        reason: str = '',
        changed_by=None,
    ) -> StorageBudget:
        """
        Atualiza o orçamento de forma transacional.

        Regras:
            - A linha do orçamento é travada com `select_for_update`.
            - `committed_bytes` é recalculado DENTRO da transação.
            - Se o novo total ficar abaixo do comprometido, bloqueia
              (política estrita).
            - Se `allocation_policy='controlled'`, permite abaixo do
              comprometido (é decisão explícita do operador).
            - Se nada mudou, não grava histórico.
            - Se mudou, grava `StorageBudgetChange`.

        Levanta:
            StorageBudgetNotFoundError
                Se o orçamento ainda não foi criado.

            StorageBudgetBelowCommittedError
                Se a política for estrita e o novo total < comprometido.

            StorageBudgetUnlimitedQuotaError, StorageBudgetAmbiguousQuotaError
                Propagados do cálculo de comprometido.
        """
        try:
            budget = StorageBudget.objects.select_for_update().get(
                singleton_key=StorageBudget.SINGLETON_KEY,
            )
        except StorageBudget.DoesNotExist:
            raise StorageBudgetNotFoundError(
                'Orçamento não configurado. Rode '
                '`python manage.py seed_storage_budget` antes de '
                'atualizar.'
            )

        previous_total = budget.total_budget_bytes
        previous_reserve = budget.reserve_percent
        previous_policy = budget.allocation_policy

        new_total = (
            total_budget_bytes
            if total_budget_bytes is not None
            else previous_total
        )
        new_reserve = (
            reserve_percent
            if reserve_percent is not None
            else previous_reserve
        )
        new_policy = (
            allocation_policy
            if allocation_policy is not None
            else previous_policy
        )

        if new_total < 0:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'total_budget_bytes': 'O orçamento não pode ser negativo.'
            })

        if new_reserve < 0 or new_reserve > 100:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'reserve_percent': 'A reserva deve estar entre 0 e 100.'
            })

        if new_policy not in dict(StorageBudget.POLICY_CHOICES):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'allocation_policy': 'Política inválida.'
            })

        # Validação contra comprometido — só quando a política é estrita.
        # Sob 'controlled', o operador assume o risco.
        if new_policy == StorageBudget.POLICY_STRICT:
            committed = StorageBudgetService.calculate_committed_bytes()

            new_allocatable = (new_total * (100 - new_reserve)) // 100

            if new_allocatable < committed:
                raise StorageBudgetBelowCommittedError(
                    f"O orçamento alocável ({new_allocatable} B) ficaria "
                    f"abaixo do já comprometido ({committed} B). "
                    f"A política estrita impede essa alteração. "
                    f"Aumente o orçamento, reduza a reserva, ou troque "
                    f"a política para 'controlled' explicitamente."
                )

        budget.total_budget_bytes = new_total
        budget.reserve_percent = new_reserve
        budget.allocation_policy = new_policy
        if changed_by is not None and getattr(changed_by, 'is_authenticated', False):
            budget.updated_by = changed_by

        changed = (
            previous_total != new_total
            or previous_reserve != new_reserve
            or previous_policy != new_policy
        )

        if not changed:
            return budget

        budget.save()

        StorageBudgetChange.objects.create(
            budget=budget,
            previous_total_bytes=previous_total,
            new_total_bytes=new_total,
            previous_reserve_percent=previous_reserve,
            new_reserve_percent=new_reserve,
            previous_allocation_policy=previous_policy,
            new_allocation_policy=new_policy,
            reason=reason or '',
            changed_by=(
                changed_by
                if (changed_by and getattr(changed_by, 'is_authenticated', False))
                else None
            ),
        )

        logger.info(
            'StorageBudget atualizado: total %s → %s, reserve %s → %s, '
            'policy %s → %s, by=%s',
            previous_total, new_total,
            previous_reserve, new_reserve,
            previous_policy, new_policy,
            getattr(changed_by, 'email', None) or 'system',
        )

        return budget

    # ==================================================================
    # HISTÓRICO
    # ==================================================================

    @staticmethod
    def list_changes(limit: Optional[int] = None) -> List[StorageBudgetChange]:
        """
        Lista o histórico de alterações, mais recentes primeiro.

        `limit=None` retorna tudo.
        """
        qs = StorageBudgetChange.objects.select_related(
            'changed_by'
        ).order_by('-created_at')

        if limit is not None and limit > 0:
            qs = qs[:limit]

        return list(qs)