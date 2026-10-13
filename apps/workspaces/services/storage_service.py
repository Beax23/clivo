"""
WorkspaceStorageService — quota e consumo de armazenamento do Workspace.

Este serviço é a camada de apresentação do Workspace sobre o
`QuotaService` do Console. Ele NÃO recalcula quota nem consumo.

Responsabilidades:
    - Delegar cota e consumo ao QuotaService (Console).
    - Adicionar dados específicos do Workspace (id, nome).
    - Preservar o contrato do endpoint administrativo do Console,
      para que o frontend da Mesa e o Console UI compartilhem o
      mesmo formato de resposta.

Regra arquitetural:
    Console governa. Workspace consome.
    Este serviço consome, não governa.

NOTA SOBRE `unconfigured_reason`:
    O `QuotaService` usa `active_subscription` para decidir se há cota.
    Um workspace com subscription INATIVA retorna cota `None` — o que é
    correto. Mas para o frontend explicar POR QUE a cota está ausente,
    precisamos distinguir 4 casos:

        - sem nenhuma subscription           → 'workspace sem plano ativo'
        - subscription existe mas inativa    → 'assinatura inativa'
        - subscription ativa mas plano inativo → 'plano inativo'
        - plano ativo mas sem limite          → 'plano sem limite configurado'

    Por isso o `_unconfigured_reason` olha `subscriptions` (todas),
    não só a ativa — é a única forma de distinguir os casos.
"""

import logging
from typing import Dict, Optional

from apps.console.exceptions import AmbiguousQuotaConfigurationError
from apps.console.services.quota_service import QuotaService

logger = logging.getLogger('workspaces')


# Marcador usado pelo QuotaService para sinalizar ambiguidade.
_AMBIGUOUS_SENTINEL = '__ambiguous__'


class WorkspaceStorageService:

    # ==================================================================
    # RESULTADO COMPLETO
    # ==================================================================

    @staticmethod
    def get_storage_state(workspace) -> Dict:
        """
        Retorna o estado completo de armazenamento do workspace.

        Mesmo formato do endpoint administrativo do Console:

            {
                'workspace_id': str,
                'workspace_name': str,
                'plan_key': str | None,
                'plan_name': str | None,
                'status': str,
                'allowed': bool,
                'quota_bytes': int | None,
                'used_bytes': int,
                'remaining_bytes': int | None,
                'percent': float,
                'behavior': str | None,
                'period': str | None,
                'feature_key': str | None,
                'unconfigured_reason': str | None,
            }

        Nunca levanta — se houver ambiguidade, devolve um estado
        explícito em vez de quebrar o frontend.
        """
        result = QuotaService.check(workspace)

        if result.feature_key == _AMBIGUOUS_SENTINEL:
            detail = WorkspaceStorageService._ambiguous_detail(workspace)

            logger.warning(
                'Quota ambígua ao consultar workspace=%s: %s',
                workspace.pk, detail,
            )
            return {
                'workspace_id': str(workspace.pk),
                'workspace_name': workspace.name,
                'plan_key': None,
                'plan_name': None,
                'status': 'unconfigured',
                'allowed': True,
                'quota_bytes': None,
                'used_bytes': result.used_bytes,
                'remaining_bytes': None,
                'percent': 0.0,
                'behavior': None,
                'period': None,
                'feature_key': _AMBIGUOUS_SENTINEL,
                'unconfigured_reason': (
                    'Configuração de quota ambígua. '
                    'Contate o administrador do Clivo.'
                ),
            }

        # Plano da assinatura ATIVA. Se não houver assinatura ativa,
        # `active_subscription` devolve None e o `plan` fica None.
        active_sub = workspace.active_subscription
        plan = active_sub.plan if active_sub else None

        return {
            'workspace_id': str(workspace.pk),
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
            'feature_key': (
                None if result.feature_key == _AMBIGUOUS_SENTINEL
                else result.feature_key
            ),
            'unconfigured_reason': WorkspaceStorageService._unconfigured_reason(
                workspace, result.status,
            ),
        }

    # ==================================================================
    # CONSULTAS SIMPLES (atalhos)
    # ==================================================================

    @staticmethod
    def get_usage_bytes(workspace) -> int:
        """
        Atalho para `QuotaService.get_usage_bytes(workspace)`.

        Sempre retorna int >= 0.
        """
        return QuotaService.get_usage_bytes(workspace)

    @staticmethod
    def get_quota_bytes(workspace) -> Optional[int]:
        """
        Atalho para `QuotaService.get_quota_info(workspace).limit_value`.

        Retorna None se o workspace não tem plano ativo, o plano não
        tem limite, ou o limite é ilimitado.

        Propaga `AmbiguousQuotaConfigurationError` quando a
        configuração for ambígua — o chamador decide o que fazer.
        """
        info = QuotaService.get_quota_info(workspace)
        if info is None:
            return None
        return info.limit_value

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _ambiguous_detail(workspace) -> str:
        """
        Recupera a mensagem rica de ambiguidade do QuotaService.

        Chamado SÓ quando `check()` já sinalizou `__ambiguous__`.
        """
        try:
            QuotaService.get_quota_info(workspace)
        except AmbiguousQuotaConfigurationError as exc:
            return str(exc)

        return (
            'Configuração de quota ambígua: mais de uma feature do '
            "plano define o limite de 'storage.bytes'."
        )

    @staticmethod
    def _unconfigured_reason(workspace, status_value) -> Optional[str]:
        """
        Explica por que o workspace está 'unconfigured'.

        Olha TODAS as subscriptions (não só a ativa), porque precisa
        distinguir quatro casos diferentes:

            - sem subscription nenhuma        → 'workspace sem plano ativo'
            - subscription existe mas inativa → 'assinatura inativa'
            - subscription ativa, plano inativo → 'plano inativo'
            - plano ativo, sem limite         → 'plano sem limite configurado'

        A ordem importa: a primeira condição que casar decide o motivo.

        Usa `subscriptions` (relacionamento reverso, plural) porque é
        a única forma de detectar assinatura INATIVA — `active_subscription`
        devolveria None nesse caso, e não saberíamos distinguir de
        "workspace sem nenhuma assinatura".
        """
        if status_value != 'unconfigured':
            return None

        # Pega a assinatura mais recente, ativa ou não.
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