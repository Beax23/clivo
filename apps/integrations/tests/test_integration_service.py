"""
Testes do IntegrationService.

Cobrem as três políticas:
    1. Preservar refresh_token anterior quando o novo é None.
    2. Não ativar conexão sem refresh_token utilizável.
    3. Rejeitar quando faltam escopos solicitados.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.integrations.encryption.service import EncryptionService
from apps.integrations.exceptions import (
    InsufficientScopesError,
    WorkspaceIntegrationError,
)
from apps.integrations.models import (
    IntegrationProvider,
    WorkspaceIntegration,
)
from apps.integrations.providers.types import OAuthResult
from apps.integrations.services.integration_service import (
    IntegrationService,
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
    return Workspace.objects.create(name='WS', slug='ws-int-svc')


@pytest.fixture
def actor(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(email='actor@example.com', password='x')


def _oauth_result(
    access_token='access',
    refresh_token='refresh',
    expires_in=3600,
    scopes=None,
    granted_resources=None,
    external_id='ext-1',
):
    if scopes is None:
        scopes = ['https://www.googleapis.com/auth/drive.readonly']
    if granted_resources is None:
        granted_resources = ['drive.file.read']

    return OAuthResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        granted_scopes=list(scopes),
        external_account_id=external_id,
        external_account_email='a@b.com',
        external_account_display_name='A B',
        external_account_avatar_url=None,
        provider_metadata={
            'granted_resources': list(granted_resources),
        },
    )


# =========================================================================
# POLÍTICA 1 — preservar refresh_token
# =========================================================================

@pytest.mark.django_db
class TestPreserveRefreshToken:

    def test_preserves_existing_when_new_is_none(
        self, encryption_key, workspace, provider, actor,
    ):
        # Cria uma integração com refresh_token válido.
        initial = _oauth_result(refresh_token='original-refresh')
        IntegrationService.upsert_from_oauth(
            workspace=workspace,
            provider=provider,
            oauth_result=initial,
            requested_resources=['drive.file.read'],
            actor=actor,
        )

        # Nova resposta SEM refresh_token.
        update = _oauth_result(refresh_token=None)
        integration = IntegrationService.upsert_from_oauth(
            workspace=workspace,
            provider=provider,
            oauth_result=update,
            requested_resources=['drive.file.read'],
            actor=actor,
        )

        # O refresh_token anterior foi preservado.
        creds = IntegrationService.get_credentials(integration)
        assert creds['refresh_token'] == 'original-refresh'
        # Mas o access_token foi atualizado.
        assert creds['access_token'] == 'access'

    def test_uses_new_refresh_token_when_present(
        self, encryption_key, workspace, provider, actor,
    ):
        initial = _oauth_result(refresh_token='old-refresh')
        IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=initial,
            requested_resources=['drive.file.read'],
            actor=actor,
        )

        update = _oauth_result(refresh_token='new-refresh')
        integration = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=update,
            requested_resources=['drive.file.read'],
            actor=actor,
        )

        creds = IntegrationService.get_credentials(integration)
        assert creds['refresh_token'] == 'new-refresh'


# =========================================================================
# POLÍTICA 2 — exigir refresh_token durável
# =========================================================================

@pytest.mark.django_db
class TestRequireRefreshToken:

    def test_rejects_when_no_refresh_token_anywhere(
        self, encryption_key, workspace, provider, actor,
    ):
        """Primeira conexão, sem refresh_token, sem anterior."""
        result = _oauth_result(refresh_token=None)
        with pytest.raises(WorkspaceIntegrationError) as exc_info:
            IntegrationService.upsert_from_oauth(
                workspace=workspace, provider=provider,
                oauth_result=result,
                requested_resources=['drive.file.read'],
                actor=actor,
            )
        assert exc_info.value.context['reason'] == 'no_refresh_token'

        # Nenhuma WorkspaceIntegration foi criada.
        assert not WorkspaceIntegration.objects.filter(
            workspace=workspace, provider=provider,
        ).exists()


# =========================================================================
# POLÍTICA 3 — validar escopos
# =========================================================================

@pytest.mark.django_db
class TestScopesValidation:

    def test_rejects_when_missing_requested_resource(
        self, encryption_key, workspace, provider, actor,
    ):
        result = _oauth_result(
            granted_resources=['drive.file.read'],  # só drive
        )
        with pytest.raises(InsufficientScopesError) as exc_info:
            IntegrationService.upsert_from_oauth(
                workspace=workspace, provider=provider,
                oauth_result=result,
                requested_resources=['drive.file.read', 'forms.body.read'],
                actor=actor,
            )
        assert 'forms.body.read' in exc_info.value.context['missing_resources']

    def test_accepts_when_superset(
        self, encryption_key, workspace, provider, actor,
    ):
        result = _oauth_result(
            granted_resources=['drive.file.read', 'forms.body.read'],
        )
        integration = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=result,
            requested_resources=['drive.file.read'],
            actor=actor,
        )
        assert integration.pk is not None


# =========================================================================
# PERSISTÊNCIA
# =========================================================================

@pytest.mark.django_db
class TestPersistence:

    def test_creates_integration(
        self, encryption_key, workspace, provider, actor,
    ):
        result = _oauth_result()
        integration = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=result,
            requested_resources=['drive.file.read'],
            actor=actor,
        )

        assert integration.workspace_id == workspace.id
        assert integration.provider_id == provider.id
        assert integration.external_account_id == 'ext-1'
        assert integration.external_account_email == 'a@b.com'
        assert integration.status == WorkspaceIntegration.STATUS_ACTIVE
        assert integration.encrypted_payload
        # Payload é binário e NÃO contém plaintext dos tokens.
        assert b'access' not in bytes(integration.encrypted_payload)
        assert b'refresh' not in bytes(integration.encrypted_payload)

    def test_updates_existing(
        self, encryption_key, workspace, provider, actor,
    ):
        first = _oauth_result(access_token='first-access')
        i1 = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=first,
            requested_resources=['drive.file.read'],
            actor=actor,
        )
        second = _oauth_result(access_token='second-access')
        i2 = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=second,
            requested_resources=['drive.file.read'],
            actor=actor,
        )
        assert i1.pk == i2.pk
        creds = IntegrationService.get_credentials(i2)
        assert creds['access_token'] == 'second-access'

    def test_payload_has_schema_version(
        self, encryption_key, workspace, provider, actor,
    ):
        result = _oauth_result()
        integration = IntegrationService.upsert_from_oauth(
            workspace=workspace, provider=provider,
            oauth_result=result,
            requested_resources=['drive.file.read'],
            actor=actor,
        )
        creds = IntegrationService.get_credentials(integration)
        assert creds['schema_version'] == 1