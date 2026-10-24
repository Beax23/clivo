"""
Testes do fluxo OAuth com `next`.

Cobrem:
    - `start` aceita `?next=...` e valida.
    - `start` rejeita `next` malicioso (open redirect).
    - `callback` bem-sucedido redireciona para `next_path`
      com `?google_connected=1`.
    - `callback` com erro redireciona para `final_redirect`
      (sem o sinal).
    - `next_path` com query string existente é respeitado.
"""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from apps.integrations.models import IntegrationProvider
from apps.integrations.services.oauth_state import OAuthStateService
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.console.models import ConsoleGovernance


User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def encryption_key():
    key = Fernet.generate_key().decode()
    with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key):
        yield key


@pytest.fixture
def gov_owner(db):
    return ConsoleGovernance.objects.create(
        key='proprietario',
        name='Proprietário',
        description='',
        scope='workspace',
        is_system=True,
        is_protected=True,
    )


@pytest.fixture
def user_owner(db):
    return User.objects.create_user(
        email='owner-oauth@example.com', password='x',
    )


@pytest.fixture
def workspace(db, user_owner, gov_owner):
    ws = Workspace.objects.create(name='WS', slug='ws-oauth-next')
    WorkspaceMembership.objects.create(
        workspace=ws, user=user_owner, governance=gov_owner,
    )
    return ws


@pytest.fixture
def provider_google(db):
    return IntegrationProvider.objects.create(
        key='google', name='Google', category='productivity',
    )


@pytest.fixture
def client_owner(client, user_owner, workspace):
    client.force_login(user_owner)
    session = client.session
    session['current_workspace_id'] = str(workspace.pk)
    session.save()
    return client


# =========================================================================
# START
# =========================================================================

@pytest.mark.django_db
class TestStartWithNext:

    def test_start_with_valid_next(
        self, client_owner, workspace, provider_google, encryption_key,
    ):
        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.build_auth_url',
            return_value='https://accounts.google.com/o/oauth2/auth?x=y',
        ) as mock_build:
            response = client_owner.get(
                '/integrations/google/start/?next=/fluxo/'
            )

        assert response.status_code == 302
        call_kwargs = mock_build.call_args.kwargs
        state = call_kwargs['state']
        ctx = OAuthStateService.consume(state)
        assert ctx is not None
        assert ctx.next_path == '/fluxo/'

    def test_start_with_malicious_next_falls_back(
        self, client_owner, provider_google, encryption_key,
    ):
        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.build_auth_url',
            return_value='https://accounts.google.com/o/oauth2/auth?x=y',
        ) as mock_build:
            client_owner.get(
                '/integrations/google/start/?next=https://evil.com/steal'
            )

        state = mock_build.call_args.kwargs['state']
        ctx = OAuthStateService.consume(state)
        assert ctx.next_path == '/workspaces/entrar/'

    def test_start_without_next_uses_default(
        self, client_owner, provider_google, encryption_key,
    ):
        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.build_auth_url',
            return_value='https://accounts.google.com/o/oauth2/auth?x=y',
        ) as mock_build:
            client_owner.get('/integrations/google/start/')

        state = mock_build.call_args.kwargs['state']
        ctx = OAuthStateService.consume(state)
        assert ctx.next_path == '/workspaces/entrar/'


# =========================================================================
# CALLBACK
# =========================================================================

@pytest.mark.django_db
class TestCallbackWithNext:

    def test_callback_with_error_redirects_without_signal(
        self, client_owner, user_owner, workspace, provider_google,
    ):
        state = OAuthStateService.issue(
            user_id=str(user_owner.pk),
            workspace_id=str(workspace.pk),
            provider_key='google',
            resources=['forms.body.read'],
            redirect_uri='http://testserver/integrations/google/callback/',
            final_redirect='/fluxo/',
            next_path='/fluxo/',
        )
        response = client_owner.get(
            f'/integrations/google/callback/?error=access_denied&state={state}'
        )
        assert response.status_code == 302
        assert response.url == '/fluxo/'
        assert 'google_connected' not in response.url

    def test_callback_success_redirects_with_signal(
        self, client_owner, user_owner, workspace, provider_google,
        encryption_key,
    ):
        from datetime import datetime, timedelta, timezone
        from apps.integrations.providers.types import OAuthResult

        state = OAuthStateService.issue(
            user_id=str(user_owner.pk),
            workspace_id=str(workspace.pk),
            provider_key='google',
            resources=['forms.body.read'],
            redirect_uri='http://testserver/integrations/google/callback/',
            final_redirect='/fluxo/',
            next_path='/fluxo/',
        )

        fake_oauth = OAuthResult(
            access_token='access',
            refresh_token='refresh',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_scopes=[
                'https://www.googleapis.com/auth/forms.body.readonly',
            ],
            external_account_id='ext-1',
            external_account_email='a@b.com',
            external_account_display_name='A B',
            external_account_avatar_url=None,
            provider_metadata={
                'granted_resources': ['forms.body.read'],
            },
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake_oauth,
        ):
            response = client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}'
            )

        assert response.status_code == 302
        assert response.url == '/fluxo/?google_connected=1'

    def test_callback_preserves_query_string_in_next(
        self, client_owner, user_owner, workspace, provider_google,
        encryption_key,
    ):
        from datetime import datetime, timedelta, timezone
        from apps.integrations.providers.types import OAuthResult

        state = OAuthStateService.issue(
            user_id=str(user_owner.pk),
            workspace_id=str(workspace.pk),
            provider_key='google',
            resources=['forms.body.read'],
            redirect_uri='http://testserver/integrations/google/callback/',
            final_redirect='/fluxo/?tab=forms',
            next_path='/fluxo/?tab=forms',
        )

        fake_oauth = OAuthResult(
            access_token='access',
            refresh_token='refresh',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_scopes=[
                'https://www.googleapis.com/auth/forms.body.readonly',
            ],
            external_account_id='ext-1',
            external_account_email='a@b.com',
            external_account_display_name='A B',
            external_account_avatar_url=None,
            provider_metadata={'granted_resources': ['forms.body.read']},
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.exchange_code',
            return_value=fake_oauth,
        ):
            response = client_owner.get(
                f'/integrations/google/callback/?code=x&state={state}'
            )

        assert response.status_code == 302
        assert 'tab=forms' in response.url
        assert 'google_connected=1' in response.url