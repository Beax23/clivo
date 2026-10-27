"""
CostAllocationService — aloca custo real da execução aos insights
que ela produziu.

REGRA DE RATEIO (documentada e testada)
---------------------------------------
Para uma execução (AnalysisRun) que produziu N insights e teve
custo real C (lido de console.UsageRecord via usage_record_id):

    1. N == 0            → nenhuma alocação (não há a quem alocar).
    2. N == 1            → o único insight recebe C inteiro
                           (rule='single_insight').
    3. N > 1             → cada insight recebe C // N, e o ÚLTIMO
                           recebe C - (C // N) * (N - 1), absorvendo
                           o resto. A soma exata é C.
                           (rule='equal_split').

A absorção do resto no último insight é o que garante que a soma
das parcelas bate com o custo real. Sem isso, `C / 3` × 3 gera
diferença de 1 unidade na última casa decimal.

C é determinístico: vem do UsageRecord (custo real). Se C for
desconhecido (usage_record_id ausente ou UsageRecord sem preço),
a alocação é criada com `allocated_cost=None` e `is_estimated=True`
— sinalizando explicitamente "custo desconhecido", nunca zero.

IDEMPOTÊNCIA
------------
`allocate_for_run` pode ser chamado múltiplas vezes sem duplicar
linhas (constraint única em insight + usage_record_id). Re-execuções
com mesmo usage_record_id são no-op.
"""

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction

from apps.intelligence.models import (
    AnalysisRun, InsightItem, InsightCostAllocation,
)

logger = logging.getLogger('intelligence')


class CostAllocationService:

    @staticmethod
    def allocate_for_run(
        run: AnalysisRun,
        ai_response: dict,
    ) -> list:
        """
        Aloca o custo da execução aos insights produzidos.

        Deve ser chamado APÓS a persistência dos insights e APÓS o
        console ter criado o UsageRecord (via call_ai).

        Nunca levanta — falha de alocação não desfaz insights.
        """
        usage_record_id = ai_response.get('usage_record_id')
        if not usage_record_id:
            logger.info(
                'Run %s sem usage_record_id. Custo não alocável.', run.id,
            )
            return []

        total_cost, currency = CostAllocationService._fetch_usage_cost(
            usage_record_id,
        )

        insights = list(
            InsightItem.objects.filter(run=run).order_by('created_at')
        )
        if not insights:
            logger.info('Run %s não produziu insights. Nada a alocar.', run.id)
            return []

        allocations = []
        with transaction.atomic():
            if len(insights) == 1:
                allocations.append(
                    CostAllocationService._create(
                        insight=insights[0],
                        usage_record_id=usage_record_id,
                        cost=total_cost,
                        currency=currency,
                        rule=InsightCostAllocation.RULE_SINGLE_INSIGHT,
                        is_estimated=False if total_cost is not None else True,
                    )
                )
            else:
                n = len(insights)
                shares = []
                if total_cost is None:
                    shares = [None] * n
                else:
                    # Divisão com absorção do resto no último.
                    base = (total_cost / Decimal(n)).quantize(
                        Decimal('0.00000001'),
                    )
                    allocated_sum = base * (n - 1)
                    last = total_cost - allocated_sum
                    shares = [base] * (n - 1) + [last]

                for insight, share in zip(insights, shares):
                    allocations.append(
                        CostAllocationService._create(
                            insight=insight,
                            usage_record_id=usage_record_id,
                            cost=share,
                            currency=currency,
                            rule=InsightCostAllocation.RULE_EQUAL_SPLIT,
                            is_estimated=True,
                        )
                    )
        return [a for a in allocations if a is not None]

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_usage_cost(usage_record_id) -> tuple:
        """
        Lê o custo real do UsageRecord.

        Retorna (Decimal | None, str). None significa desconhecido —
        NÃO significa zero.
        """
        try:
            from apps.console.models import UsageRecord
            record = UsageRecord.objects.filter(id=usage_record_id).only(
                'estimated_cost', 'currency',
            ).first()
        except Exception:
            logger.exception(
                'Falha ao consultar UsageRecord %s', usage_record_id,
            )
            return (None, '')

        if record is None:
            return (None, '')

        cost = record.estimated_cost
        currency = record.currency or ''
        if cost is None:
            return (None, currency)
        return (Decimal(cost), currency)

    @staticmethod
    def _create(
        *,
        insight,
        usage_record_id,
        cost: Optional[Decimal],
        currency: str,
        rule: str,
        is_estimated: bool,
    ):
        """
        Cria a alocação ou devolve a existente (idempotência).
        """
        try:
            obj, created = InsightCostAllocation.objects.get_or_create(
                insight=insight,
                usage_record_id=usage_record_id,
                defaults={
                    'allocated_cost': cost,
                    'currency': currency,
                    'allocation_rule': rule,
                    'is_estimated': is_estimated,
                },
            )
            return obj
        except Exception:
            logger.exception(
                'Falha ao criar alocação para insight=%s usage=%s',
                insight.id, usage_record_id,
            )
            return None