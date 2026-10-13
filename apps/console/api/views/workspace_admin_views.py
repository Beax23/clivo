"""
AdminWorkspaceViewSet — o Console visualiza e administra Workspaces.

REGRA:
    O Console observa Workspaces (read-only em identidade) e
    administra a assinatura de plano (write no plano ativo).

    O Console NÃO cria, edita ou exclui Workspaces — isso é da Mesa.

OTIMIZAÇÃO DE PREFETCH:
    A property `Workspace.active_subscription` usa o atributo
    `_active_subscriptions` para evitar query adicional quando ele
    foi populado por um `Prefetch` com `to_attr`. O queryset usa
    `Prefetch` filtrado por `is_active=True` em vez de
    `prefetch_related('subscriptions__plan')`. Isso garante:
        - Apenas assinaturas ativas são carregadas (não todo o histórico).
        - O plano é carregado via `select_related('plan')` no Prefetch.
        - A serialização da listagem não dispara N+1 por Workspace.
"""

from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.workspaces.models import Workspace, WorkspaceSubscription
from apps.workspaces.services.subscription_service import (
    WorkspaceSubscriptionService,
)
from apps.console.api.serializers.workspace_admin_serializers import (
    AdminWorkspaceSerializer,
)
from apps.console.api.serializers.subscription_serializers import (
    AdminWorkspaceSubscriptionSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin
from apps.workspaces.exceptions import SubscriptionError


def _active_subscriptions_prefetch() -> Prefetch:
    """
    Prefetch das assinaturas ATIVAS de cada Workspace.

    `to_attr='_active_subscriptions'` faz o Django guardar o resultado
    em uma lista no objeto Workspace — que a property
    `Workspace.active_subscription` consome sem query adicional.

    Ordenação por `-started_at` é defensiva: se por algum motivo
    houver mais de uma ativa (a constraint impede), a primeira da
    lista é a mais recente.
    """
    return Prefetch(
        'subscriptions',
        queryset=(
            WorkspaceSubscription.objects
            .filter(is_active=True)
            .select_related('plan')
            .order_by('-started_at')
        ),
        to_attr='_active_subscriptions',
    )


class AdminWorkspaceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only para identidade. Uma action de escrita: `change_plan`.

    Permite filtros por `q` (nome/slug), `is_active` e `city`.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = AdminWorkspaceSerializer
    lookup_field = 'id'

    def get_queryset(self):
        qs = (
            Workspace.objects
            .prefetch_related(_active_subscriptions_prefetch())
            .order_by('-created_at')
        )

        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(slug__icontains=q)

        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif is_active in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)

        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(city__icontains=city)

        return qs

    # ==================================================================
    # CHANGE PLAN
    # ==================================================================

    @action(
        detail=True,
        methods=['post'],
        url_path='change-plan',
        url_name='change-plan',
    )
    def change_plan(self, request, id=None):
        """
        Troca o plano ativo do Workspace.

        Body:
            {
                "plan_key": "basic",
                "reason": "manual"   # opcional, default: "manual"
            }

        Retorna a nova assinatura ativa serializada, ou um erro
        4xx com mensagem clara.
        """
        from apps.console.models import Plan

        workspace = self.get_object()

        plan_key = (request.data.get('plan_key') or '').strip()
        reason = (request.data.get('reason') or 'manual').strip()

        if not plan_key:
            return Response(
                {'error': 'O campo "plan_key" é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_plan = Plan.objects.get(key=plan_key)
        except Plan.DoesNotExist:
            return Response(
                {'error': f'Plano "{plan_key}" não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            new_sub = WorkspaceSubscriptionService.change_plan(
                workspace=workspace,
                new_plan=new_plan,
                changed_by=request.user,
                reason=reason,
            )
        except SubscriptionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            AdminWorkspaceSubscriptionSerializer(new_sub).data,
            status=status.HTTP_200_OK,
        )