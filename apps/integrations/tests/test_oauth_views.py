"""
Testes das views GoogleOAuthStartView e GoogleOAuthCallbackView.

Não fazem chamadas reais ao Google. O `connector.exchange_code` é
mockado.

DISTINÇÃO IMPORTANTE:
    - `api_client` (DRF) — para views REST com `force_authenticate`.
    - `api_client_owner` — para views HTML. Usa `force_login`
      (sessão Django) para que `request.user` seja populado
      corretamente. `force_authenticate` do DRF NÃO afeta views
      HTML.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from apps.console.models import (
    ConsoleGovernance,
    ConsoleGovernanceCapability,
    ConsoleCapability,
)
from apps.integrations.models import IntegrationProvider
from apps.integrations.providers.types import OAuthResult
from apps.integrations.services.oauth_state import OAuthStateService


User = get_user_model()


# =========================================================================
# FIXTURES GLOBAIS
# =========================================================================

@pytest.fixture(autouse=True)
def clear_cache():
    """Limpa o cache antes e depois de cada teste."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def encryption_key():
    """Chave Fernet válida, sobrescrita em settings durante o teste."""
    key = Fernet.generate_key().decode()
    with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key):
        yield key


# =========================================================================
# GOVERNANÇAS
# =========================================================================

@pytest.fixture
def gov_owner(db):
    return ConsoleGovernance.objects.create(
        key='proprietario', name='Proprietário',
        description='', scope='workspace',
        is_system=True, is_protected=True,
    )


@pytest.fixture
def gov_view_only(db):
    """Governança sem a capability de gerenciar integrações."""
    return ConsoleGovernance.objects.create(
        key='membro_view', name='Membro (view)',
        description='', scope='workspace',
    )


# =========================================================================
# PROVIDER
# =========================================================================

@pytest.fixture
def provider_google(db):
    return IntegrationProvider.objects.create(
        key='google', name='Google', category='productivity',
    )


# =========================================================================
# USUÁRIOS
# =========================================================================

@pytest.fixture
def user_owner(db):
    return User.objects.create_user(
        email='owner@example.com', password='x',
    )


@pytest.fixture
def user_other(db):
    return User.objects.create_user(
        email='other@example.com', password='x',
    )


# =========================================================================
# WORKSPACE
# =========================================================================

@pytest.fixture
def workspace_owner(db, user_owner, gov_owner):
    from apps.workspaces.models import (
        Workspace, WorkspaceMembership,
    )
    ws = Workspace.objects.create(name='WS', slug='ws-oauth')
    WorkspaceMembership.objects.create(
        workspace=ws, user=user_owner, governance=gov_owner,
    )
    return ws


# =========================================================================
# CLIENTS
# =========================================================================

@pytest.fixture
def api_client_owner(
    client, user_owner, workspace_owner,
):
    """
    Cliente Django com sessão autenticada.

    Usa `force_login` (sessão Django) — obrigatório para views HTML.
    `force_authenticate` do DRF afeta apenas as views DRF e NÃO
    popula `request.user` nas Django Views.

    Grava `current_workspace_id` na sessão para que as views possam
    resolver o workspace ativo.
    """
    client.force_login(user_owner)
    session = client.session
    session['current_workspace_id'] = str(workspace_owner.pk)
    session.save()
    return client


# =========================================================================
# HELPERS
# =========================================================================

def _fake_oauth_result(**overrides):
    """
    Constrói um OAuthResult válido para uso nos testes.
    """
    defaults = dict(
        access_token='fake-access',
        refresh_token='fake-refresh',
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        granted_scopes=[
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/forms.body.readonly',
        ],
        external_account_id='ext-user-1',
        external_account_email='user@google.com',
        external_account_display_name='Google User',
        external_account_avatar_url=None,
        provider_metadata={
            'granted_resources': [
                'drive.file.read', 'forms.body.read',
            ],
        },
    )
    defaults.update(overrides)
    return OAuthResult(**defaults)


def _seed_state(
    user, workspace,
    resources=None, final_redirect=None,
):
    """Emite um state OAuth válido para o usuário/workspace."""
    if resources is None:
        resources = ['drive.file.read', 'forms.body.read']
    if final_redirect is None:
        final_redirect = '/fluxo/'
    return OAuthStateService.issue(
        user_id=str(user.pk),
        workspace_id=str(workspace.pk),
        provider_key='google',
        resources=resources,
        redirect_uri='http://testserver/integrations/google/callback/',
        final_redirect=final_redirect,
    )


# =========================================================================
# START VIEW
# =========================================================================

@pytest.mark.django_db
class TestGoogleOAuthStartView:

    def test_requires_authentication(self, client):
        """
        Usuário anônimo → redirect para /login/.
        """
        url = '/integrations/google/start/'
        response = client.get(url)
        assert response.status_code == 302
        assert '/login/' in response.url

    def test_redirects_to_google_with_valid_state(
        self, api_client_owner, provider_google, workspace_owner,
    ):
        """
        Usuário autenticado com capability → redirect (302) para o Google.

        Verifica que `build_auth_url` recebeu os recursos corretos e
        um `state` não vazio.
        """
        url = '/integrations/google/start/'
        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.build_auth_url',
            return_value=(
                'https://accounts.google.com/o/oauth2/auth'
                '?client_id=test&state=whatever'
            ),
        ) as mock_build:
            response = api_client_owner.get(url)

        assert response.status_code == 302
        assert response.url.startswith('https://accounts.google.com')

        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs['resources'] == [
            'drive.file.read', 'forms.body.read',
        ]
        # State é nonce não vazio.
        assert call_kwargs['state']
        assert len(call_kwargs['state']) >= 32

class TestGoogleOAuthCallbackView:

    def test_requires_authentication(self, client):
        """
        Callback recebido sem usuário autenticado → /login/.
        """
        response = client.get(
            '/integrations/google/callback/?code=x&state=y',
        )
        assert response.status_code == 302
        assert '/login/' in response.url

    def test_invalid_state_redirects_to_fallback(
        self, api_client_owner,
    ):
        """
        State inválido/expirado → fallback seguro.
        """
        response = api_client_owner.get(
            '/integrations/google/callback/?code=x&state=invalido',
        )
        assert response.status_code == 302
        assert response.url.startswith('/workspaces/entrar/')

    def test_state_belongs_to_other_user(
        self, api_client_owner, user_other, workspace_owner,
    ):
        """
        State emitido para OUTRO usuário → não permite prosseguir.
        """
        state = _seed_state(user_other, workspace_owner)
        response = api_client_owner.get(
            f'/integrations/google/callback/?code=x&state={state}',
        )
        assert response.status_code == 302
        # Cai no fallback do final_redirect do state (que é o default),
        # não no Google nem em sucesso.
        assert 'accounts.google.com' not in response.url

    def test_user_canceled(
        self, api_client_owner, user_owner, workspace_owner,
    ):
        """
        Usuário clica em "Cancelar" no Google → mensagem de aviso
        e volta ao final_redirect.
        """
        state = _seed_state(user_owner, workspace_owner)
        response = api_client_owner.get(
            f'/integrations/google/callback/'
            f'?error=access_denied&state={state}',
        )
        assert response.status_code == 302
        assert response.url.startswith('/fluxo/')

    def test_exchange_code_fails(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google,
    ):
        """
        Google recusa a troca do code → volta ao final_redirect com erro.
        """
        from apps.integrations.exceptions import OAuthExchangeError
        state = _seed_state(user_owner, workspace_owner)

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            side_effect=OAuthExchangeError('boom'),
        ):
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        assert response.url.startswith('/fluxo/')

    def test_successful_callback_persists_integration(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google, encryption_key,
    ):
        """
        Fluxo feliz: state válido + exchange_code OK → cria
        WorkspaceIntegration e redireciona.
        """
        state = _seed_state(user_owner, workspace_owner)
        fake = _fake_oauth_result()

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake,
        ):
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        assert response.url.startswith('/fluxo/')

        from apps.integrations.models import WorkspaceIntegration
        integration = WorkspaceIntegration.objects.get(
            workspace=workspace_owner, provider=provider_google,
        )
        assert integration.status == WorkspaceIntegration.STATUS_ACTIVE
        assert integration.external_account_id == 'ext-user-1'

    def test_insufficient_scopes_rejects(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google, encryption_key,
    ):
        """
        Se faltam recursos solicitados → conexão NÃO é criada.
        """
        state = _seed_state(user_owner, workspace_owner)
        # Resultado SEM forms.body.read.
        fake = _fake_oauth_result(
            provider_metadata={
                'granted_resources': ['drive.file.read'],
            },
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake,
        ):
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        from apps.integrations.models import WorkspaceIntegration
        assert not WorkspaceIntegration.objects.filter(
            workspace=workspace_owner, provider=provider_google,
        ).exists()

    def test_no_refresh_token_rejects(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google, encryption_key,
    ):
        """
        Sem refresh_token (nem novo nem anterior) → não ativa.
        """
        state = _seed_state(user_owner, workspace_owner)
        fake = _fake_oauth_result(refresh_token=None)

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake,
        ):
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        from apps.integrations.models import WorkspaceIntegration
        assert not WorkspaceIntegration.objects.filter(
            workspace=workspace_owner, provider=provider_google,
        ).exists()

    def test_open_redirect_blocked(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google, encryption_key,
    ):
        """
        `final_redirect` malicioso é substituído por fallback seguro.
        """
        state = _seed_state(
            user_owner, workspace_owner,
            final_redirect='https://evil.com/steal',
        )
        fake = _fake_oauth_result()

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake,
        ):
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        assert 'evil.com' not in response.url
        assert response.url.startswith('/workspaces/entrar/')

    def test_state_is_single_use(
        self, api_client_owner, user_owner, workspace_owner,
        provider_google, encryption_key,
    ):
        """
        Segundo uso do mesmo state falha (consumido).
        """
        state = _seed_state(user_owner, workspace_owner)
        fake = _fake_oauth_result()

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake,
        ):
            # Primeira chamada: OK.
            api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )
            # Segunda chamada: mesmo state.
            response = api_client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}',
            )

        assert response.status_code == 302
        assert response.url.startswith('/workspaces/entrar/')