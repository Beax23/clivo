"""
WorkspaceIntegrationService — API interna para apps consumidores.

NÃO é uma API REST. É uma API Python que os apps do Clivo usam
diretamente (ex: `from apps.integrations.services.access import
WorkspaceIntegrationService`).

SEM NOÇÃO DE consumer_app:
    Não há registro de "qual app pode usar qual recurso".
    Se o workspace tem uma integração ativa, qualquer app com acesso
    ao workspace pode usá-la.

SELEÇÃO DE CONTA:
    Regra determinística, sem `.first()` arbitrário.

CONCORRÊNCIA:
    A auto-marcação de `is_preferred` acontece dentro de
    `transaction.atomic()` + `select_for_update()`.
"""

import logging

from django.db import IntegrityError, transaction

from apps.integrations.exceptions import (
    AmbiguousConnectionError,
    ConnectionNotFoundError,
    ConnectionNotEstablishedError,
    IntegrationInactiveError,
)
from apps.integrations.models import WorkspaceIntegration
from apps.integrations.providers.registry import ProviderRegistry

logger = logging.getLogger('integrations')


class WorkspaceIntegrationService:
    """
    Resolve a integração ativa do workspace com o provider.
    """

    @staticmethod
    def get_for_workspace(
        *,
        workspace,
        provider_key: str,
        integration_id=None,
    ) -> WorkspaceIntegration:
        """
        Retorna a WorkspaceIntegration ativa do workspace com o provider.

        Regras de seleção (aplicadas nesta ordem):

            1. Se `integration_id` explícito:
               - Valida que pertence ao workspace.
               - Valida que `status='active'`.
               - Retorna.

            2. Se não foi passado `integration_id`:
               2a. Se existe uma conta com `is_preferred=True,
                   status='active'` → retorna.
               2b. Se existe exatamente uma conta ativa → retorna e
                   marca como preferida.
               2c. Se existem múltiplas ativas sem preferida →
                   AmbiguousConnectionError.
               2d. Se não existe nenhuma ativa →
                   ConnectionNotEstablishedError.

        Levanta:
            ConnectionNotFoundError
            IntegrationInactiveError
            ConnectionNotEstablishedError
            AmbiguousConnectionError
        """
        if integration_id is not None:
            return WorkspaceIntegrationService._resolve_explicit(
                workspace=workspace,
                integration_id=integration_id,
            )
        return WorkspaceIntegrationService._resolve_by_preference(
            workspace=workspace,
            provider_key=provider_key,
        )

    @staticmethod
    def _resolve_explicit(
        *,
        workspace,
        integration_id,
    ) -> WorkspaceIntegration:
        try:
            integration = WorkspaceIntegration.objects.get(
                id=integration_id,
                workspace=workspace,
            )
        except (WorkspaceIntegration.DoesNotExist, ValueError):
            raise ConnectionNotFoundError(
                'Integração não encontrada neste workspace.',
                context={
                    'workspace_id': str(workspace.pk),
                    'integration_id': str(integration_id),
                },
            )

        if not integration.is_usable():
            raise IntegrationInactiveError(
                f'Integração está no estado "{integration.status}" '
                f'e não pode ser usada.',
                context={
                    'integration_id': str(integration.pk),
                    'status': integration.status,
                },
            )

        return integration

    @staticmethod
    def _resolve_by_preference(
        *,
        workspace,
        provider_key: str,
    ) -> WorkspaceIntegration:
        with transaction.atomic():
            candidates = list(
                WorkspaceIntegration.objects
                .select_for_update()
                .filter(
                    workspace=workspace,
                    provider__key=provider_key,
                    status=WorkspaceIntegration.STATUS_ACTIVE,
                )
                .order_by('-created_at')
            )

            if not candidates:
                raise ConnectionNotEstablishedError(
                    f'Nenhuma integração ativa do provider '
                    f'"{provider_key}" neste workspace.',
                    context={
                        'workspace_id': str(workspace.pk),
                        'provider_key': provider_key,
                    },
                )

            preferred = [c for c in candidates if c.is_preferred]

            if len(preferred) == 1:
                return preferred[0]

            if len(preferred) > 1:
                logger.warning(
                    'Estado inconsistente: múltiplas integrações '
                    'preferidas para workspace=%s provider=%s',
                    workspace.pk, provider_key,
                )
                raise AmbiguousConnectionError(
                    f'Múltiplas integrações preferidas para '
                    f'"{provider_key}" (estado inconsistente).',
                    context={
                        'workspace_id': str(workspace.pk),
                        'provider_key': provider_key,
                        'count': len(preferred),
                    },
                )

            if len(candidates) == 1:
                integration = candidates[0]
                if not integration.is_preferred:
                    try:
                        integration.is_preferred = True
                        integration.save(
                            update_fields=['is_preferred', 'updated_at'],
                        )
                    except IntegrityError:
                        logger.warning(
                            'Race na marcação de preferida para '
                            'integration=%s. Revalidando estado.',
                            integration.pk,
                        )
                        integration.refresh_from_db()
                        if not integration.is_preferred:
                            raise AmbiguousConnectionError(
                                'Estado inconsistente após race na '
                                'marcação de preferida.',
                                context={
                                    'workspace_id': str(workspace.pk),
                                    'provider_key': provider_key,
                                    'integration_id': str(integration.pk),
                                },
                            )
                return integration

            raise AmbiguousConnectionError(
                f'Múltiplas integrações ativas do provider '
                f'"{provider_key}" sem preferida. '
                f'Informe `integration_id` explicitamente.',
                context={
                    'workspace_id': str(workspace.pk),
                    'provider_key': provider_key,
                    'count': len(candidates),
                },
            )

    @staticmethod
    def get_connector(provider_key: str):
        """Atalho para o ProviderRegistry."""
        return ProviderRegistry.get(provider_key)

    @staticmethod
    def list_active_for_workspace(*, workspace, provider_key: str = None):
        """
        Lista integrações ativas do workspace.

        Se `provider_key` é passado, filtra por provider.
        """
        qs = (
            WorkspaceIntegration.objects
            .filter(
                workspace=workspace,
                status=WorkspaceIntegration.STATUS_ACTIVE,
            )
            .select_related('provider')
            .order_by('-is_preferred', '-created_at')
        )
        if provider_key is not None:
            qs = qs.filter(provider__key=provider_key)
        return list(qs)