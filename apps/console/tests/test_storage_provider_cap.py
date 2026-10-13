"""
Testes do endpoint `/api/console/storage/provider-cap/`.

Cobrem:
    - Provider inexistente → payload com campos nulos.
    - Provider existe sem contrato → is_configured=False.
    - Provider existe com contrato sem teto → is_configured=False.
    - Provider existe com contrato com teto → is_configured=True.
    - Snapshot 'ok' presente → usage_bytes preenchido.
    - Snapshot 'ok' ausente → usage_bytes=None.
    - Último snapshot com erro → last_snapshot_status/error.
    - Autorização.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.console.models import (
    ConsoleMembership,
    Provider,
    ProviderContract,
    StorageProviderSnapshot,
)


User = get_user_model()

CAP_URL = '/api/console/storage/provider-cap/'

GIB = 1024 ** 3


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def admin_client(db):
    from rest_framework.test import APIClient
    user = User.objects.create_user(
        email='admin-cap@example.com',
        password='x',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def plain_client(db):
    from rest_framework.test import APIClient
    user = User.objects.create_user(
        email='plain-cap@example.com',
        password='x',
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def b2_provider(db):
    return Provider.objects.create(
        key='backblaze_b2',
        name='Backblaze B2',
        category='storage',
        is_active=True,
    )


def _make_contract(provider, included_bytes=None, is_active=True):
    return ProviderContract.objects.create(
        provider=provider,
        name='Production',
        included_storage_bytes=included_bytes,
        started_at=date(2026, 1, 1),
        is_active=is_active,
    )


def _make_snapshot(status='ok', usage_bytes=None, provider_key='backblaze_b2'):
    return StorageProviderSnapshot.objects.create(
        provider_key=provider_key,
        status=status,
        storage_usage_bytes=usage_bytes,
        fetched_at=timezone.now(),
    )


# =========================================================================
# AUTORIZAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestProviderCapAuth:

    def test_anonymous_gets_401_or_403(self, api_client):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.get(CAP_URL)
        assert resp.status_code in (401, 403)

    def test_non_console_user_gets_403(self, plain_client):
        resp = plain_client.get(CAP_URL)
        assert resp.status_code == 403

    def test_admin_gets_200(self, admin_client):
        resp = admin_client.get(CAP_URL)
        assert resp.status_code == 200


# =========================================================================
# PROVIDER INEXISTENTE
# =========================================================================

@pytest.mark.django_db
class TestProviderCapNoProvider:

    def test_no_provider_returns_empty_payload(self, admin_client):
        resp = admin_client.get(CAP_URL)
        assert resp.status_code == 200
        assert resp.data['provider_key'] == 'backblaze_b2'
        assert resp.data['provider_name'] == ''
        assert resp.data['provider_is_active'] is False
        assert resp.data['contract_id'] is None
        assert resp.data['included_storage_bytes'] is None
        assert resp.data['is_configured'] is False
        assert resp.data['usage_bytes'] is None


# =========================================================================
# PROVIDER SEM CONTRATO
# =========================================================================

@pytest.mark.django_db
class TestProviderCapNoContract:

    def test_no_contract(self, admin_client, b2_provider):
        resp = admin_client.get(CAP_URL)
        assert resp.status_code == 200
        assert resp.data['provider_key'] == 'backblaze_b2'
        assert resp.data['provider_name'] == 'Backblaze B2'
        assert resp.data['provider_is_active'] is True
        assert resp.data['contract_id'] is None
        assert resp.data['included_storage_bytes'] is None
        assert resp.data['is_configured'] is False


# =========================================================================
# CONTRATO SEM TETO
# =========================================================================

@pytest.mark.django_db
class TestProviderCapContractWithoutCap:

    def test_contract_without_cap_not_configured(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=None)

        resp = admin_client.get(CAP_URL)
        assert resp.status_code == 200
        assert resp.data['contract_id'] is not None
        assert resp.data['contract_name'] == 'Production'
        assert resp.data['included_storage_bytes'] is None
        assert resp.data['is_configured'] is False


# =========================================================================
# CONTRATO COM TETO
# =========================================================================

@pytest.mark.django_db
class TestProviderCapContractWithCap:

    def test_contract_with_cap_configured(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=50 * GIB)

        resp = admin_client.get(CAP_URL)
        assert resp.status_code == 200
        assert resp.data['included_storage_bytes'] == 50 * GIB
        assert resp.data['is_configured'] is True

    def test_inactive_contract_ignored(self, admin_client, b2_provider):
        _make_contract(b2_provider, included_bytes=50 * GIB, is_active=False)

        resp = admin_client.get(CAP_URL)
        assert resp.data['contract_id'] is None
        assert resp.data['is_configured'] is False

    def test_multiple_active_contracts_picks_most_recent(
        self, admin_client, b2_provider,
    ):
        old = ProviderContract.objects.create(
            provider=b2_provider,
            name='Old',
            included_storage_bytes=10 * GIB,
            started_at=date(2025, 1, 1),
            is_active=True,
        )
        new = ProviderContract.objects.create(
            provider=b2_provider,
            name='New',
            included_storage_bytes=50 * GIB,
            started_at=date(2026, 1, 1),
            is_active=True,
        )

        resp = admin_client.get(CAP_URL)

        # O serializer serializa `contract_id` como string no payload
        # JSON. Compara convertendo o `new.id` (UUID) para string.
        assert resp.data['contract_id'] == str(new.id)
        assert resp.data['included_storage_bytes'] == 50 * GIB

        # Sanidade: `old` foi criado e existe, mas não é o escolhido.
        assert old.is_active is True
        assert old.id != new.id


# =========================================================================
# SNAPSHOT
# =========================================================================

@pytest.mark.django_db
class TestProviderCapSnapshot:

    def test_ok_snapshot_provides_usage(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=50 * GIB)
        _make_snapshot(status='ok', usage_bytes=42 * GIB)

        resp = admin_client.get(CAP_URL)
        assert resp.data['usage_bytes'] == 42 * GIB
        assert resp.data['snapshot_status'] == 'ok'
        assert resp.data['last_snapshot_status'] == 'ok'

    def test_no_snapshot_usage_null(self, admin_client, b2_provider):
        _make_contract(b2_provider, included_bytes=50 * GIB)

        resp = admin_client.get(CAP_URL)
        assert resp.data['usage_bytes'] is None
        assert resp.data['snapshot_status'] == ''
        assert resp.data['last_snapshot_status'] == ''

    def test_error_snapshot_does_not_provide_usage(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=50 * GIB)
        _make_snapshot(status='error', usage_bytes=None)

        resp = admin_client.get(CAP_URL)
        assert resp.data['usage_bytes'] is None
        assert resp.data['last_snapshot_status'] == 'error'

    def test_error_after_ok_keeps_last_usage(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=50 * GIB)

        # Snapshot 'ok' com uso.
        StorageProviderSnapshot.objects.create(
            provider_key='backblaze_b2',
            status='ok',
            storage_usage_bytes=42 * GIB,
            fetched_at=timezone.now(),
        )

        # Snapshot de erro mais recente.
        StorageProviderSnapshot.objects.create(
            provider_key='backblaze_b2',
            status='error',
            error_message='Falha temporária',
            fetched_at=timezone.now(),
        )

        resp = admin_client.get(CAP_URL)
        # Uso físico ainda é o do 'ok' mais recente.
        assert resp.data['usage_bytes'] == 42 * GIB
        # Último status é o erro.
        assert resp.data['last_snapshot_status'] == 'error'
        assert resp.data['last_snapshot_error'] == 'Falha temporária'

    def test_other_provider_snapshot_ignored(
        self, admin_client, b2_provider,
    ):
        _make_contract(b2_provider, included_bytes=50 * GIB)
        _make_snapshot(
            status='ok',
            usage_bytes=1 * GIB,
            provider_key='outro_provider',
        )

        resp = admin_client.get(CAP_URL)
        assert resp.data['usage_bytes'] is None