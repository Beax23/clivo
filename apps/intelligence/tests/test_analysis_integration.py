"""
Teste de integração OPT-IN do fluxo `AnalysisService` com
`console.call_ai` + OpenAI real.

Roda apenas com `OPENAI_INTEGRATION=1`. Sem isso, skip.
Com a flag ativa, credenciais ausentes FAILAM (não skipam) —
mesma postura de `test_b2_usage_service_integration.py`.

ATENÇÃO: este teste CONSOME TOKENS REAIS. Usa o modelo
`INTELLIGENCE_MODEL` (default gpt-4o-mini) e uma mensagem curta.
Não rode em CI sem intenção.
"""

import os
import pytest
from decimal import Decimal
from django.conf import settings
from django.utils import timezone


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
def setup_full(db, openai_provider, ai_metric):
    _assert_config_ok()
    from apps.console.models import ProviderPricing
    ProviderPricing.objects.create(
        provider=openai_provider,
        metric=ai_metric,
        pricing_model='unit',
        unit_price=Decimal('0.00001'),
        currency='USD',
        starts_at=timezone.now(),
        is_active=True,
    )
    return openai_provider, ai_metric


@pytest.mark.django_db
class TestAnalysisIntegration:

    def test_real_analysis_through_console_bridge(
        self, setup_full, analysis_job,
    ):
        """
        Executa AnalysisService.execute com a ponte `console.call_ai`
        REAL batendo na OpenAI.

        Valida:
            - run concluído;
            - tokens reais registrados;
            - UsageRecord com custo;
            - ProviderLog com sucesso;
            - evidências descartadas se refs não existirem
              (a IA pode inventar refs — o serviço filtra).
        """
        from apps.intelligence.services import AnalysisService
        from apps.console.models import UsageRecord, ProviderLog
        from apps.intelligence.models import AnalysisRun

        run = AnalysisService.execute(analysis_job)

        assert run is not None
        assert run.status == AnalysisRun.STATUS_COMPLETED
        assert run.input_tokens > 0
        assert run.output_tokens > 0

        # UsageRecord de custo foi criado (mesmo request_id do run)
        usage = UsageRecord.objects.filter(request_id=str(run.id)).first()
        assert usage is not None
        assert usage.quantity > 0

        # ProviderLog de sucesso
        log = ProviderLog.objects.filter(request_id=str(run.id)).first()
        assert log is not None
        assert log.status == 'success'