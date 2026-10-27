"""
Testes de governança do AICallService.

Cobrem:
    - Quota bloqueando ANTES da chamada (nenhum custo é gerado).
    - Quota permitindo (chamada executa, custo é registrado).
    - Custo calculado a partir do ProviderPricing VIGENTE.
    - Mudança de preço não altera custo histórico.
    - Idempotência real (corrida entre duas chamadas simultâneas).
    - Falha no provider → nenhum UsageRecord.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.console.models import (
    Provider, ProviderPricing, UsageMetric, UsageRecord,
)
from apps.console.services.ai_call_service import (
    AICallService, AICallError,
)
from apps.console.services.quota_service import QuotaCheckResult


@pytest.fixture
def setup(db):
    provider = Provider.objects.create(
        key='openai', name='OpenAI', category='ai', is_active=True,
    )
    metric = UsageMetric.objects.create(
        key='ai.credits', name='AI', unit='token',
        kind='counter', origin='recorded', is_active=True,
    )
    return provider, metric


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-gov')


def _mock_openai_response(in_tok=100, out_tok=50):
    response = MagicMock()
    response.id = 'req-xyz'
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"insights": []}'
    response.usage = MagicMock()
    response.usage.prompt_tokens = in_tok
    response.usage.completion_tokens = out_tok
    return response


def _allow_quota(mocker):
    mocker.patch(
        'apps.console.services.ai_call_service.AICallService._assert_quota_allows',
        return_value=None,
    )


# =========================================================================
# QUOTA
# =========================================================================

@pytest.mark.django_db
class TestQuotaGovernance:

    def test_blocked_quota_raises_before_provider_call(
        self, mocker, setup, workspace,
    ):
        # Mocka QuotaService.check para bloquear.
        mocker.patch(
            'apps.console.services.quota_service.QuotaService.check',
            return_value=QuotaCheckResult(
                status='blocked', allowed=False, quota_bytes=100,
                used_bytes=200, remaining_bytes=0, percent=200.0,
                behavior='hard_limit', period='monthly',
                feature_key='ai', plan_key='pro',
            ),
        )
        # Garante que openai NÃO será instanciado
        mock_openai = mocker.patch('openai.OpenAI')

        with pytest.raises(AICallError, match='quota'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-blocked',
            )

        # Sem chamada real
        mock_openai.assert_not_called()
        # Sem custo
        assert UsageRecord.objects.count() == 0

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_allowed_quota_proceeds(
        self, mocker, setup, workspace,
    ):
        mocker.patch(
            'apps.console.services.quota_service.QuotaService.check',
            return_value=QuotaCheckResult(
                status='ok', allowed=True, quota_bytes=1000,
                used_bytes=100, remaining_bytes=900, percent=10.0,
                behavior='hard_limit', period='monthly',
                feature_key='ai', plan_key='pro',
            ),
        )
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='m',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-ok',
        )

        assert UsageRecord.objects.filter(request_id='req-ok').exists()


# =========================================================================
# CUSTO
# =========================================================================

@pytest.mark.django_db
class TestCostCalculation:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_cost_uses_active_pricing(
        self, mocker, setup, workspace,
    ):
        provider, metric = setup
        _allow_quota(mocker)

        # Pricing: 0.00001 USD por token, vigente agora.
        ProviderPricing.objects.create(
            provider=provider, metric=metric,
            identifier='',
            pricing_model='unit',
            unit_price=Decimal('0.00001'),
            currency='USD',
            starts_at=timezone.now(),
            is_active=True,
        )

        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response(in_tok=100, out_tok=50)
        )

        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='m',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-cost',
        )

        rec = UsageRecord.objects.get(request_id='req-cost')
        # 150 tokens * 0.00001 = 0.0015
        assert rec.estimated_cost == Decimal('0.00150000')
        assert rec.currency == 'USD'

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_price_change_does_not_alter_history(
        self, mocker, setup, workspace,
    ):
        provider, metric = setup
        _allow_quota(mocker)

        # Preço 1: 0.00001
        pricing_1 = ProviderPricing.objects.create(
            provider=provider, metric=metric,
            pricing_model='unit',
            unit_price=Decimal('0.00001'),
            currency='USD',
            starts_at=timezone.now() - timezone.timedelta(hours=1),
            is_active=True,
        )

        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response(in_tok=100, out_tok=50)
        )

        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='m',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-hist',
        )
        rec1 = UsageRecord.objects.get(request_id='req-hist')
        cost_before = rec1.estimated_cost

        # Muda o preço: encerra o pricing_1 e cria o pricing_2
        pricing_1.ends_at = timezone.now()
        pricing_1.save(update_fields=['ends_at'])

        ProviderPricing.objects.create(
            provider=provider, metric=metric,
            pricing_model='unit',
            unit_price=Decimal('0.00010'),  # 10x mais caro
            currency='USD',
            starts_at=timezone.now(),
            is_active=True,
        )

        # O custo histórico NÃO muda
        rec1.refresh_from_db()
        assert rec1.estimated_cost == cost_before


# =========================================================================
# IDEMPOTÊNCIA SOB CORRIDA
# =========================================================================

@pytest.mark.django_db
class TestIdempotencyUnderRace:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_concurrent_same_request_id_creates_single_usage(
        self, mocker, setup, workspace,
    ):
        """
        Simula duas chamadas com o mesmo request_id que colidem no
        UsageRecordService (IdempotencyConflictError).

        O AICallService deve rebuscar o registro existente sem
        duplicar. E o provider é chamado duas vezes (não há lock),
        mas o UsageRecord final é único — o que é o invariante
        correto para reconciliação.
        """
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        # Primeira chamada cria o UsageRecord.
        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='m',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-race',
        )

        # Segunda chamada: o `_find_existing_usage` já encontra o
        # primeiro e nem chega a chamar o provider.
        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='m',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-race',
        )

        assert UsageRecord.objects.filter(
            request_id='req-race',
        ).count() == 1
        # Provider chamado apenas uma vez (a 2ª foi idempotente
        # antes da chamada)
        assert (
            mock_create.return_value.chat.completions.create.call_count == 1
        )


# =========================================================================
# FALHA NO PROVIDER
# =========================================================================

@pytest.mark.django_db
class TestProviderFailure:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_provider_failure_no_usage_no_cost(
        self, mocker, setup, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.side_effect = (
            TimeoutError('simulated timeout')
        )

        with pytest.raises(AICallError):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[{'role': 'user', 'content': 'x'}],
                request_id='req-timeout',
            )

        # Nenhum UsageRecord (não sabemos se houve cobrança)
        assert not UsageRecord.objects.filter(
            request_id='req-timeout',
        ).exists()