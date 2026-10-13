"""
Testes dos endpoints do StorageViewSet.

Cobre:
    - Autenticação e autorização (IsAuthenticated + IsConsoleAdmin).
    - Envelope `current` / `latest`.
    - Casos: nunca sincronizado, só ok, erro após ok.
    - `is_stale` e `is_failed` derivados.
    - Histórico com paginação limitada.
    - Isolamento entre provider_key diferentes.

Usa as fixtures `admin_client` / `plain_client` / `api_client` definidas
em `apps/console/tests/conftest.py`.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.console.models import StorageProviderSnapshot
from apps.console.services.b2_usage_service import PROVIDER_KEY_B2


# =========================================================================
# HELPERS
# =========================================================================

SNAPSHOT_URL = '/api/console/storage/provider-snapshot/'
HISTORY_URL = '/api/console/storage/provider-snapshot/history/'


def _make_snapshot(
    status: str = StorageProviderSnapshot.STATUS_OK,
    provider_key: str = PROVIDER_KEY_B2,
    storage_usage_bytes: int = 100,
    raw_payload: dict = None,
    error_message: str = '',
    fetched_at=None,
):
    """Cria um snapshot real no banco de teste."""
    return StorageProviderSnapshot.objects.create(
        provider_key=provider_key,
        status=status,
        storage_usage_bytes=storage_usage_bytes,
        raw_payload=raw_payload,
        error_message=error_message,
        fetched_at=fetched_at or timezone.now(),
    )


# =========================================================================
# AUTENTICAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestStorageViewAuth:

    def test_anonymous_gets_401_or_403(self, api_client):
        response = api_client.get(SNAPSHOT_URL)
        assert response.status_code in (401, 403)

    def test_authenticated_without_console_membership_gets_403(self, plain_client):
        response = plain_client.get(SNAPSHOT_URL)
        assert response.status_code == 403

    def test_history_requires_console_membership(self, plain_client):
        response = plain_client.get(HISTORY_URL)
        assert response.status_code == 403

    def test_admin_gets_200(self, admin_client):
        response = admin_client.get(SNAPSHOT_URL)
        assert response.status_code == 200


# =========================================================================
# ENVELOPE current / latest — SEM SNAPSHOTS
# =========================================================================

@pytest.mark.django_db
class TestSnapshotEmpty:

    def test_both_null_when_no_snapshots(self, admin_client):
        response = admin_client.get(SNAPSHOT_URL)

        assert response.status_code == 200
        assert response.data['current'] is None
        assert response.data['latest'] is None


# =========================================================================
# ENVELOPE current / latest — SÓ OK
# =========================================================================

@pytest.mark.django_db
class TestSnapshotOnlyOk:

    def test_current_equals_latest(self, admin_client):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=2048,
        )

        response = admin_client.get(SNAPSHOT_URL)

        assert response.status_code == 200
        assert response.data['current'] is not None
        assert response.data['latest'] is not None
        assert response.data['current']['id'] == str(snapshot.id)
        assert response.data['latest']['id'] == str(snapshot.id)

    def test_is_failed_false_for_ok(self, admin_client):
        _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)
        response = admin_client.get(SNAPSHOT_URL)
        assert response.data['current']['is_failed'] is False

    def test_is_stale_false_for_recent_ok(self, admin_client):
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=timezone.now(),
        )
        response = admin_client.get(SNAPSHOT_URL)
        assert response.data['current']['is_stale'] is False


# =========================================================================
# ENVELOPE current / latest — ERRO APÓS OK
# =========================================================================

@pytest.mark.django_db
class TestSnapshotErrorAfterOk:

    def test_current_is_last_ok_while_latest_is_error(self, admin_client):
        # Snapshot 'ok' antigo
        ok_snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=5000,
            fetched_at=timezone.now() - timedelta(hours=2),
        )
        # Snapshot 'error' mais recente
        error_snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='falha temporária',
            fetched_at=timezone.now(),
        )

        response = admin_client.get(SNAPSHOT_URL)

        assert response.data['current']['id'] == str(ok_snapshot.id)
        assert response.data['latest']['id'] == str(error_snapshot.id)

    def test_current_is_not_failed(self, admin_client):
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=timezone.now() - timedelta(hours=2),
        )
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='boom',
            fetched_at=timezone.now(),
        )

        response = admin_client.get(SNAPSHOT_URL)

        assert response.data['current']['is_failed'] is False
        assert response.data['latest']['is_failed'] is True

    def test_error_snapshot_is_not_stale(self, admin_client):
        """
        Regra: só snapshots 'ok' podem ser stale. Um snapshot de erro
        é 'failed', o que é outro estado — não conta como stale.
        """
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='boom',
            fetched_at=timezone.now() - timedelta(days=5),
        )

        response = admin_client.get(SNAPSHOT_URL)

        assert response.data['latest']['is_stale'] is False
        assert response.data['latest']['is_failed'] is True


# =========================================================================
# IS_STALE
# =========================================================================

@pytest.mark.django_db
class TestStale:

    def test_ok_within_25h_not_stale(self, admin_client):
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=timezone.now() - timedelta(hours=23),
        )
        response = admin_client.get(SNAPSHOT_URL)
        assert response.data['current']['is_stale'] is False

    def test_ok_beyond_25h_is_stale(self, admin_client):
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=timezone.now() - timedelta(hours=26),
        )
        response = admin_client.get(SNAPSHOT_URL)
        assert response.data['current']['is_stale'] is True

    def test_stale_uses_setting_override(self, admin_client, settings):
        """
        O limiar é configurável via `STORAGE_SNAPSHOT_STALE_HOURS`.
        Aqui sobrescrevemos para 1h e validamos que um snapshot de
        2h é considerado stale.
        """
        settings.STORAGE_SNAPSHOT_STALE_HOURS = 1

        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=timezone.now() - timedelta(hours=2),
        )
        response = admin_client.get(SNAPSHOT_URL)
        assert response.data['current']['is_stale'] is True


# =========================================================================
# ISOLAMENTO ENTRE PROVIDERS
# =========================================================================

@pytest.mark.django_db
class TestProviderIsolation:

    def test_other_provider_snapshot_is_ignored(self, admin_client):
        """
        Um snapshot com provider_key='outro_provider' NÃO aparece
        no endpoint — porque o default é 'backblaze_b2'.
        """
        _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            provider_key='outro_provider',
            storage_usage_bytes=999999,
        )
        response = admin_client.get(SNAPSHOT_URL)

        assert response.data['current'] is None
        assert response.data['latest'] is None

    def test_default_provider_key_is_b2(self, admin_client):
        b2_snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            provider_key=PROVIDER_KEY_B2,
            storage_usage_bytes=1234,
        )

        response = admin_client.get(SNAPSHOT_URL)

        assert response.data['current']['id'] == str(b2_snapshot.id)

    def test_explicit_provider_key_query_param(self, admin_client):
        other_snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            provider_key='outro_provider',
            storage_usage_bytes=5000,
        )

        response = admin_client.get(SNAPSHOT_URL + '?provider_key=outro_provider')

        assert response.data['current']['id'] == str(other_snapshot.id)


# =========================================================================
# HISTORY
# =========================================================================

@pytest.mark.django_db
class TestHistory:

    def test_empty_history(self, admin_client):
        response = admin_client.get(HISTORY_URL)

        assert response.status_code == 200
        assert response.data['count'] == 0
        assert response.data['results'] == []
        assert response.data['provider_key'] == PROVIDER_KEY_B2

    def test_history_default_limit_20(self, admin_client):
        for _ in range(25):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL)

        assert response.data['count'] == 20

    def test_history_custom_limit(self, admin_client):
        for _ in range(10):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL + '?limit=3')

        assert response.data['count'] == 3

    def test_history_limit_capped_at_100(self, admin_client):
        for _ in range(5):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL + '?limit=999')

        # Só existem 5; o limite máximo é 100, mas a resposta é min(5, 100)
        assert response.data['count'] == 5

    def test_history_limit_invalid_falls_back_to_20(self, admin_client):
        for _ in range(25):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL + '?limit=abc')

        assert response.data['count'] == 20

    def test_history_limit_zero_falls_back_to_1(self, admin_client):
        for _ in range(5):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL + '?limit=0')

        # O clamp inferior é 1
        assert response.data['count'] == 1

    def test_history_limit_negative_falls_back_to_1(self, admin_client):
        for _ in range(5):
            _make_snapshot(status=StorageProviderSnapshot.STATUS_OK)

        response = admin_client.get(HISTORY_URL + '?limit=-3')

        assert response.data['count'] == 1

    def test_history_isolates_providers(self, admin_client):
        for _ in range(3):
            _make_snapshot(
                status=StorageProviderSnapshot.STATUS_OK,
                provider_key=PROVIDER_KEY_B2,
            )
        for _ in range(5):
            _make_snapshot(
                status=StorageProviderSnapshot.STATUS_OK,
                provider_key='outro_provider',
            )

        response = admin_client.get(HISTORY_URL)

        # Só os 3 do B2
        assert response.data['count'] == 3

    def test_history_ordering_newest_first(self, admin_client):
        old = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=100,
            fetched_at=timezone.now() - timedelta(hours=5),
        )
        new = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=200,
            fetched_at=timezone.now(),
        )

        response = admin_client.get(HISTORY_URL)

        results = response.data['results']
        assert results[0]['id'] == str(new.id)
        assert results[1]['id'] == str(old.id)