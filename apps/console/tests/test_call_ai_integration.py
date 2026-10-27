"""
Teste de integração OPT-IN do AICallService.

Roda apenas com `OPENAI_INTEGRATION=1`. Sem isso, skip.
Com a flag ativa, credenciais ausentes FAILAM (não skipam) — mesma
postura de `test_b2_usage_service_integration.py`.

Nenhuma operação é escrita no provider. A chamada é read-only do
ponto de vista do provider (apenas consome tokens cobrados).

ATENÇÃO: este teste CONSOME TOKENS REAIS. Use um modelo barato
e uma mensagem curta. Não rode em CI sem intenção.
"""

import os
import pytest
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from apps.console.models import (
    Provider, UsageMetric, UsageRecord, ProviderLog,
)
from apps.console.services.ai_call_service import AICallService, AICallError


_INTEGRATION_ENABLED = os.getenv('OPENAI_INTEGRATION') == '1'


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _INTEGRATION_ENABLED,
        reason='OPENAI_INTEGRATION não habilitado.',
    ),
]


def _assert_config_ok():
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    assert api_key, (
        'OPENAI_INTEGRATION=1 mas OPENAI_API_KEY não configurada. '
        'Defina a env var antes de rodar a integração.'
    )


@pytest.fixture
def setup_console(db):
    _assert_config_ok()
    provider, _ = Provider.objects.get_or_create(
        key='openai',
        defaults={'name': 'OpenAI', 'category': 'ai', 'is_active': True},
    )
    metric, _ = UsageMetric.objects.get_or_create(
        key='ai.credits',
        defaults={
            'name': 'AI Credits', 'unit': 'token',
            'kind': 'counter', 'origin': 'recorded',
        },
    )
    return provider, metric


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS-Int', slug='ws-int-real')


@pytest.mark.django_db
class TestRealOpenAI:

    def test_real_call_returns_tokens_and_usage(
        self, mocker, setup_console, workspace,
    ):
        # Força quota como permitida (workspace sem plano configurado
        # retornaria 'unconfigured', que é allowed=True por padrão).
        result = AICallService.call(
            workspace=workspace,
            operation='intelligence.analysis',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[
                {
                    'role': 'user',
                    'content': (
                        'Responda apenas com JSON: {"insights": []}. '
                        'Nada além disso.'
                    ),
                },
            ],
            request_id=f'integration-{timezone.now().timestamp()}',
        )

        assert result['raw_content']
        assert result['input_tokens'] > 0
        assert result['output_tokens'] > 0
        assert result['usage_record_id'] is not None

        rec = UsageRecord.objects.get(id=result['usage_record_id'])
        assert rec.quantity > 0
        assert rec.currency  # custo registrado ou ao menos moeda

    def test_real_call_creates_provider_log(
        self, setup_console, workspace,
    ):
        result = AICallService.call(
            workspace=workspace,
            operation='integration.probe',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'diga "ok"'}],
            request_id=f'integration-log-{timezone.now().timestamp()}',
        )

        log = ProviderLog.objects.filter(
            request_id=result['provider_request_id'] or '',
        ).first() or ProviderLog.objects.first()
        assert log is not None
        assert log.status == 'success'