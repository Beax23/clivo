"""
Testes do WorkspaceSubscriptionService.

Cobrem a correção introduzida após o Commit A: com múltiplas
assinaturas por Workspace, o serviço DEVE filtrar por `is_active=True`
para retornar a assinatura vigente, não uma histórica.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from datetime import timedelta

from apps.console.models import Plan
from apps.workspaces.models import Workspace, WorkspaceSubscription
from apps.workspaces.services.subscription_service import (
    WorkspaceSubscriptionService,
)


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def plan_a(db):
    return Plan.objects.create(
        key='plan-a',
        name='Plan A',
        price=Decimal('10.00'),
        is_active=True,
    )


@pytest.fixture
def plan_b(db):
    return Plan.objects.create(
        key='plan-b',
        name='Plan B',
        price=Decimal('20.00'),
        is_active=True,
    )


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(
        name='WS Service Test',
        slug='ws-service-test',
    )


# =========================================================================
# HELPERS
# =========================================================================

def _subscribe(workspace, plan, is_active=True, started_offset_days=0):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=timezone.now() + timedelta(days=started_offset_days),
    )


# =========================================================================
# GET_SUBSCRIPTION
# =========================================================================

@pytest.mark.django_db
class TestGetSubscription:

    def test_returns_none_when_no_subscription_exists(self, workspace):
        """Workspace sem nenhuma subscription → None."""
        assert WorkspaceSubscriptionService.get_subscription(workspace) is None

    def test_returns_none_when_only_inactive_subscriptions(
        self, workspace, plan_a,
    ):
        """
        Workspace com apenas assinaturas históricas (inativas) → None.

        Este é o ponto central da correção: antes, o método buscava
        `objects.get(workspace=...)` e poderia retornar uma inativa
        ou levantar `MultipleObjectsReturned`.
        """
        _subscribe(workspace, plan_a, is_active=False, started_offset_days=-2)
        _subscribe(workspace, plan_a, is_active=False, started_offset_days=-1)

        assert WorkspaceSubscriptionService.get_subscription(workspace) is None

    def test_returns_active_subscription(self, workspace, plan_a):
        """Retorna a assinatura ativa quando ela existe."""
        active = _subscribe(workspace, plan_a, is_active=True)

        result = WorkspaceSubscriptionService.get_subscription(workspace)
        assert result is not None
        assert result.id == active.id

    def test_returns_active_among_history(self, workspace, plan_a, plan_b):
        """
        Workspace com histórico de várias assinaturas inativas e uma
        ativa — retorna apenas a ativa.
        """
        _subscribe(workspace, plan_a, is_active=False, started_offset_days=-3)
        _subscribe(workspace, plan_b, is_active=False, started_offset_days=-2)
        _subscribe(workspace, plan_a, is_active=False, started_offset_days=-1)
        active = _subscribe(workspace, plan_b, is_active=True, started_offset_days=0)

        result = WorkspaceSubscriptionService.get_subscription(workspace)
        assert result is not None
        assert result.id == active.id
        assert result.plan_id == plan_b.id

    def test_prefetches_plan(self, workspace, plan_a, django_assert_num_queries):
        """
        O `select_related('plan')` deve evitar query adicional ao
        acessar `subscription.plan`.
        """
        _subscribe(workspace, plan_a, is_active=True)

        # Uma query para buscar a subscription (com join do plan).
        with django_assert_num_queries(1):
            sub = WorkspaceSubscriptionService.get_subscription(workspace)
            # Acessar `.plan` não deve disparar query adicional
            # por causa do select_related.
            _ = sub.plan.key


# =========================================================================
# GET_ACTIVE_PLAN
# =========================================================================

@pytest.mark.django_db
class TestGetActivePlan:

    def test_returns_none_when_no_subscription(self, workspace):
        assert WorkspaceSubscriptionService.get_active_plan(workspace) is None

    def test_returns_none_when_only_inactive(self, workspace, plan_a):
        _subscribe(workspace, plan_a, is_active=False)
        assert WorkspaceSubscriptionService.get_active_plan(workspace) is None

    def test_returns_active_plan(self, workspace, plan_a):
        _subscribe(workspace, plan_a, is_active=True)

        plan = WorkspaceSubscriptionService.get_active_plan(workspace)
        assert plan is not None
        assert plan.id == plan_a.id

    def test_returns_correct_plan_among_history(
        self, workspace, plan_a, plan_b,
    ):
        """Só o plano da assinatura ativa é retornado."""
        _subscribe(workspace, plan_a, is_active=False, started_offset_days=-2)
        _subscribe(workspace, plan_b, is_active=True)

        plan = WorkspaceSubscriptionService.get_active_plan(workspace)
        assert plan is not None
        assert plan.id == plan_b.id