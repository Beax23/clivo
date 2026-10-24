"""
Testes de integridade do modelo WorkspaceIntegration.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.integrations.models import (
    IntegrationProvider,
    WorkspaceIntegration,
)


@pytest.fixture
def provider(db):
    return IntegrationProvider.objects.create(
        key='google', name='Google', category='productivity',
    )


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-int')


def _make_integration(workspace, provider, **kwargs):
    defaults = {
        'workspace': workspace,
        'provider': provider,
        'external_account_id': 'ext-1',
        'external_account_email': 'a@b.com',
        'encrypted_payload': b'fake-ciphertext',
        'granted_scopes': [],
    }
    defaults.update(kwargs)
    return WorkspaceIntegration.objects.create(**defaults)


@pytest.mark.django_db
class TestWorkspaceIntegrationConstraints:

    def test_unique_external_account_per_workspace_provider(
        self, workspace, provider,
    ):
        _make_integration(workspace, provider, external_account_id='ext-1')
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _make_integration(
                    workspace, provider, external_account_id='ext-1',
                )

    def test_unique_preferred_active(self, workspace, provider):
        _make_integration(
            workspace, provider,
            external_account_id='a', is_preferred=True,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _make_integration(
                    workspace, provider,
                    external_account_id='b', is_preferred=True,
                )

    def test_two_inactive_preferred_allowed(self, workspace, provider):
        # Constraint condicional considera apenas status='active'.
        _make_integration(
            workspace, provider,
            external_account_id='a', is_preferred=True, status='expired',
        )
        _make_integration(
            workspace, provider,
            external_account_id='b', is_preferred=True, status='expired',
        )

    def test_different_workspaces_can_share_external_id(
        self, provider,
    ):
        from apps.workspaces.models import Workspace
        ws_a = Workspace.objects.create(name='A', slug='a')
        ws_b = Workspace.objects.create(name='B', slug='b')
        _make_integration(ws_a, provider, external_account_id='shared')
        _make_integration(ws_b, provider, external_account_id='shared')