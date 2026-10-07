"""
Service para Plan, PlanFeature e PlanFeatureLimit.

Plan não conhece Provider.
Plan → PlanFeature → PlanFeatureLimit → UsageMetric.
"""

from typing import Optional, List, Dict

from django.db import transaction

from apps.console.models import (
    Plan,
    PlanFeature,
    PlanFeatureLimit,
    Feature,
    UsageMetric,
)
from apps.console.exceptions.console_exceptions import (
    UsageMetricNotFoundError,
)


class PlanService:
    """Gerenciamento de planos, features e limites."""

    @staticmethod
    def get_by_key(key: str) -> Optional[Plan]:
        try:
            return Plan.objects.get(key=key)
        except Plan.DoesNotExist:
            return None

    @staticmethod
    def list_active() -> List[Plan]:
        return list(Plan.objects.filter(is_active=True))

    @staticmethod
    def list_public() -> List[Plan]:
        return list(
            Plan.objects.filter(is_active=True, is_public=True)
        )

    # ------------------------------------------------------------------
    # PLAN FEATURE
    # ------------------------------------------------------------------

    @staticmethod
    def add_feature(plan: Plan, feature: Feature, created_by=None) -> PlanFeature:
        """Associa uma Feature a um Plan (idempotente)."""
        pf, _ = PlanFeature.objects.get_or_create(
            plan=plan,
            feature=feature,
            defaults={'created_by': created_by},
        )
        return pf

    @staticmethod
    def remove_feature(plan: Plan, feature: Feature) -> None:
        PlanFeature.objects.filter(plan=plan, feature=feature).delete()

    @staticmethod
    def get_plan_features(plan: Plan) -> List[PlanFeature]:
        return list(
            PlanFeature.objects.filter(plan=plan)
            .select_related('feature')
            .order_by('feature__name')
        )

    # ------------------------------------------------------------------
    # PLAN FEATURE LIMIT
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def set_limit(
        plan_feature: PlanFeature,
        metric_key: str,
        limit_value,
        period: str = 'monthly',
        behavior: str = 'hard_limit',
    ) -> PlanFeatureLimit:
        """
        Define/atualiza um limite de métrica dentro de uma PlanFeature.

        Se `limit_value` for None, significa ilimitado.
        """
        try:
            metric = UsageMetric.objects.get(key=metric_key)
        except UsageMetric.DoesNotExist:
            raise UsageMetricNotFoundError(
                f'Métrica "{metric_key}" não encontrada'
            )

        limit, _ = PlanFeatureLimit.objects.update_or_create(
            plan_feature=plan_feature,
            metric=metric,
            defaults={
                'limit_value': limit_value,
                'period': period,
                'behavior': behavior,
            },
        )
        return limit

    @staticmethod
    def get_limits(plan_feature: PlanFeature) -> List[PlanFeatureLimit]:
        return list(
            PlanFeatureLimit.objects.filter(plan_feature=plan_feature)
            .select_related('metric')
            .order_by('metric__key')
        )

    @staticmethod
    def get_limit_map(plan_feature: PlanFeature) -> Dict[str, PlanFeatureLimit]:
        """Retorna mapa {metric_key: limit} para uma PlanFeature."""
        return {
            lim.metric.key: lim
            for lim in PlanService.get_limits(plan_feature)
        }

    @staticmethod
    @transaction.atomic
    def replace_limits(
        plan_feature: PlanFeature,
        limits_data: List[Dict],
    ) -> List[PlanFeatureLimit]:
        """
        Substitui TODOS os limites de uma PlanFeature em lote.

        `limits_data` é uma lista de dicts validados:
            [{'metric_key': ..., 'limit_value': ..., 'period': ..., 'behavior': ...}]
        """
        plan_feature.limits.all().delete()

        created = []
        for data in limits_data:
            created.append(
                PlanService.set_limit(
                    plan_feature=plan_feature,
                    metric_key=data['metric_key'],
                    limit_value=data.get('limit_value'),
                    period=data.get('period', 'monthly'),
                    behavior=data.get('behavior', 'hard_limit'),
                )
            )
        return created