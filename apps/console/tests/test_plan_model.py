"""
Testes da property `Plan.workspaces_count`.

A property representa "Workspaces com assinatura ATIVA neste plano".
Não conta assinaturas históricas (inativas). Não conta Workspaces
sem assinatura ativa.
"""

from decimal import Decimal

import pytest

from apps.console.models import Plan
from apps.workspaces.models import Workspace, WorkspaceSubscription


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


def _make_workspace(slug: str) -> Workspace:
    return Workspace.objects.create(name=f'WS {slug}', slug=slug)


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=workspace.created_at,
    )


# =========================================================================
# CONTAGEM
# =========================================================================

@pytest.mark.django_db
class TestPlanWorkspacesCount:

    def test_count_zero_for_new_plan(self, plan_a):
        """Plano sem nenhum Workspace associado → 0."""
        assert plan_a.workspaces_count == 0

    def test_count_one_active_workspace(self, plan_a):
        """Um Workspace com assinatura ativa → 1."""
        ws = _make_workspace('ws-one')
        _subscribe(ws, plan_a, is_active=True)

        assert plan_a.workspaces_count == 1

    def test_count_multiple_active_workspaces(self, plan_a):
        """Vários Workspaces com assinatura ativa → N."""
        ws1 = _make_workspace('ws-multi-1')
        ws2 = _make_workspace('ws-multi-2')
        ws3 = _make_workspace('ws-multi-3')

        _subscribe(ws1, plan_a, is_active=True)
        _subscribe(ws2, plan_a, is_active=True)
        _subscribe(ws3, plan_a, is_active=True)

        assert plan_a.workspaces_count == 3

    def test_inactive_subscriptions_do_not_count(self, plan_a):
        """
        Assinatura inativa NÃO incrementa a contagem.

        Cobre tanto o caso "Workspace só tem histórico" quanto
        "Workspace tem histórico + ativa".
        """
        ws_only_inactive = _make_workspace('ws-inactive-only')
        _subscribe(ws_only_inactive, plan_a, is_active=False)

        ws_with_history = _make_workspace('ws-with-history')
        _subscribe(ws_with_history, plan_a, is_active=False)
        _subscribe(ws_with_history, plan_a, is_active=True)

        # Só o segundo Workspace entra (uma assinatura ativa = 1).
        assert plan_a.workspaces_count == 1

    def test_workspace_without_any_subscription_not_counted(self, plan_a):
        """
        Workspace sem assinatura ativa (e sem nenhuma assinatura)
        NÃO entra na contagem.
        """
        _make_workspace('ws-no-sub')

        assert plan_a.workspaces_count == 0

    def test_workspaces_in_different_plans_counted_separately(
        self, plan_a, plan_b,
    ):
        """Cada plano conta apenas os seus Workspaces ativos."""
        ws_a1 = _make_workspace('ws-a1')
        ws_a2 = _make_workspace('ws-a2')
        ws_b1 = _make_workspace('ws-b1')

        _subscribe(ws_a1, plan_a, is_active=True)
        _subscribe(ws_a2, plan_a, is_active=True)
        _subscribe(ws_b1, plan_b, is_active=True)

        assert plan_a.workspaces_count == 2
        assert plan_b.workspaces_count == 1

    def test_count_updates_after_subscription_ends(self, plan_a):
        """
        Quando a assinatura é encerrada (is_active=False), a contagem
        diminui. Isso valida que o filtro é aplicado em tempo real,
        não em cache.
        """
        ws = _make_workspace('ws-end')
        sub = _subscribe(ws, plan_a, is_active=True)

        assert plan_a.workspaces_count == 1

        sub.is_active = False
        sub.save(update_fields=['is_active'])

        # Recarrega o plano? Não é necessário — a property dispara
        # query nova a cada chamada, sem cache.
        assert plan_a.workspaces_count == 0