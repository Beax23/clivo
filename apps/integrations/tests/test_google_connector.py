"""
Testes do GoogleConnector.

Cobrem:
    - build_auth_url (geração da URL de consentimento)
    - exchange_code (troca de código por tokens)
    - tradução recurso ↔ escopo
    - erros de configuração

Não fazem chamadas reais ao Google. Mockam o `Flow` e o HTTP.

Parâmetros de URL são analisados via urllib.parse, não por
comparação textual. Isso evita falsos positivos/negativos por
encoding.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from apps.integrations.exceptions import (
    IntegrationConfigurationError,
    OAuthExchangeError,
    UnsupportedResourceError,
)
from apps.integrations.providers.google.connector import GoogleConnector
from apps.integrations.providers.types import OAuthResult


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def connector():
    return GoogleConnector()


@pytest.fixture(autouse=True)
def fake_google_client_credentials(settings):
    """
    Injeta credenciais falsas. Não são reais — só para o connector
    não levantar IntegrationConfigurationError.
    """
    settings.INTEGRATIONS_GOOGLE_CLIENT_ID = 'test-client-id'
    settings.INTEGRATIONS_GOOGLE_CLIENT_SECRET = 'test-client-secret'


def _parse(url: str) -> dict:
    """
    Devolve dict de query params já decodificados.
    """
    parsed = urlparse(url)
    return parse_qs(parsed.query)


# =========================================================================
# build_auth_url
# =========================================================================

class TestBuildAuthUrl:

    def test_generates_url_with_expected_host(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='abc123',
        )
        parsed = urlparse(url)
        assert parsed.scheme == 'https'
        assert parsed.netloc == 'accounts.google.com'
        assert parsed.path == '/o/oauth2/auth'

    def test_url_contains_client_id(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='abc123',
        )
        params = _parse(url)
        assert params.get('client_id') == ['test-client-id']

    def test_url_contains_state(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='xyz-987',
        )
        params = _parse(url)
        assert params.get('state') == ['xyz-987']

    def test_url_contains_redirect_uri(self, connector):
        redirect = 'http://localhost:9000/integrations/google/callback/'
        url = connector.build_auth_url(
            redirect_uri=redirect,
            resources=['drive.file.read'],
            state='abc123',
        )
        params = _parse(url)
        assert params.get('redirect_uri') == [redirect]

    def test_url_requests_offline_access(self, connector):
        """access_type=offline é necessário para obter refresh_token."""
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='abc123',
        )
        params = _parse(url)
        assert params.get('access_type') == ['offline']

    def test_url_includes_drive_scope(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='abc123',
        )
        params = _parse(url)
        scopes_str = ' '.join(params.get('scope', []))
        assert 'https://www.googleapis.com/auth/drive.readonly' in scopes_str

    def test_url_includes_forms_scope(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['forms.body.read'],
            state='abc123',
        )
        params = _parse(url)
        scopes_str = ' '.join(params.get('scope', []))
        assert 'https://www.googleapis.com/auth/forms.body.readonly' in scopes_str

    def test_url_includes_multiple_scopes(self, connector):
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read', 'forms.body.read'],
            state='abc123',
        )
        params = _parse(url)
        scopes_str = ' '.join(params.get('scope', []))
        assert 'drive.readonly' in scopes_str
        assert 'forms.body.readonly' in scopes_str

    def test_url_does_not_force_consent(self, connector):
        """
        Sem `prompt='consent'`, o Google só reexibe a tela de
        consentimento quando há escopos novos.
        """
        url = connector.build_auth_url(
            redirect_uri='http://localhost:9000/integrations/google/callback/',
            resources=['drive.file.read'],
            state='abc123',
        )
        params = _parse(url)
        assert 'prompt' not in params

    def test_unknown_resource_raises(self, connector):
        with pytest.raises(UnsupportedResourceError) as exc_info:
            connector.build_auth_url(
                redirect_uri='http://localhost:9000/integrations/google/callback/',
                resources=['unknown.resource'],
                state='abc123',
            )
        assert exc_info.value.context['resource_slug'] == 'unknown.resource'


# =========================================================================
# exchange_code
# =========================================================================

def _mock_flow_fetch(
    token='fake-access-token',
    refresh_token='fake-refresh-token',
    expires_in_seconds=3600,
    scopes=None,
    fetch_exception=None,
):
    """
    Constrói um patch que substitui `Flow.from_client_config` por
    um mock que devolve credenciais controladas.
    """
    if scopes is None:
        scopes = ['https://www.googleapis.com/auth/drive.readonly']

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=expires_in_seconds
    )

    credentials = MagicMock()
    credentials.token = token
    credentials.refresh_token = refresh_token
    credentials.expiry = expires_at.replace(tzinfo=None)
    credentials.scopes = scopes

    flow = MagicMock()
    if fetch_exception is not None:
        flow.fetch_token.side_effect = fetch_exception
    else:
        flow.fetch_token.return_value = None
    flow.credentials = credentials

    return flow


def _patch_flow(flow):
    return patch(
        'apps.integrations.providers.google.connector.Flow.from_client_config',
        return_value=flow,
    )


def _patch_userinfo(payload):
    """
    Substitui `httpx.get` no módulo do connector por um mock
    que devolve `payload`.
    """
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload

    return patch(
        'httpx.get',
        return_value=response,
    )


class TestExchangeCode:

    def test_returns_oauth_result(self, connector):
        flow = _mock_flow_fetch()
        userinfo = {
            'sub': 'user-123',
            'email': 'a@b.com',
            'name': 'User Name',
            'picture': 'https://example.com/pic.jpg',
        }
        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        assert isinstance(result, OAuthResult)
        assert result.access_token == 'fake-access-token'
        assert result.refresh_token == 'fake-refresh-token'
        assert result.expires_at is not None
        assert result.external_account_id == 'user-123'
        assert result.external_account_email == 'a@b.com'
        assert result.external_account_display_name == 'User Name'
        assert result.external_account_avatar_url == 'https://example.com/pic.jpg'

    def test_granted_scopes_preserved(self, connector):
        scopes = [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/forms.body.readonly',
        ]
        flow = _mock_flow_fetch(scopes=scopes)
        userinfo = {'sub': '1', 'email': 'a@b.com', 'name': ''}

        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        assert set(result.granted_scopes) == set(scopes)

    def test_granted_resources_derived_from_scopes(self, connector):
        scopes = [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/forms.body.readonly',
        ]
        flow = _mock_flow_fetch(scopes=scopes)
        userinfo = {'sub': '1', 'email': 'a@b.com', 'name': ''}

        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        granted_resources = result.provider_metadata['granted_resources']
        assert 'drive.file.read' in granted_resources
        assert 'forms.body.read' in granted_resources

    def test_unknown_scopes_ignored(self, connector):
        """
        Escopos que não estão no mapa (herdados de consentimentos
        anteriores, por exemplo) são ignorados — não viram recursos.
        """
        scopes = [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/some-unknown-scope',
        ]
        flow = _mock_flow_fetch(scopes=scopes)
        userinfo = {'sub': '1', 'email': 'a@b.com', 'name': ''}

        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        granted_resources = result.provider_metadata['granted_resources']
        assert 'drive.file.read' in granted_resources
        # Nenhum erro, apenas ignora.
        assert len(granted_resources) == 1

    def test_refresh_token_can_be_none(self, connector):
        """
        O connector aceita que o Google não devolva refresh_token.
        Não levanta erro. A camada de serviço decide o que fazer.
        """
        flow = _mock_flow_fetch(refresh_token=None)
        userinfo = {'sub': '1', 'email': 'a@b.com', 'name': ''}

        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        assert result.refresh_token is None

    def test_exchange_failure_raises_oauth_exchange_error(self, connector):
        flow = _mock_flow_fetch(
            fetch_exception=Exception('invalid_grant'),
        )
        with _patch_flow(flow):
            with pytest.raises(OAuthExchangeError) as exc_info:
                connector.exchange_code(
                    code='abc',
                    redirect_uri='http://localhost:9000/integrations/google/callback/',
                )
        assert exc_info.value.context['provider_key'] == 'google'
        # Não vaza o code.
        assert 'abc' not in str(exc_info.value)

    def test_userinfo_failure_raises_oauth_exchange_error(self, connector):
        flow = _mock_flow_fetch()
        # Resposta de userinfo com erro 500.
        bad_response = MagicMock()
        bad_response.status_code = 500

        with _patch_flow(flow), patch('httpx.get', return_value=bad_response):
            with pytest.raises(OAuthExchangeError) as exc_info:
                connector.exchange_code(
                    code='abc',
                    redirect_uri='http://localhost:9000/integrations/google/callback/',
                )
        assert exc_info.value.context['status_code'] == 500

    def test_expiry_is_timezone_aware(self, connector):
        flow = _mock_flow_fetch()
        userinfo = {'sub': '1', 'email': 'a@b.com', 'name': ''}

        with _patch_flow(flow), _patch_userinfo(userinfo):
            result = connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )

        assert result.expires_at is not None
        assert result.expires_at.tzinfo is not None


# =========================================================================
# resource_to_scope
# =========================================================================

class TestResourceToScope:

    def test_drive_read(self, connector):
        assert connector.resource_to_scope('drive.file.read') == \
            'https://www.googleapis.com/auth/drive.readonly'

    def test_forms_read(self, connector):
        assert connector.resource_to_scope('forms.body.read') == \
            'https://www.googleapis.com/auth/forms.body.readonly'

    def test_unknown_raises(self, connector):
        with pytest.raises(UnsupportedResourceError):
            connector.resource_to_scope('does.not.exist')


# =========================================================================
# missing credentials
# =========================================================================

class TestMissingCredentials:

    @pytest.fixture(autouse=True)
    def _clear_credentials(self, settings):
        settings.INTEGRATIONS_GOOGLE_CLIENT_ID = None
        settings.INTEGRATIONS_GOOGLE_CLIENT_SECRET = None

    def test_raises_when_client_id_missing(self, connector):
        with pytest.raises(IntegrationConfigurationError) as exc_info:
            connector.build_auth_url(
                redirect_uri='http://localhost:9000/integrations/google/callback/',
                resources=['drive.file.read'],
                state='abc123',
            )
        assert exc_info.value.context['missing'] == 'client_id'

    def test_raises_when_client_secret_missing(
        self, connector, settings,
    ):
        settings.INTEGRATIONS_GOOGLE_CLIENT_ID = 'x'
        with pytest.raises(IntegrationConfigurationError) as exc_info:
            connector.build_auth_url(
                redirect_uri='http://localhost:9000/integrations/google/callback/',
                resources=['drive.file.read'],
                state='abc123',
            )
        assert exc_info.value.context['missing'] == 'client_secret'

    def test_exchange_code_raises_when_credentials_missing(self, connector):
        with pytest.raises(IntegrationConfigurationError):
            connector.exchange_code(
                code='abc',
                redirect_uri='http://localhost:9000/integrations/google/callback/',
            )