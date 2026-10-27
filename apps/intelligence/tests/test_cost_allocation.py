"""
Testes da alocação de custo.

Cobrem:
    - N == 1  → 100% para o único insight.
    - N > 1   → divisão igual.
    - Custo desconhecido → allocated_cost=None, is_estimated=True.
    - Idempotência (não duplica).
    - N == 0  → nenhuma alocação.
"""

from decimal import Decimal

import pytest

from apps.intelligence.models import (
    InsightItem, InsightCostAllocation,
)
from apps.intelligence.services import CostAllocationService


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-cost-test')


@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='C', email='c@c.com',
        public_code='CLI-COST01',
    )


@pytest.fixture
def run(db, workspace, client):
    from apps.intelligence.models import AnalysisJob, AnalysisRun
    from django.utils import timezone
    job = AnalysisJob.objects.create(
        workspace=workspace, client=client, briefing=None,
        target_kinds=[InsightItem.KIND_DESIRE],
        data_version='v1', job_key='j-cost',
    )
    return AnalysisRun.objects.create(
        job=job, workspace=workspace, client=client, briefing=None,
        input_hash='h-cost', data_version='v1',
        provider='openai', model='m', prompt_version='v1',
        status='completed', started_at=timezone.now(),
    )


@pytest.fixture
def usage_record(db):
    """Cria um UsageRecord real para o teste de custo."""
    from apps.console.models import (
        Provider, UsageMetric, UsageRecord,
    )
    from django.utils import timezone
    provider, _ = Provider.objects.get_or_create(
        key='openai', defaults={'name': 'OpenAI', 'category': 'ai'},
    )
    metric, _ = UsageMetric.objects.get_or_create(
        key='ai.credits',
        defaults={
            'name': 'AI', 'unit': 'credit', 'kind': 'counter',
            'origin': 'recorded',
        },
    )
    return UsageRecord.objects.create(
        provider=provider, metric=metric,
        occurred_at=timezone.now(), quantity=Decimal('100'),
        unit='credit', estimated_cost=Decimal('1.00000000'),
        currency='USD',
    )


def _make_insight(run, kind, content):
    return InsightItem.objects.create(
        run=run, workspace=run.workspace, client=run.client,
        briefing=run.briefing, kind=kind, content=content,
    )


@pytest.mark.django_db
class TestCostAllocation:

    def test_single_insight_gets_full_cost(self, run, usage_record):
        _make_insight(run, InsightItem.KIND_DESIRE, 'only')
        response = {
            'usage_record_id': str(usage_record.id),
            'input_tokens': 10, 'output_tokens': 5, 'duration_ms': 100,
        }
        allocations = CostAllocationService.allocate_for_run(run, response)
        assert len(allocations) == 1
        a = allocations[0]
        assert a.allocated_cost == Decimal('1.00000000')
        assert a.is_estimated is False
        assert a.allocation_rule == InsightCostAllocation.RULE_SINGLE_INSIGHT

    def test_multiple_insights_equal_split(self, run, usage_record):
        _make_insight(run, InsightItem.KIND_DESIRE, 'a')
        _make_insight(run, InsightItem.KIND_ATTENTION, 'b')
        response = {'usage_record_id': str(usage_record.id)}
        allocations = CostAllocationService.allocate_for_run(run, response)
        assert len(allocations) == 2
        for a in allocations:
            assert a.allocated_cost == Decimal('0.50000000')
            assert a.is_estimated is True
            assert a.allocation_rule == InsightCostAllocation.RULE_EQUAL_SPLIT

    def test_unknown_cost_is_none_not_zero(self, run):
        _make_insight(run, InsightItem.KIND_DESIRE, 'x')
        # usage_record_id inventado → _fetch_usage_cost devolve None
        import uuid
        response = {'usage_record_id': str(uuid.uuid4())}
        allocations = CostAllocationService.allocate_for_run(run, response)
        assert len(allocations) == 1
        a = allocations[0]
        assert a.allocated_cost is None
        assert a.is_estimated is True  # porque é rateio de valor desconhecido

    def test_idempotent(self, run, usage_record):
        _make_insight(run, InsightItem.KIND_DESIRE, 'x')
        response = {'usage_record_id': str(usage_record.id)}
        first = CostAllocationService.allocate_for_run(run, response)
        second = CostAllocationService.allocate_for_run(run, response)
        assert len(first) == 1
        assert len(second) == 1
        assert first[0].id == second[0].id
        assert InsightCostAllocation.objects.count() == 1

    def test_no_insights_no_allocation(self, run, usage_record):
        response = {'usage_record_id': str(usage_record.id)}
        assert CostAllocationService.allocate_for_run(run, response) == []
        assert InsightCostAllocation.objects.count() == 0

    def test_no_usage_record_id_no_allocation(self, run):
        _make_insight(run, InsightItem.KIND_DESIRE, 'x')
        assert CostAllocationService.allocate_for_run(run, {}) == []