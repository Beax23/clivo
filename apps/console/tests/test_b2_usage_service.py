"""
Testes unitários do BackblazeB2UsageService.

Todos usam mock do boto3 — nenhuma chamada de rede real.

O serviço chama `boto3.client(...)` dentro de `fetch()`, então o
mock precisa patchear `boto3.client` no módulo `boto3` em si
(não no módulo do serviço).

O serviço usa `list_object_versions` (não `list_objects_v2`) para
contabilizar TODAS as versões de cada objeto — a B2 cobra por todas
elas, não só pela versão ativa. Os mocks abaixo refletem esse
formato:

    {
        'Versions': [{'Key', 'Size', 'IsLatest'}, ...],
        'DeleteMarkers': [...],
    }

A validação contra a API real do B2 fica em
`test_b2_usage_service_integration.py`, que só roda com `B2_INTEGRATION=1`.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)
from django.test import override_settings
from django.utils import timezone

from apps.console.models import StorageProviderSnapshot
from apps.console.services.b2_usage_service import (
    BackblazeB2UsageService,
    PROVIDER_KEY_B2,
    PAYLOAD_VERSION,
)


# =========================================================================
# HELPERS
# =========================================================================

B2_SETTINGS = dict(
    B2_CONFIGURED=True,
    B2_KEY_ID='test-key',
    B2_APPLICATION_KEY='test-app-key',
    B2_BUCKET_NAME='test-bucket',
    B2_ENDPOINT='https://s3.us-east-005.backblazeb2.com',
    B2_REGION='us-east-005',
)


def _make_client_error(code: str, message: str) -> ClientError:
    """Constrói um ClientError com payload mínimo."""
    return ClientError(
        {'Error': {'Code': code, 'Message': message}},
        operation_name='ListObjectVersions',
    )


def _make_paginator(versions_per_page, delete_markers_per_page=None):
    """
    Cria um mock de paginador do boto3 que devolve páginas no
    formato de `list_object_versions`:

        {'Versions': [...], 'DeleteMarkers': [...]}

    `versions_per_page`: lista de listas de dicts. Cada item da
    lista externa é uma página; cada item da interna é uma versão
    de objeto (`{'Key': ..., 'Size': int, 'IsLatest': bool}`).

    `delete_markers_per_page`: opcional. Lista de listas no mesmo
    formato. Se omitido, cada página terá `DeleteMarkers=[]`.
    """
    if delete_markers_per_page is None:
        delete_markers_per_page = [
            [] for _ in versions_per_page
        ]

    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            'Versions': page,
            'DeleteMarkers': markers,
        }
        for page, markers in zip(
            versions_per_page, delete_markers_per_page,
        )
    ]
    return paginator


def _make_client_with_paginator(paginator):
    """Cria um mock de client S3 cujo `get_paginator` devolve o paginador."""
    client = MagicMock()
    client.get_paginator.return_value = paginator
    return client


def _v(key='a.txt', size=100, is_latest=True):
    """Helper para criar um item de versão."""
    return {'Key': key, 'Size': size, 'IsLatest': is_latest}


# =========================================================================
# IS_AVAILABLE
# =========================================================================

class TestIsAvailable:

    @override_settings(B2_CONFIGURED=True)
    def test_true_when_flag_true(self):
        assert BackblazeB2UsageService.is_available() is True

    @override_settings(B2_CONFIGURED=False)
    def test_false_when_flag_false(self):
        assert BackblazeB2UsageService.is_available() is False

    def test_fallback_checks_env_when_flag_absent(self, settings):
        """
        Sem a flag, o serviço faz fallback para `os.getenv`.

        Aqui manipulamos `os.environ` diretamente porque o fallback
        lê de env, não de settings.
        """
        import os

        settings.B2_CONFIGURED = None
        # `hasattr` retorna True mesmo se for None, então o teste
        # precisa deletar o atributo do settings para simular ausência.
        del settings.B2_CONFIGURED

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv('B2_KEY_ID', 'x')
            mp.setenv('B2_APPLICATION_KEY', 'y')
            mp.setenv('B2_BUCKET_NAME', 'z')
            mp.setenv('B2_ENDPOINT', 'https://example.com')
            mp.setenv('B2_REGION', 'us-east-005')
            assert BackblazeB2UsageService.is_available() is True

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('B2_KEY_ID', raising=False)
            assert BackblazeB2UsageService.is_available() is False

        # Restaura para os outros testes não serem afetados
        settings.B2_CONFIGURED = True


# =========================================================================
# FETCH
# =========================================================================

class TestFetch:

    @override_settings(B2_CONFIGURED=False)
    def test_returns_not_ok_when_unavailable(self):
        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert result['payload'] is None
        assert 'Credenciais' in result['error']

    @override_settings(**B2_SETTINGS)
    def test_returns_ok_with_empty_bucket(self, mocker):
        paginator = _make_paginator([[]])  # uma página vazia
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['error'] is None
        payload = result['payload']
        assert payload['total_bytes'] == 0
        assert payload['file_count'] == 0
        assert payload['active_versions_count'] == 0
        assert payload['total_versions_count'] == 0
        assert payload['delete_markers_count'] == 0
        assert payload['truncated'] is False
        assert payload['bucket_name'] == 'test-bucket'
        assert payload['payload_version'] == PAYLOAD_VERSION

    @override_settings(**B2_SETTINGS)
    def test_returns_ok_with_single_object(self, mocker):
        paginator = _make_paginator([
            [_v(key='a.txt', size=100, is_latest=True)],
        ])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['payload']['total_bytes'] == 100
        assert result['payload']['file_count'] == 1
        assert result['payload']['active_versions_count'] == 1
        assert result['payload']['total_versions_count'] == 1

    @override_settings(**B2_SETTINGS)
    def test_returns_ok_with_multiple_pages(self, mocker):
        """Soma correta em múltiplas páginas de paginação."""
        paginator = _make_paginator([
            [
                _v(key='a.txt', size=100),
                _v(key='b.txt', size=250),
            ],
            [
                _v(key='c.txt', size=75),
            ],
        ])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['payload']['total_bytes'] == 425
        assert result['payload']['file_count'] == 3
        assert result['payload']['total_versions_count'] == 3

    @override_settings(**B2_SETTINGS)
    def test_ignores_objects_without_size(self, mocker):
        """Objeto sem `Size` (ou não-int) não entra na soma nem na contagem."""
        paginator = _make_paginator([
            [
                _v(key='a.txt', size=100),
                {'Key': 'no-size.txt', 'IsLatest': True},          # sem Size
                {'Key': 'b.txt', 'Size': 'invalid', 'IsLatest': True},  # Size inválido
            ],
        ])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['payload']['total_bytes'] == 100
        assert result['payload']['file_count'] == 1
        assert result['payload']['total_versions_count'] == 1

    @override_settings(**B2_SETTINGS)
    def test_counts_delete_markers(self, mocker):
        """
        DeleteMarkers são contados para auditoria, mas NÃO somam
        bytes (não têm `Size`).
        """
        paginator = _make_paginator(
            versions_per_page=[
                [_v(key='a.txt', size=100)],
            ],
            delete_markers_per_page=[
                [{'Key': 'deleted.txt'}],
            ],
        )
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['payload']['total_bytes'] == 100
        assert result['payload']['delete_markers_count'] == 1

    @override_settings(**B2_SETTINGS)
    def test_counts_old_versions(self, mocker):
        """
        Versões antigas (`IsLatest=False`) entram em `total_bytes` e
        em `total_versions_count`, mas NÃO em `active_versions_count`.
        """
        paginator = _make_paginator([
            [
                _v(key='a.txt', size=100, is_latest=True),
                _v(key='a.txt', size=100, is_latest=False),
                _v(key='a.txt', size=100, is_latest=False),
            ],
        ])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True
        assert result['payload']['total_bytes'] == 300
        assert result['payload']['active_versions_count'] == 1
        assert result['payload']['total_versions_count'] == 3

    @override_settings(**B2_SETTINGS)
    def test_handles_client_error(self, mocker):
        paginator = MagicMock()
        paginator.paginate.side_effect = _make_client_error(
            'NoSuchBucket', 'The bucket does not exist'
        )
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert result['payload'] is None
        assert 'NoSuchBucket' in result['error']
        assert 'The bucket does not exist' in result['error']

    @override_settings(**B2_SETTINGS)
    def test_handles_endpoint_connection_error(self, mocker):
        paginator = MagicMock()
        paginator.paginate.side_effect = EndpointConnectionError(
            endpoint_url='https://example.com'
        )
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert 'inacessível' in result['error'].lower()

    @override_settings(**B2_SETTINGS)
    def test_handles_botocore_error(self, mocker):
        paginator = MagicMock()
        paginator.paginate.side_effect = BotoCoreError()
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert 'SDK' in result['error']

    @override_settings(**B2_SETTINGS)
    def test_handles_unexpected_error(self, mocker):
        paginator = MagicMock()
        paginator.paginate.side_effect = ValueError('boom')
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert 'ValueError' in result['error']

    @override_settings(**B2_SETTINGS)
    def test_handles_client_creation_failure(self, mocker):
        mocker.patch('boto3.client', side_effect=Exception('no client'))

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is False
        assert 'no client' in result['error']


# =========================================================================
# SYNC
# =========================================================================

@pytest.mark.django_db
class TestSync:

    @override_settings(B2_CONFIGURED=False)
    def test_creates_unavailable_snapshot(self):
        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_UNAVAILABLE
        assert snapshot.provider_key == PROVIDER_KEY_B2
        assert 'B2 não configurado' in snapshot.error_message
        assert snapshot.storage_usage_bytes is None
        assert snapshot.raw_payload is None

    @override_settings(**B2_SETTINGS)
    def test_creates_ok_snapshot(self, mocker):
        paginator = _make_paginator([
            [
                _v(key='a.txt', size=1000),
                _v(key='b.txt', size=2000),
            ],
        ])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_OK
        assert snapshot.provider_key == PROVIDER_KEY_B2
        assert snapshot.storage_usage_bytes == 3000
        assert snapshot.raw_payload['total_bytes'] == 3000
        assert snapshot.raw_payload['file_count'] == 2
        assert snapshot.raw_payload['bucket_name'] == 'test-bucket'
        assert snapshot.raw_payload['payload_version'] == PAYLOAD_VERSION
        assert snapshot.error_message == ''

    @override_settings(**B2_SETTINGS)
    def test_creates_error_snapshot_on_fetch_failure(self, mocker):
        paginator = MagicMock()
        paginator.paginate.side_effect = _make_client_error(
            'AccessDenied', 'Access Denied'
        )
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_ERROR
        assert 'AccessDenied' in snapshot.error_message
        assert snapshot.storage_usage_bytes is None
        assert snapshot.raw_payload is None

    @override_settings(**B2_SETTINGS)
    def test_campos_especificos_de_cloudinary_ficam_null(self, mocker):
        """
        Regra: no B2, todos os campos específicos do Cloudinary
        (credits_*, bandwidth_*, transformations_*, plan_name, media_limits,
        rate_limit_*, objects_count, resources_count, derived_resources_count)
        ficam NULL. Nunca preenchidos.
        """
        paginator = _make_paginator([[_v(key='a.txt', size=100)]])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.plan_name == ''
        assert snapshot.storage_credits_usage is None
        assert snapshot.bandwidth_usage_bytes is None
        assert snapshot.bandwidth_credits_usage is None
        assert snapshot.transformations_usage is None
        assert snapshot.transformations_credits_usage is None
        assert snapshot.credits_usage is None
        assert snapshot.credits_limit is None
        assert snapshot.credits_used_percent is None
        assert snapshot.objects_count is None
        assert snapshot.resources_count is None
        assert snapshot.derived_resources_count is None
        assert snapshot.media_limits is None
        assert snapshot.rate_limit_remaining is None
        assert snapshot.rate_limit_reset_at is None

    @override_settings(**B2_SETTINGS)
    def test_sync_never_raises_on_failure(self, mocker):
        """
        Regra fundamental: `sync()` NUNCA levanta exceção. O management
        command precisa terminar com código 0 mesmo em falha da API.
        """
        mocker.patch('boto3.client', side_effect=RuntimeError('anything'))

        # Não deve levantar
        snapshot = BackblazeB2UsageService.sync()
        assert snapshot.status == StorageProviderSnapshot.STATUS_ERROR

    @override_settings(**B2_SETTINGS)
    def test_failure_preserves_previous_ok_snapshot(self, mocker):
        """
        Regra: uma falha NÃO apaga o último snapshot válido.
        Dois snapshots coexistem; a leitura usa o último 'ok'.
        """
        # 1ª chamada: sucesso
        paginator = _make_paginator([[_v(key='a.txt', size=500)]])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)
        ok_snapshot = BackblazeB2UsageService.sync()

        # 2ª chamada: falha
        paginator_fail = MagicMock()
        paginator_fail.paginate.side_effect = RuntimeError('boom')
        client_fail = _make_client_with_paginator(paginator_fail)
        mocker.patch('boto3.client', return_value=client_fail)
        error_snapshot = BackblazeB2UsageService.sync()

        assert ok_snapshot.status == StorageProviderSnapshot.STATUS_OK
        assert error_snapshot.status == StorageProviderSnapshot.STATUS_ERROR
        assert ok_snapshot.id != error_snapshot.id

        # Último 'ok' continua existindo
        latest_ok = (
            StorageProviderSnapshot.objects
            .filter(
                provider_key=PROVIDER_KEY_B2,
                status=StorageProviderSnapshot.STATUS_OK,
            )
            .order_by('-fetched_at')
            .first()
        )
        assert latest_ok is not None
        assert latest_ok.id == ok_snapshot.id

        # O último snapshot (qualquer status) é o de erro
        latest = (
            StorageProviderSnapshot.objects
            .filter(provider_key=PROVIDER_KEY_B2)
            .order_by('-fetched_at')
            .first()
        )
        assert latest.id == error_snapshot.id

    @override_settings(**B2_SETTINGS)
    def test_sync_is_append_only(self, mocker):
        """
        Cada `sync()` cria uma linha NOVA. Nunca sobrescreve.
        Verifica que após N chamadas, existem N snapshots.
        """
        paginator = _make_paginator([[_v(key='a.txt', size=100)]])
        client = _make_client_with_paginator(paginator)
        mocker.patch('boto3.client', return_value=client)

        before = StorageProviderSnapshot.objects.filter(
            provider_key=PROVIDER_KEY_B2,
        ).count()

        for _ in range(3):
            BackblazeB2UsageService.sync()

        after = StorageProviderSnapshot.objects.filter(
            provider_key=PROVIDER_KEY_B2,
        ).count()

        assert after == before + 3