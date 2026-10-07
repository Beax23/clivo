"""
MarginService — cálculo agregado de margem por plano.

IMPORTANTE:
    Não temos Subscription/Billing na V1.
    Portanto, a "receita" aqui é PREÇO DE TABELA × workspaces hipotéticos.
    Todos os campos retornados usam o prefixo `estimated_`.

REGRA ARQUITETURAL:
    MarginService consome CostService. Não duplica agregações.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Dict

from django.utils import timezone

from apps.console.models import (
    Plan,
    UsageRecord,
)
from apps.console.services.cost_service import CostService


class MarginService:
    """Cálculo agregado de margem por plano (estimativa)."""

    @staticmethod
    def estimate_plan_margin(
        plan: Plan,
        period_days: int = 30,
        workspaces_count: int = 1,
    ) -> Dict:
        """
        Estimativa de margem por plano.

        Modelo:
            estimated_revenue = plan.price × workspaces_count
            estimated_cost    = custo médio por workspace × workspaces_count

        Custo médio por workspace é estimado a partir dos UsageRecord
        dos últimos `period_days` dias.
        """
        period_start = timezone.now() - timedelta(days=period_days)
        total_cost = CostService.get_cost_for_period(period_start)

        distinct_ws = (
            UsageRecord.objects
            .filter(occurred_at__gte=period_start, workspace_id__isnull=False)
            .values('workspace_id')
            .distinct()
            .count()
        ) or 1

        avg_cost_per_ws = (total_cost / Decimal(distinct_ws)).quantize(Decimal('0.01'))

        estimated_revenue = Decimal(plan.price) * Decimal(workspaces_count)
        estimated_cost = avg_cost_per_ws * Decimal(workspaces_count)

        estimated_margin = estimated_revenue - estimated_cost
        estimated_margin_pct = (
            (estimated_margin / estimated_revenue * 100)
            if estimated_revenue > 0 else Decimal('0')
        )

        return {
            'plan_id': str(plan.id),
            'plan_key': plan.key,
            'plan_name': plan.name,
            'plan_price': str(plan.price),
            'currency': plan.currency,
            'period_days': period_days,
            'workspaces_count': workspaces_count,
            'estimated_revenue': str(estimated_revenue),
            'estimated_cost': str(estimated_cost),
            'estimated_margin': str(estimated_margin),
            'estimated_margin_pct': str(estimated_margin_pct.quantize(Decimal('0.1'))),
            'avg_cost_per_workspace': str(avg_cost_per_ws),
            'distinct_workspaces_in_sample': distinct_ws,
        }