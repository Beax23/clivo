"""
IntegrationService — ciclo de vida da WorkspaceIntegration.

Este serviço aplica as políticas de negócio que o GoogleConnector
deliberadamente NÃO aplica:

    1. Preservação de refresh_token anterior válido.
    2. Não ativar conexão sem refresh_token utilizável.
    3. Validação de escopos concedidos antes de habilitar operações.
    4. Renovação preguiçosa de access_token (on-demand).
    5. Revogação local + best-effort no provider.
    6. Marcação de estado (expired) quando refresh falha.

Também cuida da cifra dos tokens antes de persistir.

MODELO DE CONCORRÊNCIA (refresh):
    Várias partes do produto podem precisar do access_token válido
    ao mesmo tempo (ex: várias chamadas à API do Drive em paralelo).
    Se cada uma disparasse um refresh, teríamos tempestade de
    requisições ao Google.

    Estratégia: `refresh_credentials` roda dentro de uma transação
    com `select_for_update` na integração. A primeira chamada renova;
    as concorrentes esperam, veem o token novo e saem sem renovar.

    Em SQLite o `select_for_update` não tem efeito — o que é
    aceitável, porque SQLite é usado apenas em dev/test. Em
    PostgreSQL (produção) a serialização é real.

MODELO DE "RAISE OUTSIDE ATOMIC":
    Marcações de estado de erro (`_mark_expired`, `_mark_error`,
    `_record_transient_error`) NÃO podem acontecer dentro do
    `transaction.atomic()` de `refresh_credentials`, porque o
    rollback da exceção desfaria a marcação.

    Por isso, o padrão adotado é:

        1. Capturar a exceção dentro do atomic.
        2. Guardar `pending_state_update` e `pending_exception`.
        3. Sair do atomic (commit acontece).
        4. Marcar o estado FORA do atomic (persiste).
        5. Re-levantar a exceção guardada.

    Isso garante que a integração vai para `expired` mesmo com o
    refresh falhando, sem que o rollback apague essa transição.
"""

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.integrations.encryption.service import EncryptionService
from apps.integrations.exceptions import (
    ConnectionExpiredError,
    ConnectionRevokedError,
    IntegrationInactiveError,
    InsufficientScopesError,
    RefreshTokenInvalidError,
    RefreshTransientError,
    WorkspaceIntegrationError,
)
from apps.integrations.models import (
    IntegrationProvider,
    WorkspaceIntegration,
)
from apps.integrations.providers.registry import ProviderRegistry
from apps.integrations.providers.types import OAuthResult

logger = logging.getLogger('integrations')


# Schema do payload cifrado. Incrementar quando o formato mudar.
PAYLOAD_SCHEMA_VERSION = 1

# Margem de segurança: renovamos o token quando faltar MENOS do que
# este tempo para expirar. Evita a condição de corrida onde o token
# expira entre a checagem e a chamada real à API.
REFRESH_MARGIN_SECONDS = 5 * 60  # 5 minutos


class IntegrationService:
    """
    Gerencia a persistência segura de credenciais OAuth.
    """

    # =====================================================================
    # CRIAÇÃO / ATUALIZAÇÃO A PARTIR DE OAUTH
    # =====================================================================

    @staticmethod
    @transaction.atomic
    def upsert_from_oauth(
        *,
        workspace,
        provider: IntegrationProvider,
        oauth_result: OAuthResult,
        requested_resources: list,
        actor,
    ) -> WorkspaceIntegration:
        """
        Cria ou atualiza uma WorkspaceIntegration a partir de um
        OAuthResult.

        Políticas aplicadas:

            1. Se `oauth_result.refresh_token` é None, preserva o
               refresh_token da integração existente (se houver).

            2. Se, depois da preservação, ainda não há refresh_token
               utilizável, levanta `WorkspaceIntegrationError`.
               A conexão NÃO é ativada.

            3. Valida que os escopos concedidos cobrem os recursos
               solicitados. Se faltar algum, levanta
               `InsufficientScopesError`.

        Levanta:
            WorkspaceIntegrationError — sem refresh_token utilizável.
            InsufficientScopesError — faltam recursos solicitados.
        """

        # -----------------------------------------------------------------
        # 1. Localiza integração existente (mesma conta externa).
        # -----------------------------------------------------------------
        existing = WorkspaceIntegration.objects.filter(
            workspace=workspace,
            provider=provider,
            external_account_id=oauth_result.external_account_id,
        ).first()

        # -----------------------------------------------------------------
        # 2. Preservação de refresh_token.
        # -----------------------------------------------------------------
        refresh_token = oauth_result.refresh_token

        if refresh_token is None and existing is not None:
            refresh_token = IntegrationService._extract_refresh_token(
                existing
            )
            if refresh_token:
                logger.info(
                    'Preservando refresh_token existente para '
                    'workspace=%s provider=%s account=%s',
                    workspace.pk, provider.key,
                    oauth_result.external_account_id,
                )

        # -----------------------------------------------------------------
        # 3. Se ainda não há refresh_token utilizável, NÃO ativa.
        # -----------------------------------------------------------------
        if not refresh_token:
            raise WorkspaceIntegrationError(
                'A conexão não pode ser ativada: o Google não '
                'retornou credencial de longa duração e não há uma '
                'anterior válida. Reconecte e autorize novamente.',
                context={
                    'workspace_id': str(workspace.pk),
                    'provider_key': provider.key,
                    'reason': 'no_refresh_token',
                },
            )

        # -----------------------------------------------------------------
        # 4. Validar escopos concedidos.
        # -----------------------------------------------------------------
        granted_resources = set(
            oauth_result.provider_metadata.get(
                'granted_resources', []
            )
        )
        requested = set(requested_resources)
        missing = requested - granted_resources

        if missing:
            raise InsufficientScopesError(
                'A conexão não pode ser ativada: alguns recursos '
                'solicitados não foram concedidos.',
                context={
                    'workspace_id': str(workspace.pk),
                    'provider_key': provider.key,
                    'missing_resources': sorted(missing),
                },
            )

        # -----------------------------------------------------------------
        # 5. Cifrar payload.
        # -----------------------------------------------------------------
        encrypted = IntegrationService._encrypt_payload(
            access_token=oauth_result.access_token,
            refresh_token=refresh_token,
            expires_at=oauth_result.expires_at,
            scopes=oauth_result.granted_scopes,
        )

        # -----------------------------------------------------------------
        # 6. Persistir (cria ou atualiza).
        # -----------------------------------------------------------------
        now = timezone.now()

        if existing is None:
            integration = WorkspaceIntegration.objects.create(
                workspace=workspace,
                provider=provider,
                external_account_id=oauth_result.external_account_id,
                external_account_email=oauth_result.external_account_email,
                external_account_display_name=(
                    oauth_result.external_account_display_name or ''
                ),
                external_account_avatar_url=(
                    oauth_result.external_account_avatar_url or ''
                ),
                encrypted_payload=encrypted,
                granted_scopes=list(oauth_result.granted_scopes),
                status=WorkspaceIntegration.STATUS_ACTIVE,
                last_refresh_at=now,
                is_preferred=False,  # será resolvido pelo service de acesso
                created_by=actor if actor and actor.is_authenticated else None,
            )
            logger.info(
                'WorkspaceIntegration criada | workspace=%s '
                'provider=%s account=%s',
                workspace.pk, provider.key,
                oauth_result.external_account_id,
            )
        else:
            existing.encrypted_payload = encrypted
            existing.granted_scopes = list(oauth_result.granted_scopes)
            existing.external_account_email = (
                oauth_result.external_account_email
            )
            existing.external_account_display_name = (
                oauth_result.external_account_display_name or ''
            )
            existing.external_account_avatar_url = (
                oauth_result.external_account_avatar_url or ''
            )
            existing.status = WorkspaceIntegration.STATUS_ACTIVE
            existing.last_refresh_at = now
            existing.last_error_at = None
            existing.last_error_code = ''
            existing.save()
            integration = existing
            logger.info(
                'WorkspaceIntegration atualizada | workspace=%s '
                'provider=%s account=%s',
                workspace.pk, provider.key,
                oauth_result.external_account_id,
            )

        return integration

    # =====================================================================
    # RENOVAÇÃO DE TOKENS
    # =====================================================================

    @staticmethod
    def get_valid_access_token(
        integration: WorkspaceIntegration,
    ) -> str:
        """
        Retorna um access_token VÁLIDO, renovando se necessário.

        Esta é a PORTA PADRÃO para qualquer código que precise
        chamar a API externa em nome do usuário.

        Comportamento:
            1. Se a integração não está `active`, levanta
               `IntegrationInactiveError` / `ConnectionExpiredError`
               / `ConnectionRevokedError` (conforme o estado).
            2. Decifra o payload.
            3. Se o access_token expira em mais de REFRESH_MARGIN,
               devolve-o sem tocar no Google.
            4. Se falta menos que a margem (ou já expirou), dispara
               `refresh_credentials` e devolve o novo token.

        Levanta:
            ConnectionRevokedError — integração revogada.
            ConnectionExpiredError — refresh_token inválido (Google
                rejeitou).
            IntegrationInactiveError — estado inesperado.
            RefreshTransientError — falha transitória de rede.
        """
        IntegrationService._assert_usable(integration)

        creds = IntegrationService.get_credentials(integration)

        if not IntegrationService._needs_refresh(creds):
            return creds['access_token']

        # Precisamos renovar. Delegamos para o método que tem lock.
        refreshed = IntegrationService.refresh_credentials(integration)
        return refreshed['access_token']

    @staticmethod
    def refresh_credentials(
        integration: WorkspaceIntegration,
    ) -> dict:
        """
        Força a renovação dos tokens da integração.

        Serializado por `select_for_update`. Se duas chamadas
        concorrentes pedirem refresh, apenas a primeira renova;
        a segunda vê o token novo e não chama o Google.

        Retorna o payload decifrado novo (dict).

        Levanta:
            ConnectionExpiredError — refresh_token inválido. A
                integração é marcada como `expired` ANTES da exceção.
            RefreshTransientError — falha transitória. A integração
                NÃO é marcada como expired — apenas `last_error_*`.
            IntegrationInactiveError — integração não está `active`
                quando o refresh foi pedido.
            ConnectionRevokedError — integração já está revogada.

        NOTA SOBRE TRANSAÇÕES:
            A marcação de estado de erro (`_mark_expired`,
            `_record_transient_error`, `_mark_error`) NÃO pode
            acontecer dentro do `transaction.atomic()`, porque o
            rollback da exceção desfaria a marcação. Por isso,
            usamos um padrão de "raise outside atomic": capturamos
            a exceção dentro do bloco, guardamos para re-levantar
            depois, e marcamos o estado FORA do bloco.
        """
        IntegrationService._assert_usable(integration)

        pending_exception = None
        pending_state_update = None
        result = None

        with transaction.atomic():
            # Relê a integração com lock. Se outra thread renovou
            # enquanto esperávamos, os dados novos estarão aqui.
            locked = (
                WorkspaceIntegration.objects
                .select_for_update()
                .get(pk=integration.pk)
            )

            # Se outra thread renovou, o `last_refresh_at` mudou e
            # o payload é novo. Não renovamos de novo.
            if not IntegrationService._integration_needs_refresh(locked):
                return IntegrationService.get_credentials(locked)

            creds = IntegrationService.get_credentials(locked)
            refresh_token = creds.get('refresh_token')

            if not refresh_token:
                # Estado inconsistente — sem refresh_token, a
                # integração não deveria estar `active`.
                pending_state_update = ('expired', 'missing_refresh_token')
                pending_exception = ConnectionExpiredError(
                    'A integração não possui credencial de longa '
                    'duração. Reconecte.',
                    context={'integration_id': str(locked.pk)},
                )
            else:
                connector = ProviderRegistry.get(locked.provider.key)

                try:
                    oauth_result = connector.refresh(
                        refresh_token=refresh_token,
                    )
                except RefreshTokenInvalidError:
                    # O Google disse: essa credencial não vale mais.
                    pending_state_update = ('expired', 'refresh_invalid')
                    pending_exception = ConnectionExpiredError(
                        'A credencial de longa duração foi revogada ou '
                        'expirou. Reconecte a integração.',
                        context={'integration_id': str(locked.pk)},
                    )
                except RefreshTransientError as exc:
                    # Falha de rede / 5xx. NÃO marca como expired —
                    # pode ser só um blip.
                    pending_state_update = (
                        'transient', 'refresh_transient',
                    )
                    pending_exception = exc
                except Exception as exc:
                    # Qualquer erro inesperado. Marcamos como erro
                    # mas não sabemos se é permanente.
                    logger.exception(
                        'Erro inesperado no refresh (integration=%s)',
                        locked.pk,
                    )
                    pending_state_update = ('error', 'refresh_unknown')
                    pending_exception = WorkspaceIntegrationError(
                        'Erro inesperado ao renovar credenciais.',
                        context={'integration_id': str(locked.pk)},
                    )

                if pending_exception is None:
                    # Persiste os tokens novos.
                    encrypted = IntegrationService._encrypt_payload(
                        access_token=oauth_result.access_token,
                        refresh_token=(
                            oauth_result.refresh_token or refresh_token
                        ),
                        expires_at=oauth_result.expires_at,
                        scopes=(
                            oauth_result.granted_scopes
                            or creds.get('scopes', [])
                        ),
                    )

                    locked.encrypted_payload = encrypted
                    locked.last_refresh_at = timezone.now()
                    locked.last_error_at = None
                    locked.last_error_code = ''
                    locked.save(update_fields=[
                        'encrypted_payload',
                        'last_refresh_at',
                        'last_error_at',
                        'last_error_code',
                        'updated_at',
                    ])

                    logger.info(
                        'Refresh concluído | integration=%s',
                        locked.pk,
                    )

                    # Atualiza o objeto em memória do chamador para
                    # que ele veja o estado novo caso faça mais
                    # alguma coisa com ele.
                    integration.encrypted_payload = encrypted
                    integration.last_refresh_at = locked.last_refresh_at

                    result = IntegrationService.get_credentials(locked)

        # FORA do atomic — o commit já aconteceu. Agora:
        #
        # 1. Se houve erro, marcamos o estado (fora do rollback).
        # 2. Re-levantamos a exceção para o chamador.
        if pending_state_update is not None:
            state, error_code = pending_state_update

            # Relê do banco para pegar o estado atual.
            integration.refresh_from_db()

            if state == 'expired':
                IntegrationService._mark_expired(
                    integration, error_code=error_code,
                )
            elif state == 'transient':
                IntegrationService._record_transient_error(
                    integration, error_code=error_code,
                )
            elif state == 'error':
                IntegrationService._mark_error(
                    integration, error_code=error_code,
                )

            raise pending_exception

        return result

    # =====================================================================
    # REVOGAÇÃO
    # =====================================================================

    @staticmethod
    @transaction.atomic
    def revoke_integration(
        *,
        integration: WorkspaceIntegration,
        actor=None,
        reason: str = 'user_revoked',
    ) -> WorkspaceIntegration:
        """
        Revoga a integração.

        Comportamento:
            1. Chama o connector para revogar os tokens no provider
               (best-effort).
            2. Marca a integração local como `revoked` — SEMPRE,
               mesmo se o provider falhar.
            3. Preserva o histórico (não deleta).

        Idempotente: se a integração já está `revoked`, não faz nada.

        Levanta:
            IntegrationInactiveError — se a integração está em estado
                inconsistente (ex: `error`) e não pode ser revogada.

        NOTA sobre a revogação no provider:
            A ordem é: revogar no provider PRIMEIRO, marcar local
            DEPOIS. Se o provider estiver offline, não travamos o
            usuário — a integração é marcada como `revoked` mesmo
            assim. Um cron futuro pode re-tentar a revogação remota
            (não implementado na V1).
        """
        if integration.status == WorkspaceIntegration.STATUS_REVOKED:
            return integration

        # Lê as credenciais para ter os tokens em mãos.
        try:
            creds = IntegrationService.get_credentials(integration)
        except Exception:
            # Se as credenciais estão corrompidas, não conseguimos
            # revogar no provider. Mas ainda assim marcamos como
            # revogada localmente — o acesso do usuário não depende
            # do provider.
            logger.warning(
                'Falha ao decifrar credenciais ao revogar '
                '(integration=%s). Marcando como revoked localmente.',
                integration.pk,
            )
            creds = {}

        connector = ProviderRegistry.get(integration.provider.key)

        # Best-effort no provider.
        try:
            connector.revoke(
                access_token=creds.get('access_token', ''),
                refresh_token=creds.get('refresh_token'),
            )
        except Exception:
            logger.exception(
                'Falha ao revogar no provider (integration=%s). '
                'Marcando como revoked localmente mesmo assim.',
                integration.pk,
            )

        integration.status = WorkspaceIntegration.STATUS_REVOKED
        integration.is_preferred = False  # revogada nunca é preferida
        integration.last_error_at = timezone.now()
        integration.last_error_code = reason
        integration.save(update_fields=[
            'status',
            'is_preferred',
            'last_error_at',
            'last_error_code',
            'updated_at',
        ])

        logger.info(
            'WorkspaceIntegration revogada | integration=%s '
            'reason=%s actor=%s',
            integration.pk,
            reason,
            getattr(actor, 'email', None) or 'system',
        )

        return integration

    # =====================================================================
    # LEITURA DE CREDENCIAIS
    # =====================================================================

    @staticmethod
    def get_credentials(integration: WorkspaceIntegration) -> dict:
        """
        Decifra e devolve o payload da integração.

        Uso interno. Não expõe em APIs públicas.

        Retorna dict com:
            {
                "access_token": str,
                "refresh_token": str,
                "expires_at": str | None,  # ISO 8601
                "scopes": list[str],
                "schema_version": int,
            }
        """
        raw = EncryptionService.decrypt(integration.encrypted_payload)
        try:
            return json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error(
                'Payload decifrado não é JSON válido (integration=%s)',
                integration.pk,
            )
            raise WorkspaceIntegrationError(
                'Credenciais corrompidas. Reconecte a integração.',
                context={
                    'integration_id': str(integration.pk),
                    'reason': 'invalid_payload',
                },
            ) from exc

    # =====================================================================
    # HELPERS PRIVADOS
    # =====================================================================

    @staticmethod
    def _assert_usable(integration: WorkspaceIntegration) -> None:
        """
        Levanta a exceção apropriada se a integração não pode ser
        usada no estado atual.
        """
        if integration.status == WorkspaceIntegration.STATUS_ACTIVE:
            return

        if integration.status == WorkspaceIntegration.STATUS_REVOKED:
            raise ConnectionRevokedError(
                'A integração foi revogada.',
                context={'integration_id': str(integration.pk)},
            )

        if integration.status == WorkspaceIntegration.STATUS_EXPIRED:
            raise ConnectionExpiredError(
                'A integração expirou. Reconecte.',
                context={'integration_id': str(integration.pk)},
            )

        raise IntegrationInactiveError(
            f'A integração está no estado "{integration.status}".',
            context={
                'integration_id': str(integration.pk),
                'status': integration.status,
            },
        )

    @staticmethod
    def _needs_refresh(creds: dict) -> bool:
        """
        Determina se o access_token do payload precisa ser renovado.

        Regra: renova se falta menos de REFRESH_MARGIN_SECONDS para
        expirar (incluindo já expirado).

        Se `expires_at` for None (não informado), assume que NÃO
        precisa — quem decide é o provider, que vai devolver 401 se
        o token estiver ruim.
        """
        expires_at_str = creds.get('expires_at')
        if not expires_at_str:
            return False

        try:
            expires_at = datetime.fromisoformat(expires_at_str)
        except (TypeError, ValueError):
            # Não conseguimos interpretar — melhor renovar.
            return True

        # Garantir timezone-aware.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt_timezone.utc)

        now = datetime.now(tz=dt_timezone.utc)
        margin = timedelta(seconds=REFRESH_MARGIN_SECONDS)

        return expires_at <= (now + margin)

    @staticmethod
    def _integration_needs_refresh(
        integration: WorkspaceIntegration,
    ) -> bool:
        """
        Versão que opera sobre a integração — lê o payload e chama
        `_needs_refresh`.

        Usada dentro do bloco com lock para decidir se ainda vale
        renovar ou se outra thread já fez.
        """
        try:
            creds = IntegrationService.get_credentials(integration)
        except Exception:
            return True  # se não consegue ler, assume que precisa
        return IntegrationService._needs_refresh(creds)

    @staticmethod
    def _mark_expired(
        integration: WorkspaceIntegration,
        *,
        error_code: str,
    ) -> None:
        """
        Marca a integração como `expired`. Usada quando o refresh
        falha com erro permanente (refresh_token inválido).
        """
        integration.status = WorkspaceIntegration.STATUS_EXPIRED
        integration.is_preferred = False
        integration.last_error_at = timezone.now()
        integration.last_error_code = error_code
        integration.save(update_fields=[
            'status',
            'is_preferred',
            'last_error_at',
            'last_error_code',
            'updated_at',
        ])

    @staticmethod
    def _mark_error(
        integration: WorkspaceIntegration,
        *,
        error_code: str,
    ) -> None:
        """
        Marca a integração como `error`. Usada quando o refresh
        falha mas não sabemos se é permanente.
        """
        integration.status = WorkspaceIntegration.STATUS_ERROR
        integration.last_error_at = timezone.now()
        integration.last_error_code = error_code
        integration.save(update_fields=[
            'status',
            'last_error_at',
            'last_error_code',
            'updated_at',
        ])

    @staticmethod
    def _record_transient_error(
        integration: WorkspaceIntegration,
        *,
        error_code: str,
    ) -> None:
        """
        Registra um erro transitório SEM mudar o status. A
        integração continua `active` — o próximo refresh pode
        funcionar.
        """
        integration.last_error_at = timezone.now()
        integration.last_error_code = error_code
        integration.save(update_fields=[
            'last_error_at',
            'last_error_code',
            'updated_at',
        ])

    @staticmethod
    def _encrypt_payload(
        *,
        access_token: str,
        refresh_token: str,
        expires_at,
        scopes: list,
    ) -> bytes:
        """
        Serializa e cifra o payload de credenciais.
        """
        payload = {
            'schema_version': PAYLOAD_SCHEMA_VERSION,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': (
                expires_at.isoformat() if expires_at else None
            ),
            'scopes': list(scopes or []),
        }
        blob = json.dumps(payload).encode('utf-8')
        return EncryptionService.encrypt(blob)

    @staticmethod
    def _extract_refresh_token(
        integration: WorkspaceIntegration,
    ) -> Optional[str]:
        """
        Tenta decifrar o refresh_token da integração existente.

        Retorna None se:
            - a decifra falhar,
            - o payload não tiver refresh_token,
            - o refresh_token for string vazia.

        Nunca levanta — a ausência de refresh_token é uma condição
        esperada, tratada pelo chamador.
        """
        try:
            data = IntegrationService.get_credentials(integration)
        except Exception as exc:
            logger.warning(
                'Falha ao decifrar integração existente (%s): %s. '
                'Tratando como ausência de refresh_token.',
                integration.pk, type(exc).__name__,
            )
            return None

        rt = data.get('refresh_token')
        return rt if rt else None