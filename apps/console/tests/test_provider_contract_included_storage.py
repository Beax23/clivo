"""
Testes do campo `ProviderContract.included_storage_bytes`.

Contexto:
    O teto operacional de armazenamento do contrato com o Backblaze B2
    é cadastrado MANUALMENTE. A API S3-compatible do B2 não expõe o
    "Daily Storage Cap" da conta; ele só existe no console web do B2,
    em "Caps & Alerts".

    Este teste valida:
        - O campo é aceito como None (teto não cadastrado).
        - O campo é aceito como 0 (teto zero, cadastrado explicitamente).
        - O campo é aceito como inteiro positivo.
        - O campo rejeita valores negativos.
        - `included_storage_display` reflete corretamente cada caso.
        - A API de leitura expõe `included_storage_bytes` e
          `included_storage_display`.
        - A API de escrita aceita atualizar o valor via PATCH.
        - NULL não é confundido com "ilimitado".
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.console.models import (
    ConsoleMembership,
    Provider,
    ProviderContract,
)


User = get_user_model()

PROVIDER_CONTRACTS_URL = '/api/console/contracts/'


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def console_admin(db):
    user = User.objects.create_user(
        email='admin-contract@example.com',
        password='x',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    return user


@pytest.fixture
def admin_client(console_admin):
    client = APIClient()
    client.force_authenticate(user=console_admin)
    return client


@pytest.fixture
def provider_b2(db):
    return Provider.objects.create(
        key='backblaze_b2',
        name='Backblaze B2',
        category='storage',
        description='',
        is_active=True,
    )


@pytest.fixture
def contract_factory(db, provider_b2):
    def _make(
        name='Clivo Production',
        included_storage_bytes=None,
        is_active=True,
    ):
        return ProviderContract.objects.create(
            provider=provider_b2,
            name=name,
            included_storage_bytes=included_storage_bytes,
            started_at=date(2026, 1, 1),
            is_active=is_active,
        )
    return _make


# =========================================================================
# MODELO
# =========================================================================

@pytest.mark.django_db
class TestProviderContractIncludedStorageModel:

    def test_null_is_accepted(self, contract_factory):
        """NULL = teto não cadastrado. Estado válido."""
        contract = contract_factory(included_storage_bytes=None)
        contract.refresh_from_db()
        assert contract.included_storage_bytes is None

    def test_zero_is_accepted(self, contract_factory):
        """Zero = teto cadastrado, explicitamente zerado."""
        contract = contract_factory(included_storage_bytes=0)
        contract.refresh_from_db()
        assert contract.included_storage_bytes == 0

    def test_positive_integer_is_accepted(self, contract_factory):
        """50 GiB expresso em bytes."""
        fifty_gib = 50 * 1024 ** 3
        contract = contract_factory(included_storage_bytes=fifty_gib)
        contract.refresh_from_db()
        assert contract.included_storage_bytes == fifty_gib

    def test_negative_is_rejected_on_save(self, contract_factory):
        """Valor negativo é rejeitado na validação do modelo."""
        from django.core.exceptions import ValidationError

        contract = ProviderContract(
            provider=Provider.objects.get(key='backblaze_b2'),
            name='Bad',
            included_storage_bytes=-1,
            started_at=date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            contract.save()

    def test_null_is_not_unlimited(self, contract_factory):
        """
        NULL NÃO significa ilimitado. É apenas ausência de dado.

        Este teste é conceitual: confirma que o campo aceita NULL
        e que, no modelo, não há lógica que converta NULL para
        algum valor sentinela de "infinito".
        """
        contract = contract_factory(included_storage_bytes=None)
        contract.refresh_from_db()
        assert contract.included_storage_bytes is None
        # Nenhum valor derivado deve transformar None em algo
        # que pareça "infinito".
        assert not hasattr(contract, 'is_unlimited_storage')


# =========================================================================
# SERIALIZER DE LEITURA
# =========================================================================

@pytest.mark.django_db
class TestProviderContractIncludedStorageSerializerRead:

    def test_display_null_when_none(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=None)
        resp = admin_client.get(f'{PROVIDER_CONTRACTS_URL}{contract.id}/')
        assert resp.status_code == 200
        assert resp.data['included_storage_bytes'] is None
        assert resp.data['included_storage_display'] is None

    def test_display_zero(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=0)
        resp = admin_client.get(f'{PROVIDER_CONTRACTS_URL}{contract.id}/')
        assert resp.status_code == 200
        assert resp.data['included_storage_bytes'] == 0
        assert resp.data['included_storage_display'] == '0 B'

    def test_display_bytes(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=512)
        resp = admin_client.get(f'{PROVIDER_CONTRACTS_URL}{contract.id}/')
        assert resp.status_code == 200
        assert resp.data['included_storage_bytes'] == 512
        assert resp.data['included_storage_display'] == '512.00 B'

    def test_display_gibibyte(self, admin_client, contract_factory):
        fifty_gib = 50 * 1024 ** 3
        contract = contract_factory(included_storage_bytes=fifty_gib)
        resp = admin_client.get(f'{PROVIDER_CONTRACTS_URL}{contract.id}/')
        assert resp.status_code == 200
        assert resp.data['included_storage_bytes'] == fifty_gib
        assert resp.data['included_storage_display'] == '50.00 GB'


# =========================================================================
# SERIALIZER DE ESCRITA
# =========================================================================

@pytest.mark.django_db
class TestProviderContractIncludedStorageSerializerWrite:

    def test_patch_set_value(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=None)
        fifty_gib = 50 * 1024 ** 3

        resp = admin_client.patch(
            f'{PROVIDER_CONTRACTS_URL}{contract.id}/',
            {'included_storage_bytes': fifty_gib},
            format='json',
        )
        assert resp.status_code == 200
        contract.refresh_from_db()
        assert contract.included_storage_bytes == fifty_gib

    def test_patch_clear_value(self, admin_client, contract_factory):
        """
        Enviar `null` explicitamente deve limpar o teto cadastrado.
        Isso é intencional: operador pode decidir que não quer manter
        a informação. Não é o mesmo que "zerar".
        """
        contract = contract_factory(included_storage_bytes=1024)

        resp = admin_client.patch(
            f'{PROVIDER_CONTRACTS_URL}{contract.id}/',
            {'included_storage_bytes': None},
            format='json',
        )
        assert resp.status_code == 200
        contract.refresh_from_db()
        assert contract.included_storage_bytes is None

    def test_patch_zero(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=1024)

        resp = admin_client.patch(
            f'{PROVIDER_CONTRACTS_URL}{contract.id}/',
            {'included_storage_bytes': 0},
            format='json',
        )
        assert resp.status_code == 200
        contract.refresh_from_db()
        assert contract.included_storage_bytes == 0

    def test_negative_is_rejected(self, admin_client, contract_factory):
        contract = contract_factory(included_storage_bytes=None)

        resp = admin_client.patch(
            f'{PROVIDER_CONTRACTS_URL}{contract.id}/',
            {'included_storage_bytes': -1},
            format='json',
        )
        assert resp.status_code == 400

        # O projeto envelopa erros do DRF em {'error': <string>, 'status_code': int}.
        # O nome do campo aparece dentro da string, não como chave de topo.
        # Asserção tolerante: checa o campo no payload, seja como chave
        # de topo (comportamento padrão do DRF) ou dentro do envelope.
        payload_str = str(resp.data)
        assert 'included_storage_bytes' in payload_str

        # Garante que o valor NÃO foi persistido.
        contract.refresh_from_db()
        assert contract.included_storage_bytes is None


# =========================================================================
# HELPERS
# =========================================================================

@pytest.mark.django_db
class TestHumanizeBytes:

    def test_zero(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(0) == '0 B'

    def test_bytes(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(512) == '512.00 B'

    def test_kilobytes(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(1024) == '1.00 KB'

    def test_megabytes(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(1024 * 1024) == '1.00 MB'

    def test_gibibyte(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(1024 ** 3) == '1.00 GB'

    def test_terabyte(self):
        from apps.console.api.serializers.provider_serializers import (
            _humanize_bytes,
        )
        assert _humanize_bytes(1024 ** 4) == '1.00 TB'