"""
Teste de integração OPT-IN do BackblazeB2UsageService.

Este teste NÃO roda por padrão. Ele só roda quando `B2_INTEGRATION=1`
está definido no ambiente. Sem isso, é pulado.

COMPORTAMENTO
-------------
    B2_INTEGRATION != '1'                        → skip
    B2_INTEGRATION == '1' + credenciais ausentes → FAIL (não skip)
    B2_INTEGRATION == '1' + credenciais válidas  → roda contra a API real

O fail (em vez de skip) é intencional: se você pediu explicitamente o
teste de integração, uma configuração ausente é um erro que precisa ser
visto — não escondido.

OPERAÇÕES
---------
    Somente leitura.
    - `fetch()` chama a API do B2 via boto3 (`list_objects_v2`).
    - `sync()` chama `fetch()` e persiste o snapshot no banco de testes
      (SQLite em memória durante o pytest).

Nenhuma operação de escrita é feita no B2. Não há upload, delete, nem
`put_object`. O único efeito colateral é local ao banco de teste.

COMO RODAR
----------
    # Só os testes de integração
    B2_INTEGRATION=1 pytest -m integration

    # Todos os demais (integração pulada)
    pytest -m "not integration"

    # Ou sem o marker
    pytest apps/console/tests/ -v

NOTA SOBRE O QUE É VALIDADO
---------------------------
Este teste NÃO assume valores específicos do B2. Não há garantia de
que um bucket esteja vazio ou cheio. O que é validado é apenas:
    - A chamada funciona e devolve `ok=True`.
    - O payload tem as chaves esperadas.
    - Os tipos das métricas estão corretos quando presentes.
    - `sync()` persiste corretamente o snapshot.

Asserções sobre valores numéricos específicos ficam fora — elas
seriam frágeis e dependeriam do estado real do bucket.
"""

import os
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.console.models import StorageProviderSnapshot
from apps.console.services.b2_usage_service import (
    BackblazeB2UsageService,
    PROVIDER_KEY_B2,
    PAYLOAD_VERSION,
)


# =========================================================================
# GUARD DE OPT-IN
# =========================================================================

_INTEGRATION_ENABLED = os.getenv('B2_INTEGRATION') == '1'


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _INTEGRATION_ENABLED,
        reason=(
            'Teste de integração real do B2 desabilitado. '
            'Defina B2_INTEGRATION=1 para rodar.'
        ),
    ),
]


# =========================================================================
# VALIDAÇÃO DE CREDENCIAIS E BUCKET
# =========================================================================

def _assert_credentials_configured():
    """
    Verifica que as credenciais e o bucket estão configurados.

    Chamado em cada teste quando B2_INTEGRATION=1. Se algo estiver
    faltando, LEVANTA AssertionError — o teste falha, não pula.
    Isso é intencional: foi pedido o teste de integração, uma
    configuração ausente é um erro que precisa ser visto.
    """
    assert BackblazeB2UsageService.is_available(), (
        'B2_INTEGRATION=1 mas credenciais ausentes. Defina '
        'B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME, '
        'B2_ENDPOINT e B2_REGION no .env.'
    )

    bucket = getattr(settings, 'B2_BUCKET_NAME', None)
    assert bucket, (
        'B2_INTEGRATION=1 mas settings.B2_BUCKET_NAME está vazio.'
    )
    assert isinstance(bucket, str), (
        f'settings.B2_BUCKET_NAME deveria ser string, '
        f'recebido {type(bucket).__name__}.'
    )


# =========================================================================
# IS_AVAILABLE — verificação de configuração real
# =========================================================================

class TestB2IntegrationAvailability:

    def test_is_available_returns_true(self):
        """
        Se B2_INTEGRATION=1, a configuração do ambiente deve estar
        completa. Se `is_available()` devolver False, é bug de
        configuração — o teste falha.
        """
        _assert_credentials_configured()
        assert BackblazeB2UsageService.is_available() is True

    def test_bucket_name_is_set(self):
        """O bucket name deve estar preenchido em settings."""
        _assert_credentials_configured()
        bucket = settings.B2_BUCKET_NAME
        assert isinstance(bucket, str)
        assert len(bucket) > 0


# =========================================================================
# FETCH — contra a API real
# =========================================================================

class TestB2IntegrationFetch:

    def test_fetch_returns_ok(self):
        """
        A chamada real à API do B2 deve retornar `ok=True`.

        Se o B2 estiver inacessível ou as credenciais estiverem
        erradas, o teste falha — porque a intenção de rodar a
        integração foi explícita.
        """
        _assert_credentials_configured()

        result = BackblazeB2UsageService.fetch()

        assert result['ok'] is True, (
            f'Chamada real ao B2 falhou: {result["error"]}'
        )
        assert result['error'] is None
        assert isinstance(result['payload'], dict)

    def test_fetch_payload_has_expected_keys(self):
        """
        O payload deve ter as chaves que o serviço produz.
        Não asserção sobre valores — só sobre a estrutura.
        """
        _assert_credentials_configured()

        result = BackblazeB2UsageService.fetch()
        assert result['ok'] is True

        payload = result['payload']
        expected_keys = {
            'payload_version',
            'bucket_name',
            'endpoint',
            'region',
            'total_bytes',
            'file_count',
            'truncated',
        }
        assert expected_keys.issubset(payload.keys())

    def test_fetch_payload_version_is_current(self):
        """O payload_version deve ser o que o serviço define."""
        _assert_credentials_configured()

        result = BackblazeB2UsageService.fetch()
        assert result['ok'] is True
        assert result['payload']['payload_version'] == PAYLOAD_VERSION

    def test_fetch_payload_types_are_correct(self):
        """
        Valida os TIPOS quando os campos estão presentes.

        Não presume valores — só verifica coerência de tipo:
            - total_bytes: int >= 0
            - file_count: int >= 0
            - truncated: bool
            - bucket_name: string não vazia
        """
        _assert_credentials_configured()

        result = BackblazeB2UsageService.fetch()
        assert result['ok'] is True

        payload = result['payload']

        total_bytes = payload['total_bytes']
        assert isinstance(total_bytes, int)
        assert total_bytes >= 0

        file_count = payload['file_count']
        assert isinstance(file_count, int)
        assert file_count >= 0

        truncated = payload['truncated']
        assert isinstance(truncated, bool)

        bucket_name = payload['bucket_name']
        assert isinstance(bucket_name, str)
        assert len(bucket_name) > 0

    def test_fetch_payload_bucket_matches_settings(self):
        """
        O bucket reportado pelo payload deve ser o mesmo bucket
        configurado em settings. Isso é o que a sua precaução
        pediu: validar que estamos olhando o bucket esperado.
        """
        _assert_credentials_configured()

        result = BackblazeB2UsageService.fetch()
        assert result['ok'] is True
        assert result['payload']['bucket_name'] == settings.B2_BUCKET_NAME


# =========================================================================
# SYNC — persiste o snapshot no banco de teste
# =========================================================================

@pytest.mark.django_db
class TestB2IntegrationSync:

    def test_sync_persists_ok_snapshot(self):
        """
        `sync()` deve persistir um snapshot com `status='ok'` e
        `provider_key=backblaze_b2`.

        O snapshot é persistido no banco de teste (SQLite em memória),
        não no B2. Nenhuma escrita é feita no bucket.
        """
        _assert_credentials_configured()

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot is not None
        assert snapshot.provider_key == PROVIDER_KEY_B2
        assert snapshot.status == StorageProviderSnapshot.STATUS_OK
        assert snapshot.fetched_at is not None

    def test_sync_persists_storage_usage_bytes(self):
        """
        O snapshot persistido deve ter `storage_usage_bytes`
        preenchido e compatível com o payload.
        """
        _assert_credentials_configured()

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_OK
        # Deve ser um inteiro não-negativo — o valor exato depende do
        # estado do bucket, e não é presumido pelo teste.
        assert isinstance(snapshot.storage_usage_bytes, int)
        assert snapshot.storage_usage_bytes >= 0

    def test_sync_persists_raw_payload(self):
        """
        O `raw_payload` deve estar presente com as chaves esperadas.
        """
        _assert_credentials_configured()

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_OK
        assert isinstance(snapshot.raw_payload, dict)

        payload = snapshot.raw_payload
        assert payload['bucket_name'] == settings.B2_BUCKET_NAME
        assert payload['payload_version'] == PAYLOAD_VERSION

    def test_sync_does_not_fill_cloudinary_fields(self):
        """
        Os campos específicos do Cloudinary devem permanecer NULL,
        porque o B2 não tem equivalentes.
        """
        _assert_credentials_configured()

        snapshot = BackblazeB2UsageService.sync()

        assert snapshot.status == StorageProviderSnapshot.STATUS_OK
        assert snapshot.plan_name == ''
        assert snapshot.credits_usage is None
        assert snapshot.credits_limit is None
        assert snapshot.credits_used_percent is None
        assert snapshot.bandwidth_usage_bytes is None
        assert snapshot.transformations_usage is None
        assert snapshot.objects_count is None
        assert snapshot.media_limits is None

    def test_sync_is_append_only_against_real_b2(self):
        """
        Cada chamada de `sync()` cria uma linha nova. Verifica
        contra a API real que o modelo não faz upsert.
        """
        _assert_credentials_configured()

        before = StorageProviderSnapshot.objects.filter(
            provider_key=PROVIDER_KEY_B2,
        ).count()

        s1 = BackblazeB2UsageService.sync()
        s2 = BackblazeB2UsageService.sync()

        after = StorageProviderSnapshot.objects.filter(
            provider_key=PROVIDER_KEY_B2,
        ).count()

        assert after == before + 2
        assert s1.id != s2.id