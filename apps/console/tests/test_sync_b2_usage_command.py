"""
Testes do management command `sync_b2_usage`.

O command é uma camada fina sobre `BackblazeB2UsageService.sync()`.
Por isso, aqui mockamos `sync()` — não a API do B2. Os testes da API
real estão em `test_b2_usage_service.py` (mock do boto3) e no teste
de integração opt-in.

Estes testes cobrem apenas o comportamento do command:
    - escolha do formato de saída (humano / JSON / quiet)
    - exit code 0 mesmo em falha
    - conteúdo do JSON
    - texto humano para cada status
"""

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.console.models import StorageProviderSnapshot
from apps.console.services.b2_usage_service import PROVIDER_KEY_B2


# =========================================================================
# HELPERS
# =========================================================================

def _make_snapshot(
    status: str = StorageProviderSnapshot.STATUS_OK,
    storage_usage_bytes: int = None,
    raw_payload: dict = None,
    error_message: str = '',
):
    """
    Cria um StorageProviderSnapshot real no banco, para o command
    consumir via `sync()` mockado.

    Não usa mock do modelo — o snapshot é real e é persistido.
    """
    return StorageProviderSnapshot.objects.create(
        provider_key=PROVIDER_KEY_B2,
        status=status,
        raw_payload=raw_payload,
        storage_usage_bytes=storage_usage_bytes,
        error_message=error_message,
        fetched_at=timezone.now(),
    )


# =========================================================================
# OUTPUT HUMANO — SUCESSO
# =========================================================================

@pytest.mark.django_db
class TestCommandHumanOutput:

    def test_success_shows_b2_sincronizado(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=1024,
            raw_payload={
                'bucket_name': 'test-bucket',
                'file_count': 3,
                'total_bytes': 1024,
                'truncated': False,
            },
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        output = out.getvalue()
        assert 'B2 sincronizado' in output
        assert 'test-bucket' in output
        assert '1024' in output
        assert '3' in output  # file_count

    def test_success_shows_snapshot_id(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=500,
            raw_payload={'bucket_name': 'b', 'file_count': 1, 'total_bytes': 500},
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        assert str(snapshot.id) in out.getvalue()

    def test_success_with_truncated_warns(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=100,
            raw_payload={
                'bucket_name': 'b',
                'file_count': 1,
                'total_bytes': 100,
                'truncated': True,
            },
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        assert 'Paginação interrompida' in out.getvalue()


# =========================================================================
# OUTPUT HUMANO — ERRO
# =========================================================================

@pytest.mark.django_db
class TestCommandErrorOutput:

    def test_error_shows_falha_message(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='B2 ClientError NoSuchBucket: bucket does not exist',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        output = out.getvalue()
        assert 'Falha ao consultar o B2' in output
        assert 'NoSuchBucket' in output

    def test_error_does_not_raise(self):
        """
        Regra fundamental: o command NUNCA levanta exceção para o
        chamador, para não poluir logs de cron. Exit code sempre 0.
        """
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='boom',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            # Não deve levantar SystemExit nem nada
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

    def test_error_human_mentions_previous_snapshot(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='fail',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        assert 'snapshot anterior' in out.getvalue().lower()


# =========================================================================
# OUTPUT HUMANO — UNAVAILABLE
# =========================================================================

@pytest.mark.django_db
class TestCommandUnavailableOutput:

    def test_unavailable_shows_warning(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_UNAVAILABLE,
            error_message='B2 não configurado',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', stdout=out)

        output = out.getvalue()
        assert 'não configurado' in output.lower()
        assert 'B2 não configurado' in output


# =========================================================================
# --quiet
# =========================================================================

@pytest.mark.django_db
class TestCommandQuiet:

    def test_quiet_suppresses_output_on_success(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=100,
            raw_payload={'bucket_name': 'b', 'file_count': 1, 'total_bytes': 100},
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--quiet', stdout=out)

        assert out.getvalue() == ''

    def test_quiet_suppresses_output_on_error(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='boom',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--quiet', stdout=out)

        assert out.getvalue() == ''


# =========================================================================
# --json
# =========================================================================

@pytest.mark.django_db
class TestCommandJson:

    def test_json_output_is_valid(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=1024,
            raw_payload={
                'bucket_name': 'test-bucket',
                'file_count': 3,
                'total_bytes': 1024,
                'truncated': False,
            },
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--json', stdout=out)

        data = json.loads(out.getvalue())

        assert data['status'] == 'ok'
        assert data['provider_key'] == PROVIDER_KEY_B2
        assert data['storage_usage_bytes'] == 1024
        assert data['bucket_name'] == 'test-bucket'
        assert data['file_count'] == 3
        assert data['truncated'] is False
        assert data['error_message'] == ''
        assert data['id'] == str(snapshot.id)
        assert 'fetched_at' in data

    def test_json_output_on_error(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_ERROR,
            error_message='AccessDenied',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--json', stdout=out)

        data = json.loads(out.getvalue())

        assert data['status'] == 'error'
        assert data['error_message'] == 'AccessDenied'
        assert data['storage_usage_bytes'] is None
        assert data['bucket_name'] is None
        assert data['file_count'] is None
        assert data['truncated'] is None

    def test_json_output_on_unavailable(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_UNAVAILABLE,
            error_message='B2 não configurado',
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--json', stdout=out)

        data = json.loads(out.getvalue())
        assert data['status'] == 'unavailable'
        assert 'B2 não configurado' in data['error_message']

    def test_json_with_truncated_payload(self):
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=999,
            raw_payload={
                'bucket_name': 'b',
                'file_count': 2,
                'total_bytes': 999,
                'truncated': True,
            },
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--json', stdout=out)

        data = json.loads(out.getvalue())
        assert data['truncated'] is True


# =========================================================================
# PRIORIDADE ENTRE FLAGS
# =========================================================================

@pytest.mark.django_db
class TestCommandFlagPriority:

    def test_json_wins_over_quiet(self):
        """
        Regra do command: se `--json`, imprime JSON — mesmo com
        `--quiet` presente. `--json` é formato explícito; `--quiet`
        é para cron silencioso. `--json` tem prioridade.
        """
        snapshot = _make_snapshot(
            status=StorageProviderSnapshot.STATUS_OK,
            storage_usage_bytes=1,
            raw_payload={'bucket_name': 'b', 'file_count': 1, 'total_bytes': 1},
        )

        with patch(
            'apps.console.management.commands.sync_b2_usage.'
            'BackblazeB2UsageService.sync',
            return_value=snapshot,
        ):
            out = StringIO()
            call_command('sync_b2_usage', '--quiet', '--json', stdout=out)

        output = out.getvalue()
        # Deve ser JSON válido, não vazio
        data = json.loads(output)
        assert data['status'] == 'ok'