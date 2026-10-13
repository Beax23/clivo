"""
QuotaViewSet — consulta administrativa da quota de armazenamento.

Endpoint:
    GET /api/console/quota/workspaces/<workspace_id>/

Só leitura. Requer IsConsoleAdmin.
"""

import logging

from django.core.exceptions import ValidationError
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.console.api.serializers.quota_serializers import QuotaCheckSerializer
from apps.console.exceptions import AmbiguousQuotaConfigurationError
from apps.console.permissions.console_permissions import IsConsoleAdmin
from apps.console.services.quota_service import QuotaService

logger = logging.getLogger('console')


# Sentinela: o QuotaService sinaliza ambiguidade atribuindo este valor
# ao `feature_key` do resultado. O endpoint traduz em HTTP 500.
_AMBIGUOUS_SENTINEL = '__ambiguous__'


class QuotaViewSet(viewsets.ViewSet):
    """
    Consulta administrativa da quota de armazenamento de um workspace.

    O Console VÊ, mas não bloqueia uploads por aqui — o enforcement
    real acontece nos endpoints de upload dos módulos consumidores
    (documents/references) e será implementado em etapa posterior.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]

    # ------------------------------------------------------------------
    # WORKSPACE
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path=r'workspaces/(?P<workspace_id>[^/.]+)',
        url_name='workspace-quota',
    )
    def workspace_quota(self, request, workspace_id=None):
        from apps.workspaces.models import Workspace

        workspace = self._resolve_workspace(Workspace, workspace_id)
        if workspace is None:
            return Response(
                {'error': 'Workspace não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # `check()` nunca levanta. Sinaliza ambiguidade via
        # `feature_key='__ambiguous__'`.
        result = QuotaService.check(workspace)

        if result.feature_key == _AMBIGUOUS_SENTINEL:
            # Reaproveita a mensagem rica do serviço — que cita o plano
            # e as features conflitantes. `get_quota_info()` é seguro
            # de chamar aqui: acabamos de detectar a ambiguidade via
            # `check()`, então sabemos que ele vai levantar.
            detail = self._ambiguous_detail(workspace)

            logger.warning(
                'Quota ambígua ao consultar workspace=%s: %s',
                workspace.pk, detail,
            )
            return Response(
                {
                    'error': detail,
                    'code': 'ambiguous_quota_configuration',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        unconfigured_reason = self._unconfigured_reason(
            workspace, result.status,
        )

        # Plano da assinatura ATIVA. Se não houver assinatura ativa,
        # `active_subscription` devolve None e o `plan` fica None.
        active_sub = workspace.active_subscription
        plan = active_sub.plan if active_sub else None

        payload = {
            'workspace_id': workspace.id,
            'workspace_name': workspace.name,
            'plan_key': plan.key if plan else None,
            'plan_name': plan.name if plan else None,
            'status': result.status,
            'allowed': result.allowed,
            'quota_bytes': result.quota_bytes,
            'used_bytes': result.used_bytes,
            'remaining_bytes': result.remaining_bytes,
            'percent': result.percent,
            'behavior': result.behavior,
            'period': result.period,
            'feature_key': result.feature_key,
            'unconfigured_reason': unconfigured_reason,
        }

        serializer = QuotaCheckSerializer(payload)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_workspace(WorkspaceModel, workspace_id):
        """
        Resolve o workspace por ID, tolerando IDs inválidos.

        `Workspace.objects.filter(id='not-a-uuid')` levanta
        `ValidationError` do Django na construção da query — antes
        de qualquer acesso ao banco. Tratamos explicitamente para
        devolver 404, não 500.

        NÃO usa `select_related('subscription__plan')` porque o
        relacionamento antigo (OneToOne) foi substituído por FK
        com `related_name='subscriptions'`. A property
        `active_subscription` resolve o plano quando necessário.
        """
        if not workspace_id:
            return None
        try:
            return (
                WorkspaceModel.objects
                .filter(id=workspace_id)
                .first()
            )
        except (ValidationError, ValueError):
            return None

    @staticmethod
    def _ambiguous_detail(workspace) -> str:
        """
        Recupera a mensagem detalhada de ambiguidade.

        Chamado SÓ quando `check()` já sinalizou `__ambiguous__`.
        Nesse caso, `get_quota_info()` levanta
        `AmbiguousQuotaConfigurationError` com a mensagem rica.
        Fazemos fallback se, por algum motivo, não levantar.
        """
        try:
            QuotaService.get_quota_info(workspace)
        except AmbiguousQuotaConfigurationError as exc:
            return str(exc)

        # Fallback defensivo — não deve acontecer, mas se acontecer
        # devolvemos uma mensagem genérica em vez de 500 vazio.
        return (
            'Configuração de quota ambígua: mais de uma feature do '
            "plano define o limite de 'storage.bytes'."
        )

    @staticmethod
    def _unconfigured_reason(workspace, status_value) -> str:
        """
        Explica por que o workspace está 'unconfigured'.

        Só retorna string quando `status_value == 'unconfigured'`.
        Nos demais estados retorna None.

        Olha TODAS as subscriptions (não só a ativa) para distinguir:

            - sem subscription nenhuma        → 'workspace sem plano ativo'
            - subscription existe mas inativa → 'assinatura inativa'
            - subscription ativa, plano inativo → 'plano inativo'
            - plano ativo, sem limite         → 'plano sem limite configurado'
        """
        if status_value != 'unconfigured':
            return None

        latest = (
            workspace.subscriptions
            .order_by('-started_at')
            .first()
        )

        if latest is None:
            return 'workspace sem plano ativo'

        if not latest.is_active:
            return 'assinatura inativa'

        if latest.plan is None or not latest.plan.is_active:
            return 'plano inativo'

        return 'plano sem limite configurado para storage.bytes'