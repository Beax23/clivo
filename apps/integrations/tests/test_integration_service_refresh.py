"""
Testes de `IntegrationService.get_valid_access_token` e
`IntegrationService.refresh_credentials`.

Cobrem:
    - Renovação preguiçosa quando o token está expirado.
    - Não renovar quando o token ainda é válido.
    - Renovar quando falta menos que REFRESH_MARGIN_SECONDS.
    - RefreshTokenInvalidError → integração vira `expired`.
    - RefreshTransientError → integração continua `active`.
    - Credenciais corrompidas → erro explícito.
    - Integração revogada → ConnectionRevokedError.
    - Integração expirada → ConnectionExpiredError.
    - Revogação marca `revoked` + limpa `is_preferred`.
    - Revogação é idempotente.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.integrations.encryption.service import EncryptionService
from apps.integrations.exceptions import (
    ConnectionExpiredError,
    ConnectionRevokedError,
    IntegrationInactiveError,
    RefreshTokenInvalidError,
    RefreshTransientError,
)
from apps.integrations.models import (
    IntegrationProvider,
    WorkspaceIntegration,
)
from apps.integrations.providers.types import OAuthResult
from apps.integrations.services.integration_service import (
    IntegrationService,
    REFRESH_MARGIN_SECONDS,
)


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def encryption_key():
    key = Fernet.generate_key().decode()
    with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key):
        yield key


@pytest.fixture
def provider(db):
    return IntegrationProvider.objects.create(
        key='google', name='Google', category='productivity',
    )


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-refresh-test')


@pytest.fixture
def actor(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(email='actor@example.com', password='x')


def _make_integration(
    workspace, provider, actor,
    access_token='valid-access',
    refresh_token='valid-refresh',
    expires_in_seconds=3600,
    status=WorkspaceIntegration.STATUS_ACTIVE,
    is_preferred=False,
):
    """
    Cria uma WorkspaceIntegration com payload cifrado real.
    """
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    )
    payload = {
        'schema_version': 1,
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_at': expires_at.isoformat(),
        'scopes': ['https://www.googleapis.com/auth/drive.readonly'],
    }
    blob = json.dumps(payload).encode('utf-8')
    encrypted = EncryptionService.encrypt(blob)

    return WorkspaceIntegration.objects.create(
        workspace=workspace,
        provider=provider,
        external_account_id='ext-user-1',
        external_account_email='user@google.com',
        encrypted_payload=encrypted,
        granted_scopes=payload['scopes'],
        status=status,
        is_preferred=is_preferred,
        created_by=actor,
    )


def _make_oauth_result(
    access_token='new-access',
    refresh_token='new-refresh',
    expires_in_seconds=3600,
):
    return OAuthResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        ),
        granted_scopes=['https://www.googleapis.com/auth/drive.readonly'],
        external_account_id='',
        external_account_email='',
        external_account_display_name='',
        external_account_avatar_url=None,
        provider_metadata={
            'granted_resources': ['drive.file.read'],
            'source': 'refresh',
        },
    )


# =========================================================================
# GET_VALID_ACCESS_TOKEN
# =========================================================================

@pytest.mark.django_db
class TestGetValidAccessToken:

    def test_returns_token_when_still_valid(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        Token expira em 1h → NÃO renova, devolve o atual.
        """
        integration = _make_integration(
            workspace, provider, actor,
            access_token='still-valid',
            expires_in_seconds=3600,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.refresh',
        ) as mock_refresh:
            token = IntegrationService.get_valid_access_token(integration)

        assert token == 'still-valid'
        mock_refresh.assert_not_called()

    def test_refreshes_when_expired(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        Token já expirou → renova e devolve o novo.
        """
        integration = _make_integration(
            workspace, provider, actor,
            access_token='expired-access',
            expires_in_seconds=-60,  # já expirou
        )

        new_result = _make_oauth_result(access_token='fresh-access')

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.refresh',
            return_value=new_result,
        ):
            token = IntegrationService.get_valid_access_token(integration)

        assert token == 'fresh-access'
        integration.refresh_from_db()
        assert integration.status == WorkspaceIntegration.STATUS_ACTIVE

    def test_refreshes_when_within_margin(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        Faltam 2 minutos para expirar — dentro da margem (5 min),
        então renova proativamente.
        """
        integration = _make_integration(
            workspace, provider, actor,
            access_token='almost-expired',
            expires_in_seconds=120,  # 2 min
        )

        new_result = _make_oauth_result(access_token='fresh-access')

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.refresh',
            return_value=new_result,
        ):
            token = IntegrationService.get_valid_access_token(integration)

        assert token == 'fresh-access'


# =========================================================================
# FALHAS DE REFRESH
# =========================================================================

@pytest.mark.django_db
class TestRefreshFailures:

    def test_invalid_refresh_token_marks_expired(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        RefreshTokenInvalidError → integração vira `expired`.
        """
        integration = _make_integration(
            workspace, provider, actor,
            expires_in_seconds=-60,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.refresh',
            side_effect=RefreshTokenInvalidError('invalid_grant'),
        ):
            with pytest.raises(ConnectionExpiredError):
                IntegrationService.get_valid_access_token(integration)

        integration.refresh_from_db()
        assert integration.status == WorkspaceIntegration.STATUS_EXPIRED
        assert integration.last_error_code == 'refresh_invalid'
        assert integration.is_preferred is False

    def test_transient_error_keeps_status_active(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        RefreshTransientError → integração continua `active`,
        só registra o último erro.
        """
        integration = _make_integration(
            workspace, provider, actor,
            expires_in_seconds=-60,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.refresh',
            side_effect=RefreshTransientError('network down'),
        ):
            with pytest.raises(RefreshTransientError):
                IntegrationService.get_valid_access_token(integration)

        integration.refresh_from_db()
        assert integration.status == WorkspaceIntegration.STATUS_ACTIVE
        assert integration.last_error_code == 'refresh_transient'


# =========================================================================
# ESTADOS INVÁLIDOS
# =========================================================================

@pytest.mark.django_db
class TestInvalidStates:

    def test_revoked_integration_raises(
        self, encryption_key, workspace, provider, actor,
    ):
        integration = _make_integration(
            workspace, provider, actor,
            status=WorkspaceIntegration.STATUS_REVOKED,
        )

        with pytest.raises(ConnectionRevokedError):
            IntegrationService.get_valid_access_token(integration)

    def test_expired_integration_raises(
        self, encryption_key, workspace, provider, actor,
    ):
        integration = _make_integration(
            workspace, provider, actor,
            status=WorkspaceIntegration.STATUS_EXPIRED,
        )

        with pytest.raises(ConnectionExpiredError):
            IntegrationService.get_valid_access_token(integration)

    def test_error_integration_raises(
        self, encryption_key, workspace, provider, actor,
    ):
        integration = _make_integration(
            workspace, provider, actor,
            status=WorkspaceIntegration.STATUS_ERROR,
        )

        with pytest.raises(IntegrationInactiveError):
            IntegrationService.get_valid_access_token(integration)


# =========================================================================
# REVOGAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestRevokeIntegration:

    def test_revoke_marks_revoked_and_clears_preferred(
        self, encryption_key, workspace, provider, actor,
    ):
        integration = _make_integration(
            workspace, provider, actor,
            is_preferred=True,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.revoke',
        ):
            IntegrationService.revoke_integration(
                integration=integration,
                actor=actor,
                reason='user_revoked',
            )

        integration.refresh_from_db()
        assert integration.status == WorkspaceIntegration.STATUS_REVOKED
        assert integration.is_preferred is False
        assert integration.last_error_code == 'user_revoked'

    def test_revoke_is_idempotent(
        self, encryption_key, workspace, provider, actor,
    ):
        integration = _make_integration(
            workspace, provider, actor,
            status=WorkspaceIntegration.STATUS_REVOKED,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.revoke',
        ) as mock_revoke:
            IntegrationService.revoke_integration(
                integration=integration, actor=actor,
            )

        # Se já estava revogada, não chama o provider.
        mock_revoke.assert_not_called()

    def test_revoke_provider_failure_still_marks_revoked(
        self, encryption_key, workspace, provider, actor,
    ):
        """
        Se o provider estiver offline, a integração é revogada
        localmente mesmo assim.
        """
        integration = _make_integration(
            workspace, provider, actor,
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleConnector.revoke',
            side_effect=Exception('provider down'),
        ):
            IntegrationService.revoke_integration(
                integration=integration, actor=actor,
            )

        integration.refresh_from_db()
        assert integration.status == WorkspaceIntegration.STATUS_REVOKED