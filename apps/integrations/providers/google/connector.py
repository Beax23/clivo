"""
GoogleConnector — conector para as APIs do Google (Drive, Forms).

Escopo desta versão:
    - build_auth_url  → IMPLEMENTADO (real)
    - exchange_code   → IMPLEMENTADO (real, via HTTP direto)
    - refresh         → IMPLEMENTADO (real)
    - revoke          → IMPLEMENTADO (real)

O connector é registrado em IntegrationsConfig.ready() e resolvido
pelo ProviderRegistry.

NOTA DE NOMENCLATURA:
    NÃO confundir com `apps.accounts.adapters.social.CustomSocialAccountAdapter`,
    que é o adapter do django-allauth para login de usuário via Google.
    São coisas diferentes:

        - allauth Adapter     → identidade (login via Google)
        - GoogleConnector     → operações com Drive/Forms (ferramentas)

    Usam OAuth Clients DIFERENTES (GOOGLE_CLIENT_ID vs.
    INTEGRATIONS_GOOGLE_CLIENT_ID), com escopos diferentes.

DIVISÃO DE RESPONSABILIDADES:
    O connector TRADUZ fielmente a resposta do Google. NÃO aplica
    políticas de negócio. Especificamente:

        1. Se o Google não devolve refresh_token, o connector reporta
           `None`. A camada de serviço decide se a conexão pode
           prosseguir ou se precisa de nova autorização.

        2. Se o usuário concede menos escopos do que os solicitados,
           o connector reporta o que veio em `granted_scopes`. A
           camada de serviço específica (ex: GoogleDriveService)
           valida se o escopo necessário está presente antes de
           chamar a API.

        3. O connector NÃO valida se `granted_scopes` cobre
           `REQUIRED_RESOURCES`. Essa validação é feita por operação.

        4. `refresh` mapeia erros HTTP do Google para exceções
           específicas (RefreshTokenInvalidError vs. RefreshTransientError).
           A decisão de o que fazer com cada uma é do serviço.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from django.conf import settings
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import Flow

from apps.integrations.exceptions import (
    IntegrationConfigurationError,
    OAuthExchangeError,
    RefreshTokenInvalidError,
    RefreshTransientError,
    UnsupportedResourceError,
)
from apps.integrations.providers.base import ProviderConnector
from apps.integrations.providers.types import OAuthResult

logger = logging.getLogger('integrations')


# Erros do Google que indicam refresh_token permanentemente inválido.
# Se o Google responde com um desses, o usuário precisa reconectar.
_GOOGLE_INVALID_GRANT_ERRORS = frozenset({
    'invalid_grant',
    'invalid_client',
    'unauthorized_client',
})


class GoogleConnector(ProviderConnector):

    key = 'google'

    # =====================================================================
    # MAPA RECURSO → ESCOPO OAUTH
    # =====================================================================
    #
    # Distinção importante:
    #
    #   RECURSO (IntegrationResource.slug) — conceito interno do Clivo.
    #       Ex: "drive.file.read". Descreve uma CAPACIDADE que o
    #       arquiteto autoriza (ler arquivos do Drive).
    #
    #   ESCOPO OAuth (string do Google) — conceito do provider.
    #       Ex: "https://www.googleapis.com/auth/drive.readonly".
    #       Descreve a permissão técnica na API do Google.
    #
    # Este mapa é a ÚNICA fonte de verdade da tradução. Nem o catálogo
    # nem o serviço de alto nível conhecem escopos OAuth.
    #
    # Fonte dos escopos:
    #   https://developers.google.com/identity/protocols/oauth2/scopes

    RESOURCE_TO_SCOPE = {
        'drive.file.read':  'https://www.googleapis.com/auth/drive.readonly',
        'drive.file.write': 'https://www.googleapis.com/auth/drive.file',
        'forms.body.read':  'https://www.googleapis.com/auth/forms.body.readonly',
        'forms.body.write': 'https://www.googleapis.com/auth/forms.body',
        'userinfo.email':   'https://www.googleapis.com/auth/userinfo.email',
        'userinfo.profile': 'https://www.googleapis.com/auth/userinfo.profile',
    }

    # Escopo reverso: dado um escopo OAuth devolvido pelo Google,
    # qual recurso Clivo ele representa.
    #
    # Usado para traduzir `granted_scopes` (Google → Clivo).
    #
    # Nota: o Google pode devolver escopos que não estão no nosso mapa
    # (ex: escopos herdados de consentimentos anteriores via
    # `include_granted_scopes=true`). Esses são simplesmente ignorados
    # na hora de gerar a lista de recursos concedidos — não é erro.
    SCOPE_TO_RESOURCE = {
        v: k for k, v in RESOURCE_TO_SCOPE.items()
    }

    # =====================================================================
    # REQUISITOS POR OPERAÇÃO
    # =====================================================================

    REQUIRED_RESOURCES = {
        'list_files':          ['drive.file.read'],
        'get_file_metadata':   ['drive.file.read'],
        'list_forms':          ['forms.body.read'],
        'get_form':            ['forms.body.read'],
        'list_form_responses': ['forms.body.read'],
    }

    OPTIONAL_RESOURCES = {
        'list_files': ['userinfo.email'],
        'list_forms': ['userinfo.email'],
    }

    # =====================================================================
    # ENDPOINTS OAUTH DO GOOGLE
    # =====================================================================

    GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
    GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'
    GOOGLE_REVOKE_URI = 'https://oauth2.googleapis.com/revoke'
    GOOGLE_USERINFO_URI = 'https://www.googleapis.com/oauth2/v3/userinfo'

    # =====================================================================
    # OAUTH — IMPLEMENTADO
    # =====================================================================

    def build_auth_url(
        self,
        *,
        redirect_uri: str,
        resources: list,
        state: str,
        login_hint: str | None = None,
    ) -> str:
        """
        Gera a URL de consentimento do Google.

        Parâmetros:
            redirect_uri — DEVE estar cadastrado no OAuth Client.
            resources    — slugs de IntegrationResource
                           (ex: ["drive.file.read"]).
                           Traduzidos para escopos OAuth via
                           RESOURCE_TO_SCOPE.
            state        — nonce anti-CSRF gerado pelo chamador.
                           Devolvido intacto pelo Google no callback.
            login_hint   — email do usuário logado na Clivo. Quando
                           informado, o Google pré-seleciona a
                           conta correspondente no consentimento,
                           evitando que outras contas logadas no
                           navegador sejam exibidas por padrão.

                           NÃO há acoplamento com `accounts`: o
                           valor vem de `request.user.email`, que
                           é campo padrão do Django.

        Retorna: URL completa de consentimento.

        Levanta:
            UnsupportedResourceError — resource slug não suportado.
            IntegrationConfigurationError — Client OAuth ausente.

        NOTA sobre `prompt='consent'`:
            Forçamos `prompt='consent'` para GARANTIR que o Google
            envie um `refresh_token` novo a cada autorização.

            Sem isso, o Google pode omitir o `refresh_token` quando
            o usuário já autorizou o app anteriormente — o que
            inviabiliza persistir uma integração durável.

            Trade-off: o usuário vê a tela de consentimento sempre.
            Aceitável em desenvolvimento/testes. Em produção, com o
            app verificado e política de reconexão bem definida,
            pode-se considerar remover este parâmetro.

        NOTA sobre `login_hint`:
            O Google trata `login_hint` como SUGESTÃO. O usuário
            ainda pode trocar para outra conta se quiser. Mas o
            caminho padrão passa a ser a conta correta — que é
            justamente a conta com a qual o usuário faz login na
            Clivo.
        """
        scopes = [self.resource_to_scope(r) for r in resources]
        client_config = self._build_client_config()

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=scopes,
            redirect_uri=redirect_uri,
            state=state,
        )

        # Parâmetros extras enviados ao Google.
        #
        # `access_type='offline'` é necessário para obter refresh_token.
        # `include_granted_scopes='true'` permite reaproveitar
        # consentimentos anteriores (útil para re-autorizações).
        # `prompt='consent'` FORÇA a tela de consentimento a cada
        # autorização — e, com isso, garante o envio de um novo
        # `refresh_token`.
        auth_params = {
            'access_type': 'offline',
            'include_granted_scopes': 'true',
            'prompt': 'consent',
        }

        # Se temos o email do usuário logado na Clivo, usa como
        # `login_hint`. O Google pré-seleciona essa conta.
        if login_hint:
            auth_params['login_hint'] = login_hint

        auth_url, _ = flow.authorization_url(**auth_params)

        logger.debug(
            'Google auth URL gerada | scopes=%s | redirect=%s | '
            'login_hint=%s | prompt=consent',
            scopes, redirect_uri, login_hint or '—',
        )

        return auth_url

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OAuthResult:
        """
        Troca um `code` de autorização por tokens OAuth.

        Faz a chamada HTTP DIRETAMENTE ao endpoint de token do
        Google, em vez de usar `Flow.fetch_token`.

        MOTIVO DA MUDANÇA:
            O `Flow.fetch_token` do `google-auth-oauthlib` faz uma
            validação de escopos que dispara `Warning` em vários
            cenários legítimos (ex: o Google devolve `openid`,
            `email`, `profile` além dos escopos solicitados).
            Como o Clivo só se importa com os escopos que
            efetivamente consegue traduzir em recursos, essa
            validação agressiva é desnecessária e quebra o fluxo.

            A chamada HTTP direta devolve exatamente o mesmo
            payload, sem a camada de validação.

        Parâmetros:
            code         — `code` devolvido pelo Google no callback.
            redirect_uri — o MESMO redirect_uri usado em `build_auth_url`.

        Retorna: `OAuthResult` com:
            - access_token
            - refresh_token (pode ser None — ver nota abaixo)
            - expires_at
            - granted_scopes (o que o Google efetivamente concedeu)
            - external_account_id, email, display_name, avatar_url

        Levanta:
            OAuthExchangeError — se o Google recusa a troca.
            IntegrationConfigurationError — Client OAuth ausente.

        NOTA sobre `refresh_token=None`:
            O Google pode não devolver `refresh_token` quando o
            usuário já consentiu antes. Nesse caso, devolvemos `None`.
            A camada de serviço (IntegrationService.upsert_from_oauth)
            é quem decide se preserva um refresh_token anterior ou
            se recusa ativar a conexão.
        """
        client_config = self._build_client_config()
        web_config = client_config['web']

        # Chamada HTTP direta ao endpoint de token do Google.
        # O contrato é idêntico ao do `Flow`, mas sem validação
        # de escopos.
        try:
            response = httpx.post(
                web_config['token_uri'],
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': redirect_uri,
                    'client_id': web_config['client_id'],
                    'client_secret': web_config['client_secret'],
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                },
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                'Falha de rede ao trocar code por tokens (Google): %s',
                type(exc).__name__,
            )
            raise OAuthExchangeError(
                'Não foi possível trocar o código de autorização '
                'por tokens.',
                context={
                    'provider_key': self.key,
                    'error_type': type(exc).__name__,
                },
            ) from exc

        # Se o Google recusou, extrai o motivo para o contexto
        # (sem vazar o code nem os tokens).
        if response.status_code != 200:
            error_code = None
            error_description = None
            try:
                payload = response.json()
                error_code = payload.get('error')
                error_description = payload.get('error_description')
            except Exception:
                pass

            logger.warning(
                'Google recusou exchange_code | status=%s | error=%s',
                response.status_code, error_code,
            )
            raise OAuthExchangeError(
                'O Google recusou a troca do código de autorização '
                'por tokens.',
                context={
                    'provider_key': self.key,
                    'status_code': response.status_code,
                    'error': error_code,
                    'error_description': error_description,
                },
            )

        # Parse do payload JSON.
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning(
                'Google devolveu payload não-JSON em exchange_code',
            )
            raise OAuthExchangeError(
                'O Google devolveu uma resposta inválida.',
                context={
                    'provider_key': self.key,
                    'error_type': 'invalid_json',
                },
            ) from exc

        access_token = data.get('access_token')
        refresh_token = data.get('refresh_token')
        expires_in = data.get('expires_in')
        granted_scopes = data.get('scope', '').split()

        if not access_token:
            logger.warning(
                'Google não devolveu access_token em exchange_code',
            )
            raise OAuthExchangeError(
                'O Google não devolveu o token de acesso.',
                context={'provider_key': self.key},
            )

        # Normaliza expires_at a partir de `expires_in`.
        expires_at = None
        if expires_in:
            try:
                expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(expires_in),
                )
            except (TypeError, ValueError):
                expires_at = None

        # Busca userinfo usando o access_token.
        userinfo = self._fetch_userinfo(access_token)

        # Traduz escopos → recursos Clivo.
        granted_resources = self._scopes_to_resources(granted_scopes)

        logger.info(
            'exchange_code OK | account=%s | has_refresh=%s | scopes=%s',
            userinfo.get('email', '?'),
            bool(refresh_token),
            granted_scopes,
        )

        return OAuthResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            granted_scopes=list(granted_scopes),
            external_account_id=userinfo.get('sub', ''),
            external_account_email=userinfo.get('email', ''),
            external_account_display_name=userinfo.get('name', ''),
            external_account_avatar_url=userinfo.get('picture'),
            provider_metadata={
                'granted_resources': granted_resources,
                'userinfo': userinfo,
            },
        )

    def refresh(
        self,
        *,
        refresh_token: str,
    ) -> OAuthResult:
        """
        Renova o access_token usando um refresh_token.

        Parâmetros:
            refresh_token — refresh_token previamente obtido via
                            `exchange_code`.

        Retorna: `OAuthResult` com:
            - access_token (novo)
            - refresh_token (o MESMO que foi passado — o Google
              geralmente não devolve um novo em refresh)
            - expires_at (novo)
            - granted_scopes (o Google pode devolver os mesmos
              escopos; usamos o que vier)
            - external_account_* (o Google NÃO devolve userinfo em
              refresh; esses campos vêm vazios)

        Levanta:
            RefreshTokenInvalidError — refresh_token revogado,
                expirado ou inválido. O usuário precisa reconectar.
            RefreshTransientError — erro transitório (rede, 5xx,
                rate limit). Retry é possível.
            IntegrationConfigurationError — Client OAuth ausente.

        NOTA sobre os campos de identidade:
            Um refresh NÃO devolve `sub`, `email`, etc. Esses campos
            vêm vazios no `OAuthResult` de refresh. O chamador
            (IntegrationService) NÃO usa esse resultado para atualizar
            a identidade da integração — só os tokens.

        NOTA sobre rotação de refresh_token:
            O Google geralmente NÃO rotaciona o refresh_token. Mas
            se ele devolver um novo (o que é raro, mas acontece em
            algumas políticas de segurança), usamos o novo. O
            chamador deve sempre persistir o refresh_token devolvido,
            mesmo que seja igual ao anterior.
        """
        client_config = self._build_client_config()

        # Método 1: usar google-auth (mais robusto).
        # Tentamos primeiro este caminho porque ele mapeia erros
        # de forma mais estruturada.
        try:
            return self._refresh_via_google_auth(
                client_config=client_config,
                refresh_token=refresh_token,
            )
        except RefreshError as exc:
            # google-auth devolve RefreshError. Precisamos distinguir
            # "inválido permanentemente" de "transitório".
            message = str(exc).lower()

            # O Google devolve "invalid_grant" para refresh_token
            # inválido/expirado/revogado.
            if 'invalid_grant' in message or 'invalid_client' in message:
                logger.warning(
                    'Refresh token inválido (Google): %s',
                    type(exc).__name__,
                )
                raise RefreshTokenInvalidError(
                    'A credencial de longa duração foi revogada ou '
                    'expirou. O usuário precisa reconectar a integração.',
                    context={'provider_key': self.key},
                ) from exc

            # Qualquer outra coisa é transitória (rede, 5xx, rate
            # limit).
            logger.warning(
                'Falha transitória no refresh (Google): %s',
                type(exc).__name__,
            )
            raise RefreshTransientError(
                'Falha temporária ao renovar a credencial. '
                'Tente novamente.',
                context={'provider_key': self.key},
            ) from exc

    def revoke(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        """
        Revoga tokens no Google.

        Estratégia:
            - Revoga AMBOS os tokens (access e refresh) via endpoint
              /revoke do Google.
            - Best-effort: se o Google não responder, loga mas NÃO
              levanta. A revogação LOCAL é responsabilidade do
              IntegrationService — o Google ser notificado é o ideal,
              mas não bloqueia o fluxo do usuário.

        Parâmetros:
            access_token  — access_token atual.
            refresh_token — refresh_token (pode ser None).

        NOTA sobre idempotência:
            Se o token já foi revogado no Google, o endpoint devolve
            200 (idempotente). Não é erro.
        """
        tokens_to_revoke = []
        if refresh_token:
            tokens_to_revoke.append(refresh_token)
        if access_token:
            tokens_to_revoke.append(access_token)

        if not tokens_to_revoke:
            return

        for token in tokens_to_revoke:
            try:
                response = httpx.post(
                    self.GOOGLE_REVOKE_URI,
                    data={'token': token},
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    timeout=10.0,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    'Falha de rede ao revogar token no Google: %s',
                    type(exc).__name__,
                )
                continue

            if response.status_code >= 500:
                logger.warning(
                    'Google devolveu %s ao revogar token',
                    response.status_code,
                )
                continue

            # 200 = revogado (ou já revogado).
            # 400 = token inválido (já revogado ou nunca existiu).
            # Ambos são "efeito desejado alcançado".
            if response.status_code not in (200, 400):
                logger.warning(
                    'Google devolveu %s ao revogar token',
                    response.status_code,
                )

        logger.info(
            'Revogação no Google concluída (best-effort) | tokens=%d',
            len(tokens_to_revoke),
        )

    # =====================================================================
    # MAPEAMENTO
    # =====================================================================

    def resource_to_scope(self, resource_slug: str) -> str:
        scope = self.RESOURCE_TO_SCOPE.get(resource_slug)
        if scope is None:
            raise UnsupportedResourceError(
                f'Recurso "{resource_slug}" não suportado pelo GoogleConnector.',
                context={
                    'provider_key': self.key,
                    'resource_slug': resource_slug,
                },
            )
        return scope

    def required_resources_for_operation(self, operation: str) -> list:
        return list(self.REQUIRED_RESOURCES.get(operation, []))

    def optional_resources_for_operation(self, operation: str) -> list:
        return list(self.OPTIONAL_RESOURCES.get(operation, []))

    # =====================================================================
    # HELPERS INTERNOS
    # =====================================================================

    def _refresh_via_google_auth(
        self,
        *,
        client_config: dict,
        refresh_token: str,
    ) -> OAuthResult:
        """
        Renova o token usando `google.oauth2.credentials.Credentials`.

        Este caminho é preferível ao refresh manual via HTTP porque
        o `google-auth` mapeia os erros do Google de forma estruturada
        (RefreshError), permitindo distinguir "inválido" de
        "transitório" com precisão.
        """
        web_config = client_config['web']

        credentials = GoogleCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=web_config['token_uri'],
            client_id=web_config['client_id'],
            client_secret=web_config['client_secret'],
            scopes=[],
        )

        # Este é o ponto onde o RefreshError pode ser levantado.
        # Não capturamos aqui — deixamos subir para `refresh()`, que
        # traduz para as exceções do domínio.
        credentials.refresh(GoogleAuthRequest())

        return OAuthResult(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token or refresh_token,
            expires_at=self._normalize_expiry(credentials.expiry),
            granted_scopes=list(credentials.scopes or []),
            # Campos de identidade NÃO vêm em refresh.
            external_account_id='',
            external_account_email='',
            external_account_display_name='',
            external_account_avatar_url=None,
            provider_metadata={
                'granted_resources': self._scopes_to_resources(
                    credentials.scopes or []
                ),
                'source': 'refresh',
            },
        )

    def _build_client_config(self) -> dict:
        """
        Monta o dict no formato que `Flow.from_client_config` espera.

        Lê de INTEGRATIONS_GOOGLE_CLIENT_ID (dedicado ao integrations),
        NÃO de GOOGLE_CLIENT_ID (allauth).
        """
        client_id = getattr(
            settings, 'INTEGRATIONS_GOOGLE_CLIENT_ID', None,
        )
        client_secret = getattr(
            settings, 'INTEGRATIONS_GOOGLE_CLIENT_SECRET', None,
        )

        if not client_id:
            raise IntegrationConfigurationError(
                'INTEGRATIONS_GOOGLE_CLIENT_ID não está configurado.',
                context={
                    'provider_key': self.key,
                    'missing': 'client_id',
                },
            )
        if not client_secret:
            raise IntegrationConfigurationError(
                'INTEGRATIONS_GOOGLE_CLIENT_SECRET não está configurado.',
                context={
                    'provider_key': self.key,
                    'missing': 'client_secret',
                },
            )

        return {
            'web': {
                'client_id': client_id,
                'client_secret': client_secret,
                'auth_uri': self.GOOGLE_AUTH_URI,
                'token_uri': self.GOOGLE_TOKEN_URI,
            }
        }

    def _fetch_userinfo(self, access_token: str) -> dict:
        """
        Busca informações da conta externa via Google UserInfo API.

        Não usa `google-api-python-client` — usa HTTP direto.
        Isso mantém a superfície de dependências pequena.

        Levanta OAuthExchangeError se o Google recusar.
        """
        try:
            response = httpx.get(
                self.GOOGLE_USERINFO_URI,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                'Falha ao buscar userinfo (Google): %s',
                type(exc).__name__,
            )
            raise OAuthExchangeError(
                'Não foi possível obter dados da conta Google.',
                context={
                    'provider_key': self.key,
                    'error_type': type(exc).__name__,
                },
            ) from exc

        if response.status_code != 200:
            logger.warning(
                'Google userinfo retornou %s',
                response.status_code,
            )
            raise OAuthExchangeError(
                'O Google recusou a consulta de userinfo.',
                context={
                    'provider_key': self.key,
                    'status_code': response.status_code,
                },
            )

        return response.json()

    def _scopes_to_resources(self, scopes: list) -> list:
        """
        Traduz uma lista de escopos OAuth do Google para slugs de
        recursos Clivo.

        Escopos que não estão no mapa são ignorados silenciosamente.
        Isso é esperado: `include_granted_scopes=true` pode devolver
        escopos concedidos em consentimentos anteriores.
        """
        resources = []
        for scope in scopes:
            resource = self.SCOPE_TO_RESOURCE.get(scope)
            if resource is not None:
                resources.append(resource)
        return resources

    @staticmethod
    def _normalize_expiry(expiry) -> datetime | None:
        """
        Normaliza o `expiry` do `google.auth.credentials.Credentials`.

        O Google devolve um `datetime` naive (sem tzinfo). Convertemos
        para UTC, para não gerar ambiguidade quando comparado com
        `timezone.now()`.
        """
        if expiry is None:
            return None
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry