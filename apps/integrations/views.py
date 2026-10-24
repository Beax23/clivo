"""
Views HTML do módulo integrations.

Rotas:
    GET /integrations/google/start/?next=<path>
        Autenticado. Inicia o fluxo OAuth para o workspace ativo
        da sessão.

    GET /integrations/google/callback/?code=...&state=...
        Recebe o retorno do Google. Aplica políticas, persiste a
        WorkspaceIntegration e redireciona para o `next_path` do
        state (com sinal `?google_connected=1`), ou para o
        `final_redirect` em caso de falha.

FRONTEIRA:
    Este módulo NÃO importa apps.console.

SOBRE `next`
------------
O parâmetro `next` (query string) é o caminho para onde o usuário
deve voltar DEPOIS de conectar com sucesso. É validado por
`safe_redirect_or_fallback` e persistido no state OAuth.

No retorno, o backend acrescenta `?google_connected=1` na URL.
O frontend usa esse sinal para reabrir a ação que estava em
andamento (por exemplo, o modal de Importar Forms).

SOBRE `login_hint`
------------------
Passamos `request.user.email` como `login_hint` para o Google.
Isso pré-seleciona a conta correta na tela de consentimento,
evitando mostrar outras contas logadas no navegador.

Isso NÃO cria acoplamento com `accounts`: apenas lemos
`request.user.email`, que é campo padrão do Django.
"""

import logging

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View

from apps.integrations.exceptions import (
    IntegrationConfigurationError,
    IntegrationError,
    InsufficientScopesError,
    OAuthExchangeError,
    UnsupportedResourceError,
    WorkspaceIntegrationError,
)
from apps.integrations.models import IntegrationProvider
from apps.integrations.providers.registry import ProviderRegistry
from apps.integrations.services.integration_service import IntegrationService
from apps.integrations.services.oauth_state import OAuthStateService
from apps.integrations.services.redirects import safe_redirect_or_fallback
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('integrations')


# Recursos padrão solicitados ao Google.
# Hoje: Drive (leitura) + Forms (leitura).
DEFAULT_GOOGLE_RESOURCES = [
    'drive.file.read',
    'forms.body.read',
]


# Destino padrão quando não há `next` no query string.
DEFAULT_NEXT_PATH = '/workspaces/entrar/'


# Sinal para o frontend saber que o OAuth foi concluído com sucesso.
GOOGLE_CONNECTED_PARAM = 'google_connected'


# =========================================================================
# HELPERS
# =========================================================================

def _resolve_current_workspace(request):
    """
    Resolve o workspace ativo a partir da sessão.
    Retorna None se não houver.
    """
    ws_id = request.session.get('current_workspace_id')
    if not ws_id:
        return None
    return WorkspaceQueries.get_for_user(ws_id, request.user)


def _callback_redirect_uri(request) -> str:
    """
    Monta a redirect_uri absoluta do callback.
    """
    return request.build_absolute_uri('/integrations/google/callback/')


def _with_google_connected(path: str) -> str:
    """
    Acrescenta `?google_connected=1` a uma URL interna.

    Preserva query strings existentes.
    """
    safe = safe_redirect_or_fallback(path)
    sep = '&' if '?' in safe else '?'
    return f'{safe}{sep}{GOOGLE_CONNECTED_PARAM}=1'


# =========================================================================
# START — INICIA O FLUXO OAUTH
# =========================================================================

class GoogleOAuthStartView(View):
    """
    GET /integrations/google/start/?next=<path>

    Exige:
        - usuário autenticado;
        - workspace ativo na sessão.

    Fluxo:
        1. Valida pré-requisitos.
        2. Lê `next` da query string e valida.
        3. Gera state no Redis via OAuthStateService (com `next_path`).
        4. Chama GoogleConnector.build_auth_url, passando o email do
           usuário como `login_hint`.
        5. Redireciona (302) para o Google.

    NOTA sobre capability:
        NÃO exigimos `integrations.connection.manage`. Conectar uma
        conta Google é parte de operar o workspace — qualquer membro
        pode. O controle de escopo real acontece nos consumidores
        (ex: `briefings.template.manage` para importar Forms).
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace = _resolve_current_workspace(request)
        if workspace is None:
            messages.error(
                request,
                'Nenhum workspace ativo. Escolha um workspace antes.',
            )
            return redirect('/workspaces/entrar/')

        # Lê e valida o `next`.
        raw_next = request.GET.get('next', '')
        next_path = safe_redirect_or_fallback(raw_next or DEFAULT_NEXT_PATH)

        # `final_redirect` é o destino em caso de FALHA no callback.
        # `next_path` é o destino em caso de SUCESSO.
        # Ambos são o mesmo caminho aqui — o sinal `?google_connected=1`
        # é acrescentado apenas no sucesso.
        final_redirect = next_path

        try:
            provider = IntegrationProvider.objects.get(
                key='google', is_active=True,
            )
        except IntegrationProvider.DoesNotExist:
            logger.warning(
                'Provider Google não encontrado ou inativo | user=%s',
                request.user.pk,
            )
            messages.error(
                request,
                'O provider Google não está disponível neste '
                'momento. Contate o suporte.',
            )
            return redirect(final_redirect)

        redirect_uri = _callback_redirect_uri(request)

        state = OAuthStateService.issue(
            user_id=str(request.user.pk),
            workspace_id=str(workspace.pk),
            provider_key='google',
            resources=DEFAULT_GOOGLE_RESOURCES,
            redirect_uri=redirect_uri,
            final_redirect=final_redirect,
            next_path=next_path,
        )

        try:
            connector = ProviderRegistry.get('google')
            auth_url = connector.build_auth_url(
                redirect_uri=redirect_uri,
                resources=DEFAULT_GOOGLE_RESOURCES,
                state=state,
                # ─────────────────────────────────────────────────
                # login_hint: usa o email do usuário logado na Clivo
                # para pré-selecionar a conta correta no Google.
                #
                # O `accounts` continua sendo a única autoridade
                # sobre "quem é o usuário". Aqui apenas LEMOS
                # `request.user.email`, um campo padrão do Django —
                # sem importar nada de `apps.accounts`.
                # ─────────────────────────────────────────────────
                login_hint=request.user.email,
            )
        except IntegrationConfigurationError:
            logger.exception(
                'Configuração do Google OAuth ausente em /start/',
            )
            messages.error(
                request,
                'O sistema não está configurado para conectar ao '
                'Google. Contate o suporte.',
            )
            return redirect(final_redirect)
        except UnsupportedResourceError:
            logger.exception(
                'Recurso não suportado em /start/: %s',
                DEFAULT_GOOGLE_RESOURCES,
            )
            messages.error(
                request,
                'A configuração de recursos do Google está '
                'inconsistente. Contate o suporte.',
            )
            return redirect(final_redirect)

        logger.info(
            'Iniciando OAuth Google | user=%s | workspace=%s | login_hint=%s',
            request.user.email,
            workspace.pk,
            request.user.email,
        )

        return HttpResponseRedirect(auth_url)


# =========================================================================
# CALLBACK — RECEBE O RETORNO DO GOOGLE
# =========================================================================

class GoogleOAuthCallbackView(View):
    """
    GET /integrations/google/callback/?code=...&state=...

    Fluxo:
        1. Valida state (consome do Redis).
        2. Confirma que `request.user` bate com o contexto do state.
        3. Confirma que o workspace do contexto ainda é acessível.
        4. Troca code por tokens (exchange_code).
        5. Aplica políticas (preservar refresh_token, validar
           escopos, exigir refresh_token durável).
        6. Cifra e persiste a WorkspaceIntegration.
        7. Redireciona:
           - sucesso  → ctx.next_path + `?google_connected=1`
           - falha    → ctx.final_redirect
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        error = request.GET.get('error')
        state_nonce = request.GET.get('state') or ''

        # Consome o state ANTES de checar erro, porque precisamos
        # do `final_redirect`/`next_path` do contexto.
        ctx = OAuthStateService.consume(state_nonce)

        if ctx is None:
            logger.warning(
                'Callback com state inválido/expirado | user=%s',
                request.user.pk,
            )
            messages.error(
                request,
                'Sua sessão de conexão expirou ou é inválida. '
                'Tente novamente.',
            )
            return redirect('/workspaces/entrar/')

        # Confirma vínculo: o usuário que clicou em "Conectar"
        # precisa ser o MESMO que está recebendo o callback.
        if str(request.user.pk) != ctx.user_id:
            logger.warning(
                'Callback state pertence a outro usuário | '
                'esperado=%s atual=%s',
                ctx.user_id, request.user.pk,
            )
            messages.error(
                request,
                'Esta conexão não pertence à sua sessão. '
                'Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        # Se o usuário cancelou, não é erro técnico.
        if error == 'access_denied':
            logger.info(
                'Usuário cancelou OAuth Google | user=%s',
                request.user.pk,
            )
            messages.warning(
                request,
                'Você cancelou a conexão com o Google.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        if error:
            logger.warning(
                'Callback com erro do Google: %s', error,
            )
            messages.error(
                request,
                'O Google retornou um erro ao conectar. '
                'Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        code = request.GET.get('code')
        if not code:
            messages.error(
                request,
                'Código de autorização ausente. Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        # Confirma que o workspace ainda é acessível.
        workspace = WorkspaceQueries.get_for_user(
            ctx.workspace_id, request.user,
        )
        if workspace is None:
            messages.error(
                request,
                'Você não tem mais acesso a este workspace.',
            )
            return redirect('/workspaces/entrar/')

        # Provider.
        try:
            provider = IntegrationProvider.objects.get(
                key=ctx.provider_key, is_active=True,
            )
        except IntegrationProvider.DoesNotExist:
            messages.error(
                request,
                'O provider desta conexão não está mais disponível.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        # Troca code por tokens.
        try:
            connector = ProviderRegistry.get(ctx.provider_key)
            oauth_result = connector.exchange_code(
                code=code,
                redirect_uri=ctx.redirect_uri,
            )
        except OAuthExchangeError:
            logger.warning(
                'Falha ao trocar code por tokens | user=%s',
                request.user.pk,
            )
            messages.error(
                request,
                'Não foi possível concluir a conexão com o Google. '
                'Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))
        except IntegrationError as exc:
            logger.exception(
                'Erro de integração no callback: %s', exc,
            )
            messages.error(
                request,
                'Erro ao processar a conexão. Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        # Aplica políticas e persiste.
        try:
            IntegrationService.upsert_from_oauth(
                workspace=workspace,
                provider=provider,
                oauth_result=oauth_result,
                requested_resources=ctx.resources,
                actor=request.user,
            )
        except InsufficientScopesError as exc:
            missing = exc.context.get('missing_resources', [])
            logger.info(
                'Conexão rejeitada por escopos insuficientes | '
                'user=%s missing=%s',
                request.user.pk, missing,
            )
            messages.error(
                request,
                'Faltam permissões para concluir a conexão. '
                'Reconecte autorizando todas as opções solicitadas.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))
        except WorkspaceIntegrationError as exc:
            reason = exc.context.get('reason')
            if reason == 'no_refresh_token':
                messages.error(
                    request,
                    'O Google não retornou credencial de longa '
                    'duração. Reconecte e autorize o acesso '
                    'permanente.',
                )
            else:
                messages.error(
                    request,
                    'Não foi possível ativar a conexão. '
                    'Tente novamente.',
                )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))
        except Exception:
            logger.exception(
                'Falha inesperada ao persistir integração | user=%s',
                request.user.pk,
            )
            messages.error(
                request,
                'Erro inesperado ao salvar a conexão. '
                'Tente novamente.',
            )
            return redirect(safe_redirect_or_fallback(ctx.final_redirect))

        messages.success(
            request,
            'Google conectado com sucesso.',
        )

        logger.info(
            'Google conectado com sucesso | user=%s | workspace=%s',
            request.user.email,
            workspace.pk,
        )

        # Redireciona para `next_path` com o sinal `?google_connected=1`.
        success_url = _with_google_connected(
            ctx.next_path or ctx.final_redirect
        )
        return redirect(success_url)