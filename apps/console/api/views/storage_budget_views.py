"""
StorageBudgetViewSet — leitura e edição do orçamento operacional.

Endpoints:
    GET   /api/console/storage/budget/
    PATCH /api/console/storage/budget/
    GET   /api/console/storage/budget/history/
    GET   /api/console/storage/budget/breakdown/

Requer `IsConsoleAdmin`.
"""

import logging

from django.core.exceptions import ValidationError
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.console.api.serializers import (
    StorageBudgetSerializer,
    StorageBudgetUpdateSerializer,
    StorageBudgetChangeSerializer,
    StorageBudgetBreakdownSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin
from apps.console.services import StorageBudgetService
from apps.console.exceptions import (
    StorageBudgetError,
    StorageBudgetNotFoundError,
    StorageBudgetNotConfiguredError,
    StorageBudgetBelowCommittedError,
    StorageBudgetUnlimitedQuotaError,
    StorageBudgetAmbiguousQuotaError,
)

logger = logging.getLogger('console')


class StorageBudgetViewSet(viewsets.ViewSet):
    """
    Leitura e edição do orçamento operacional de armazenamento.

    Não há create nem delete. O orçamento é singleton, criado por
    `python manage.py seed_storage_budget` e alterado por PATCH.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]

    # ------------------------------------------------------------------
    # GET /api/console/storage/budget/
    # ------------------------------------------------------------------

    def list(self, request):
        """
        Devolve o estado completo do orçamento.

        Se o orçamento não existir, devolve 404 com mensagem clara.
        Se o cálculo de comprometido não puder ser feito (ilimitado
        ou ambíguo), devolve 409 com a mensagem rica.
        """
        try:
            state = StorageBudgetService.get_budget_state()
        except StorageBudgetNotConfiguredError as e:
            return Response(
                {'error': str(e), 'code': 'not_configured'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except StorageBudgetUnlimitedQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'unlimited_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetAmbiguousQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'ambiguous_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StorageBudgetSerializer(state)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # PATCH /api/console/storage/budget/
    # ------------------------------------------------------------------

    def partial_update(self, request, pk=None):
        """
        Atualiza o orçamento. Body validado por
        `StorageBudgetUpdateSerializer`.
        """
        serializer = StorageBudgetUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            StorageBudgetService.update_budget(
                total_budget_bytes=data.get('total_budget_bytes'),
                reserve_percent=data.get('reserve_percent'),
                allocation_policy=data.get('allocation_policy'),
                reason=data.get('reason', ''),
                changed_by=request.user,
            )
        except StorageBudgetNotFoundError as e:
            return Response(
                {'error': str(e), 'code': 'not_configured'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except StorageBudgetBelowCommittedError as e:
            return Response(
                {'error': str(e), 'code': 'below_committed'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetUnlimitedQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'unlimited_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetAmbiguousQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'ambiguous_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as e:
            return Response(
                {'error': e.message_dict if hasattr(e, 'message_dict') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Recarrega o estado para devolver o resultado.
        try:
            state = StorageBudgetService.get_budget_state()
        except StorageBudgetError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(StorageBudgetSerializer(state).data)

    # ------------------------------------------------------------------
    # GET /api/console/storage/budget/history/
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path='history',
        url_name='budget-history',
    )
    def history(self, request):
        """
        Histórico de alterações do orçamento, mais recentes primeiro.

        Query params:
            limit (opcional, default 50, máx 200)
        """
        try:
            limit = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(200, limit))

        changes = StorageBudgetService.list_changes(limit=limit)
        serializer = StorageBudgetChangeSerializer(changes, many=True)
        return Response({
            'count': len(serializer.data),
            'results': serializer.data,
        })

    # ------------------------------------------------------------------
    # GET /api/console/storage/budget/breakdown/
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path='breakdown',
        url_name='budget-breakdown',
    )
    def breakdown(self, request):
        """
        Breakdown do compromisso por plano.

        Devolve, para cada plano ativo com pelo menos um workspace
        ativo com assinatura ativa:

            - plan_key, plan_name
            - quota_bytes (null se não configurada)
            - has_quota (bool)
            - is_unlimited (bool)
            - workspaces_count
            - committed_bytes

        Mais totais agregados e contagem de planos sem quota.

        Só leitura. Não altera nada.
        """
        try:
            breakdown = StorageBudgetService.get_breakdown()
        except StorageBudgetUnlimitedQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'unlimited_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetAmbiguousQuotaError as e:
            return Response(
                {'error': str(e), 'code': 'ambiguous_quota'},
                status=status.HTTP_409_CONFLICT,
            )
        except StorageBudgetError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StorageBudgetBreakdownSerializer(breakdown)
        return Response(serializer.data)