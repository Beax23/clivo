"""
CostService — cálculo determinístico de custo.

Fonte oficial de custo:
    UsageRecord × ProviderPricing → CostService → custo

REGRA ARQUITETURAL:
    CostService não conhece regras de negócio de domínios.
    Ele recebe provider + metric + quantity e devolve um custo.

    CostService é também responsável por agregações de custo
    (por provider, por workspace, total) e pelo resumo econômico
    de um provider.

    MarginService consome CostService para calcular margem.
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from django.db.models import Q, Sum, Count
from django.utils import timezone

from apps.console.models import (
    Provider,
    ProviderContract,
    ProviderPricing,
    UsageMetric,
    UsageRecord,
)


class CostService:
    """Cálculo de custo de uso e agregações."""

    # =====================================================================
    # CÁLCULO PONTUAL
    # =====================================================================

    @staticmethod
    def get_active_pricing(
        provider: Provider,
        metric: UsageMetric,
        contract: Optional[ProviderContract] = None,
        at: Optional[datetime] = None,
    ) -> Optional[ProviderPricing]:
        """
        Retorna o ProviderPricing vigente para (provider, metric) no instante `at`.

        Preferência:
            1. Pricing vinculado ao contrato específico
            2. Pricing genérico do provider (contract=None)
        """
        moment = at or timezone.now()

        qs = (
            ProviderPricing.objects
            .filter(
                provider=provider,
                metric=metric,
                is_active=True,
                starts_at__lte=moment,
            )
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=moment))
        )

        if contract is not None:
            specific = qs.filter(contract=contract).order_by('-starts_at').first()
            if specific:
                return specific

        generic = qs.filter(contract__isnull=True).order_by('-starts_at').first()
        return generic

    @staticmethod
    def calculate_cost(
        pricing: ProviderPricing,
        quantity,
    ) -> Decimal:
        """
        Calcula o custo a partir de um ProviderPricing e uma quantity.

        Regras:
            unit    → max(quantity - included, 0) × unit_price
            minimum → max(billable × unit_price, minimum_charge)
            flat    → minimum_charge (ou 0)
            tiered  → NotImplementedError (não implementado na V1)
        """
        qty = Decimal(str(quantity or 0))
        unit_price = pricing.unit_price or Decimal('0')
        included = pricing.included_quantity or Decimal('0')
        minimum = pricing.minimum_charge

        # Quantidade cobrável = quantity - franquia, nunca negativo
        billable = qty - included
        if billable < 0:
            billable = Decimal('0')

        if pricing.pricing_model == 'tiered':
            raise NotImplementedError(
                'Tiered pricing não implementado na V1. '
                'Cadastre um pricing_model unit/minimum/flat.'
            )

        if pricing.pricing_model == 'flat':
            cost = minimum if minimum is not None else Decimal('0')

        elif pricing.pricing_model == 'minimum':
            calculated = billable * unit_price
            cost = max(calculated, minimum) if minimum is not None else calculated

        elif pricing.pricing_model == 'unit':
            cost = billable * unit_price

        else:
            cost = billable * unit_price

        return cost.quantize(Decimal('0.00000001'))

    @staticmethod
    def calculate_for_usage(
        provider: Provider,
        metric: UsageMetric,
        quantity,
        contract: Optional[ProviderContract] = None,
        at: Optional[datetime] = None,
    ) -> tuple:
        """
        Conveniência: encontra pricing vigente e calcula custo.

        Retorna: (cost, currency, pricing_used)
        """
        pricing = CostService.get_active_pricing(
            provider=provider,
            metric=metric,
            contract=contract,
            at=at,
        )
        if pricing is None:
            return Decimal('0'), 'USD', None

        cost = CostService.calculate_cost(pricing, quantity)
        return cost, pricing.currency, pricing

    # =====================================================================
    # AGREGAÇÕES
    # =====================================================================

    @staticmethod
    def get_cost_for_period(
        period_start: datetime,
        period_end: Optional[datetime] = None,
        workspace_id: Optional[str] = None,
    ) -> Decimal:
        """Soma de custo estimado em UsageRecord no período."""
        end = period_end or timezone.now()

        qs = UsageRecord.objects.filter(
            occurred_at__gte=period_start,
            occurred_at__lt=end,
        )
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)

        total = qs.aggregate(total=Sum('estimated_cost'))['total']
        return total or Decimal('0')

    @staticmethod
    def get_provider_cost_breakdown(
        period_start: datetime,
        period_end: Optional[datetime] = None,
    ) -> List[Dict]:
        """Custo agrupado por provider no período."""
        end = period_end or timezone.now()

        rows = (
            UsageRecord.objects
            .filter(occurred_at__gte=period_start, occurred_at__lt=end)
            .values('provider__id', 'provider__name', 'provider__key', 'currency')
            .annotate(total=Sum('estimated_cost'), count=Count('id'))
            .order_by('-total')
        )

        return [
            {
                'provider_id': str(r['provider__id']),
                'provider_name': r['provider__name'],
                'provider_key': r['provider__key'],
                'currency': r['currency'],
                'total_cost': str(r['total'] or Decimal('0')),
                'record_count': r['count'],
            }
            for r in rows
        ]

    @staticmethod
    def get_workspace_cost_breakdown(
        period_start: datetime,
        period_end: Optional[datetime] = None,
    ) -> List[Dict]:
        """Custo agrupado por workspace no período."""
        end = period_end or timezone.now()

        rows = (
            UsageRecord.objects
            .filter(
                occurred_at__gte=period_start,
                occurred_at__lt=end,
                workspace_id__isnull=False,
            )
            .values('workspace_id', 'currency')
            .annotate(total=Sum('estimated_cost'), count=Count('id'))
            .order_by('-total')
        )

        return [
            {
                'workspace_id': str(r['workspace_id']),
                'currency': r['currency'],
                'total_cost': str(r['total'] or Decimal('0')),
                'record_count': r['count'],
            }
            for r in rows
        ]

    @staticmethod
    def get_provider_economics(
        provider: Provider,
        period_days: int = 30,
    ) -> Dict:
        """
        Resumo econômico de um provider num período.

        Retorna custo, requests e taxa de erro.
        NÃO retorna avg_cost_per_request — não há relação 1:1 garantida
        entre UsageRecord e ProviderLog.

        Fonte:
            - Custo: UsageRecord
            - Requests / erros: ProviderLog
        """
        from apps.console.models import ProviderLog

        now = timezone.now()
        start = now - timedelta(days=period_days)

        # Custo via UsageRecord
        usage_qs = UsageRecord.objects.filter(
            provider=provider,
            occurred_at__gte=start,
            occurred_at__lt=now,
        )
        total_cost = usage_qs.aggregate(t=Sum('estimated_cost'))['t'] or Decimal('0')
        usage_records_count = usage_qs.count()

        # Requests / erros via ProviderLog
        logs_qs = ProviderLog.objects.filter(
            provider=provider,
            occurred_at__gte=start,
            occurred_at__lt=now,
        )
        total_requests = logs_qs.count()
        failed_requests = logs_qs.filter(
            status__in=['failed', 'timeout', 'rate_limited']
        ).count()
        success_rate = (
            (total_requests - failed_requests) / total_requests * 100
            if total_requests else 0
        )
        error_rate = (
            failed_requests / total_requests * 100
            if total_requests else 0
        )

        # Contrato ativo e pricing ativo
        active_contract = (
            provider.contracts
            .filter(is_active=True)
            .order_by('-started_at')
            .first()
        )
        active_pricings_count = provider.pricings.filter(is_active=True).count()

        return {
            'period_days': period_days,
            'usage_records_count': usage_records_count,
            'total_cost': str(total_cost.quantize(Decimal('0.01'))),
            'total_requests': total_requests,
            'failed_requests': failed_requests,
            'success_rate_pct': round(success_rate, 2),
            'error_rate_pct': round(error_rate, 2),
            'active_contract': {
                'id': str(active_contract.id) if active_contract else None,
                'name': active_contract.name if active_contract else None,
                'billing_period': active_contract.billing_period if active_contract else None,
                'currency': active_contract.currency if active_contract else None,
                'started_at': active_contract.started_at.isoformat() if active_contract else None,
            } if active_contract else None,
            'active_pricings_count': active_pricings_count,
        }