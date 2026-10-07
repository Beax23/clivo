from datetime import timedelta

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from apps.console.models import Plan
from apps.console.services.cost_service import CostService
from apps.console.services.margin_service import MarginService
from apps.console.permissions.console_permissions import IsConsoleAdmin


# Limite máximo de período em dias (evita queries absurdas).
_MAX_DAYS = 365
_DEFAULT_DAYS = 30


class CostViewSet(viewsets.ViewSet):
    """
    Endpoints agregados de custo e margem.

    CostService     → custos (por provider, por workspace, total)
    MarginService   → margem por plano
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]

    def _parse_days(self, request) -> int:
        """
        Lê `days` da query string com validação.

        Regras:
            - default: _DEFAULT_DAYS
            - mínimo: 1
            - máximo: _MAX_DAYS
            - valores inválidos: usa default
        """
        raw = request.query_params.get('days')
        if raw is None:
            return _DEFAULT_DAYS
        try:
            days = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_DAYS
        if days < 1:
            return 1
        if days > _MAX_DAYS:
            return _MAX_DAYS
        return days

    def _get_period(self, request):
        days = self._parse_days(request)
        start = timezone.now() - timedelta(days=days)
        return start, days

    @action(detail=False, methods=['get'], url_path='by-provider')
    def by_provider(self, request):
        start, days = self._get_period(request)
        data = CostService.get_provider_cost_breakdown(start)
        return Response({'period_days': days, 'results': data})

    @action(detail=False, methods=['get'], url_path='by-workspace')
    def by_workspace(self, request):
        start, days = self._get_period(request)
        data = CostService.get_workspace_cost_breakdown(start)
        return Response({'period_days': days, 'results': data})

    @action(detail=False, methods=['get'], url_path='total')
    def total(self, request):
        start, days = self._get_period(request)
        total = CostService.get_cost_for_period(start)
        return Response({
            'period_days': days,
            'total_cost': str(total),
        })

    @action(detail=False, methods=['get'], url_path='plan-margins')
    def plan_margins(self, request):
        period_days = self._parse_days(request)

        raw_ws = request.query_params.get('workspaces', '1')
        try:
            workspaces_count = int(raw_ws)
        except (TypeError, ValueError):
            workspaces_count = 1
        if workspaces_count < 1:
            workspaces_count = 1
        if workspaces_count > 10000:
            workspaces_count = 10000

        plans = Plan.objects.filter(is_active=True).order_by('price')
        results = [
            MarginService.estimate_plan_margin(
                plan=p,
                period_days=period_days,
                workspaces_count=workspaces_count,
            )
            for p in plans
        ]
        return Response({
            'period_days': period_days,
            'workspaces_count': workspaces_count,
            'results': results,
        })

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        start, days = self._get_period(request)
        total = CostService.get_cost_for_period(start)
        by_provider = CostService.get_provider_cost_breakdown(start)
        by_workspace = CostService.get_workspace_cost_breakdown(start)

        return Response({
            'period_days': days,
            'total_cost': str(total),
            'by_provider': by_provider,
            'by_workspace': by_workspace,
        })