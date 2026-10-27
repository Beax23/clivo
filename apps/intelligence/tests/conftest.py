"""
Fixtures do app `intelligence`.

Cobre o mínimo necessário para:
    - testes unitários de AnalysisService, IngestService, TagService,
      CostAllocationService, StalenessService, ContainerService;
    - teste de integração ponta a ponta (`test_full_flow.py`);
    - teste opt-in contra OpenAI real (`test_analysis_integration.py`).

Não cria workspace com plano completo nem governança: os testes de
autorização ficam em `apps/workspaces` e `apps/console`, fora daqui.
Quando um teste precisa de quota permitida, ele mocka
`console.public.is_ai_execution_allowed` explicitamente — não
depende de um plano configurado.
"""

import pytest
from django.utils import timezone
from decimal import Decimal


# =========================================================================
# WORKSPACE
# =========================================================================

@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS Intel', slug='ws-intel')


@pytest.fixture
def workspace_other(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS Intel B', slug='ws-intel-b')


# =========================================================================
# CLIENTE
# =========================================================================

@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace,
        name='Cliente Intel',
        email='cliente-intel@example.com',
        public_code='CLI-INTEL1',
    )


@pytest.fixture
def client_other(db, workspace_other):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace_other,
        name='Cliente Outro',
        email='cliente-outro@example.com',
        public_code='CLI-INTEL2',
    )


# =========================================================================
# BRIEFING
# =========================================================================

@pytest.fixture
def briefing(db, workspace, client):
    from apps.briefings.models import Briefing
    return Briefing.objects.create(
        workspace=workspace,
        client=client,
        title='Briefing Intel',
        structure_snapshot={'sections': []},
    )


# =========================================================================
# ANALYSIS JOB
# =========================================================================

@pytest.fixture
def analysis_job(db, workspace, client, briefing):
    from apps.intelligence.models import AnalysisJob
    return AnalysisJob.objects.create(
        workspace=workspace,
        client=client,
        briefing=briefing,
        target_kinds=[],
        data_version='v1',
        job_key='job-intel-1',
    )


@pytest.fixture
def analysis_job_client_only(db, workspace, client):
    """Job sem briefing — análise do cliente como um todo."""
    from apps.intelligence.models import AnalysisJob
    return AnalysisJob.objects.create(
        workspace=workspace,
        client=client,
        briefing=None,
        target_kinds=[],
        data_version='v1',
        job_key='job-intel-client-only',
    )


# =========================================================================
# USUÁRIO
# =========================================================================

@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email='intel-user@example.com', password='x',
    )


# =========================================================================
# CONSOLE — provider e métrica
# =========================================================================

@pytest.fixture
def openai_provider(db):
    from apps.console.models import Provider
    provider, _ = Provider.objects.get_or_create(
        key='openai',
        defaults={'name': 'OpenAI', 'category': 'ai', 'is_active': True},
    )
    return provider


@pytest.fixture
def ai_metric(db):
    from apps.console.models import UsageMetric
    metric, _ = UsageMetric.objects.get_or_create(
        key='ai.credits',
        defaults={
            'name': 'AI Credits',
            'unit': 'token',
            'kind': 'counter',
            'origin': 'recorded',
            'is_active': True,
        },
    )
    return metric


@pytest.fixture
def openai_pricing(db, openai_provider, ai_metric):
    """Pricing vigente para a chamada de teste."""
    from apps.console.models import ProviderPricing
    return ProviderPricing.objects.create(
        provider=openai_provider,
        metric=ai_metric,
        pricing_model='unit',
        unit_price=Decimal('0.00001'),
        currency='USD',
        starts_at=timezone.now(),
        is_active=True,
    )


# =========================================================================
# MOCK DE QUOTA
# =========================================================================

@pytest.fixture
def allow_quota(mocker):
    """
    Força `console.public.is_ai_execution_allowed` a permitir.

    Usado por qualquer teste que chegue a `AICallService.call`. Não
    depende de plano configurado — apenas do mock.
    """
    return mocker.patch(
        'apps.console.public.is_ai_execution_allowed',
        return_value=(True, 'ok'),
    )