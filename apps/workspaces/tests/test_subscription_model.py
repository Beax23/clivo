"""
Testes do modelo WorkspaceSubscription (multi-assinatura).

Cobrem:
    - Property `active_subscription` (workspace.active_subscription).
    - Constraint condicional: no máximo uma ativa por workspace.
    - Múltiplas assinaturas inativas são permitidas.
    - Workspace sem assinatura ativa é estado válido.
    - Uso do cache `_active_subscriptions` (populado por Prefetch).

NOTA SOBRE O TESTE DE CONSTRAINT:
    `WorkspaceSubscription.save()` chama `full_clean()`, que valida as
    constraints EM PYTHON. Nesse caminho, a constraint condicional
    levanta `ValidationError`, não `IntegrityError` — porque o Django
    nunca chega a emitir o INSERT.

    Para testar que a constraint existe NO BANCO (que é o que garante
    o invariante sob concorrência), usamos `bulk_create()`, que pula
    o `save()` e o `full_clean()`. Só assim o `IntegrityError` vem
    do banco de verdade.
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.workspaces.models import Workspace, WorkspaceSubscription


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def plan_a(db):
    from apps.console.models import Plan
    return Plan.objects.create(
        key='plan-a', name='Plan A', price=10, is_active=True,
    )


@pytest.fixture
def plan_b(db):
    from apps.console.models import Plan
    return Plan.objects.create(
        key='plan-b', name='Plan B', price=20, is_active=True,
    )


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(name='WS', slug='ws-test')


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=timezone.now(),
    )


# =========================================================================
# PROPERTY active_subscription
# =========================================================================

@pytest.mark.django_db
class TestActiveSubscriptionProperty:

    def test_returns_none_when_no_subscription(self, workspace):
        """Workspace sem nenhuma subscription → None."""
        assert workspace.active_subscription is None

    def test_returns_active_subscription(self, workspace, plan_a):
        sub = _subscribe(workspace, plan_a, is_active=True)
        assert workspace.active_subscription.id == sub.id

    def test_ignores_inactive_subscriptions(
        self, workspace, plan_a, plan_b,
    ):
        """Só a ativa é retornada, mesmo com inativas presentes."""
        _subscribe(workspace, plan_a, is_active=False)
        active = _subscribe(workspace, plan_b, is_active=True)
        assert workspace.active_subscription.id == active.id

    def test_returns_none_when_only_inactive(self, workspace, plan_a):
        _subscribe(workspace, plan_a, is_active=False)
        assert workspace.active_subscription is None


# =========================================================================
# CONSTRAINT DE UNICIDADE CONDICIONAL
# =========================================================================

@pytest.mark.django_db
class TestUniquenessConstraint:

    def test_two_active_subscriptions_rejected(
        self, workspace, plan_a, plan_b,
    ):
        """
        Duas assinaturas ATIVAS para o mesmo workspace → IntegrityError.

        Usa `bulk_create()` para pular `full_clean()`. Sem isso, o
        Django valida a constraint em Python e levanta `ValidationError`
        antes de chegar ao banco — o que não prova que a constraint
        existe no DB.

        Com `bulk_create()`, o INSERT vai direto, e o `IntegrityError`
        vem do banco. É o invariante que importa: sob concorrência,
        quem garante é o DB, não o Python.
        """
        _subscribe(workspace, plan_a, is_active=True)

        duplicate = WorkspaceSubscription(
            workspace=workspace,
            plan=plan_b,
            is_active=True,
            started_at=timezone.now(),
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WorkspaceSubscription.objects.bulk_create([duplicate])

    def test_multiple_inactive_allowed(
        self, workspace, plan_a, plan_b,
    ):
        """
        N assinaturas inativas + 1 ativa → permitido.
        A constraint só bloqueia múltiplas ativas.
        """
        _subscribe(workspace, plan_a, is_active=False)
        _subscribe(workspace, plan_b, is_active=False)
        active = _subscribe(workspace, plan_a, is_active=True)

        assert workspace.subscriptions.count() == 3
        assert workspace.active_subscription.id == active.id

    def test_active_plus_inactive_allowed(
        self, workspace, plan_a, plan_b,
    ):
        """1 ativa + 1 inativa → permitido."""
        active = _subscribe(workspace, plan_a, is_active=True)
        _subscribe(workspace, plan_b, is_active=False)

        assert workspace.subscriptions.count() == 2
        assert workspace.active_subscription.id == active.id


# =========================================================================
# CACHE DO PREFETCH
# =========================================================================

@pytest.mark.django_db
class TestPrefetchCache:

    def test_uses_cached_active_subscriptions(self, workspace, plan_a):
        """
        Se `_active_subscriptions` está populado (Prefetch), a property
        usa o cache sem query adicional.
        """
        sub = _subscribe(workspace, plan_a, is_active=True)
        workspace._active_subscriptions = [sub]
        assert workspace.active_subscription.id == sub.id

    def test_falls_back_to_query_when_cache_absent(
        self, workspace, plan_a,
    ):
        """
        Sem `_active_subscriptions`, a property dispara query
        filtrada e retorna a assinatura correta.
        """
        _subscribe(workspace, plan_a, is_active=True)
        assert not hasattr(workspace, '_active_subscriptions')
        assert workspace.active_subscription is not None

    def test_cache_empty_returns_none(self, workspace):
        """
        `_active_subscriptions = []` (Prefetch não encontrou nenhuma)
        → None, sem query.
        """
        workspace._active_subscriptions = []
        assert workspace.active_subscription is None